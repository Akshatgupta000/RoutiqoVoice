"""Routiqo sales assistant.

Live replies come from the Gemini API through the official google-genai SDK.
If the key is missing or the API call fails, demo mode writes a short reply
from the same knowledge file and the same lead hints. Demo replies are labeled
`demo` so the interface never presents them as live Gemini output.

The API is stateless. The browser sends the recent transcript with each
message. This file uses the last few turns as context and does not save them.
"""

from __future__ import annotations

import json
import logging
import re

from app.config import Settings
from app.knowledge_base import build_knowledge_context, meaningful_terms, overview_section
from app.lead_service import (
    build_fallback_summary,
    demo_interest_label,
    extract_lead_hints,
    score_lead,
)

logger = logging.getLogger("routiqo.ai")

# Twelve turns is enough to remember a short sales call without a huge request.
HISTORY_LIMIT = 12

SYSTEM_PROMPT = """You are the Routiqo AI Sales Assistant.

You represent Routiqo, a fleet dispatch and route optimization platform for last-mile logistics businesses.

Your job:
- Understand the customer's logistics business.
- Explain only capabilities that appear in the product knowledge.
- Identify the customer's problems.
- Qualify the lead in a natural conversation.
- Collect the customer name, company name, email if they are willing, number of vehicles, current logistics challenges, and whether they want a product demonstration.
- Encourage interested customers to request a demonstration.

Conversation rules:
- Speak naturally and professionally.
- Keep each reply to 2 or 3 short sentences.
- Ask only one question at a time.
- Do not repeat a question the customer already answered.
- Use the earlier messages in this conversation.
- Do not use a high-pressure sales style.
- Never invent product features, integrations, prices, or customer testimonials.
- Never promise specific cost savings or performance numbers.
- Do not say a meeting or appointment is booked. You can record a demo request. A person on the sales team schedules the demonstration.
- Do not request unnecessary personal information. Email is optional.
- If the customer is not interested, thank them and close politely.
- If the product knowledge does not answer a question, say that the sales team can clarify it during a product demonstration.

Product knowledge:
{knowledge}

Details already collected (do not ask for these again):
{known}
"""


def _known_lines(hints: dict) -> str:
    if not hints:
        return "Nothing confirmed yet."
    labels = {
        "customer_name": "Customer name",
        "company_name": "Company",
        "email": "Email",
        "vehicle_count": "Vehicle count",
        "business_problem": "Business problem",
        "interested_in_demo": "Interested in a demo",
    }
    lines = []
    for key, label in labels.items():
        if key in hints:
            lines.append(f"- {label}: {hints[key]}")
    return "\n".join(lines) if lines else "Nothing confirmed yet."


def _trim_history(history: list[dict]) -> list[dict]:
    cleaned = []
    for item in history:
        content = (item.get("content") or "").strip()
        role = item.get("role")
        if content and role in {"user", "assistant"}:
            cleaned.append({"role": role, "content": content})
    return cleaned[-HISTORY_LIMIT:]


def _transcript(history: list[dict], message: str) -> str:
    parts = [item["content"] for item in history]
    parts.append(message)
    return "\n".join(parts)


def _redact(settings: Settings, text: str) -> str:
    if settings.gemini_api_key:
        text = text.replace(settings.gemini_api_key, "[redacted]")
    return text[:300]


def _first_sentences(text: str, count: int = 2) -> str:
    body = " ".join(text.split())
    pieces = re.split(r"(?<=[.!?])\s+", body)
    chosen = " ".join(pieces[:count]).strip()
    if len(chosen) > 420:
        chosen = chosen[:420].rsplit(" ", 1)[0].rstrip("., ") + "."
    return chosen


def _looks_like_question(message: str) -> bool:
    lowered = message.strip().lower()
    if "?" in message:
        return True
    starters = (
        "what", "how", "can ", "does ", "do ", "is ", "are ", "why",
        "where", "when", "tell ", "explain", "price", "cost", "feature",
    )
    return lowered.startswith(starters)


def _is_greeting(message: str) -> bool:
    lowered = re.sub(r"[^a-z\s]", "", message.lower()).strip()
    return lowered in {
        "hi", "hello", "hey", "good morning", "good afternoon", "good evening",
        "hi there", "hello there",
    }


def next_qualification_question(hints: dict) -> str | None:
    """One next question, based on what is still missing."""
    if "company_name" not in hints:
        return "What company do you work with?"
    if "vehicle_count" not in hints:
        return "About how many vehicles are in the fleet?"
    if "business_problem" not in hints:
        return "What is the main dispatch or routing challenge right now?"
    if "customer_name" not in hints:
        return "Who should the sales team ask for?"
    if "email" not in hints:
        return "If you are comfortable sharing it, what email should the team use for follow-up?"
    if "interested_in_demo" not in hints:
        return "Would you like the sales team to arrange a product demonstration?"
    return None


def _acknowledgement(message: str, hints: dict) -> str:
    lowered = message.lower()
    notes = []
    if "vehicle_count" in hints and re.search(r"\d+", message):
        notes.append(f"Noted, a fleet of {hints['vehicle_count']} vehicles.")
    if "business_problem" in hints and any(cue in lowered for cue in ("struggle", "problem", "challenge", "manual", "late", "delay")):
        notes.append("That operational challenge is useful context.")
    if "company_name" in hints and any(word in lowered for word in ("company", "work", "from")):
        notes.append(f"I have {hints['company_name']} in the call notes.")
    if "customer_name" in hints and any(phrase in lowered for phrase in ("my name", "i am", "i'm", "this is")):
        notes.append(f"Thanks, {hints['customer_name']}.")
    if "email" in hints and "@" in message:
        notes.append("I have the email for a sales follow-up.")
    if hints.get("interested_in_demo") is True and re.search(r"demo|demonstration", lowered):
        notes.append("I will mark this as a demo request. This does not book a calendar slot.")
    if hints.get("interested_in_demo") is False and re.search(r"not interested|no demo", lowered):
        notes.append("Understood. I will not push a demonstration.")
    return " ".join(notes[:2])


def build_demo_reply(
    message: str,
    history: list[dict],
    matched_sections: list[dict],
    overview: dict | None = None,
) -> str:
    """Scripted sales reply used only when Gemini is not answering."""
    hints = extract_lead_hints(_transcript(history, message))
    if not history and _is_greeting(message) and not _looks_like_question(message):
        return (
            "Hello, this is the Routiqo sales assistant. "
            "Routiqo helps logistics teams with fleet dispatch and route planning. "
            "What kind of delivery operation are you running?"
        )

    answer = ""
    if _looks_like_question(message):
        covered: set[str] = set()
        for section in matched_sections:
            covered |= meaningful_terms(f"{section['title']} {section['body']}")
        missing = meaningful_terms(message) - covered
        # If the question has words the matched notes do not contain, do not improvise.
        if matched_sections and not missing:
            answer = _first_sentences(matched_sections[0]["body"])
        elif overview and not meaningful_terms(message):
            answer = _first_sentences(overview["body"])
        elif overview and missing == {"routiqo"}:
            answer = _first_sentences(overview["body"])
        else:
            answer = (
                "I do not have that detail in the Routiqo product notes. "
                "The sales team can clarify it during a product demonstration."
            )

    question = next_qualification_question(hints)
    acknowledgement = "" if answer else _acknowledgement(message, hints)
    parts = [part for part in (answer, acknowledgement, question) if part]
    if not parts:
        return (
            "Thank you. I have the main details from this conversation. "
            "The sales team can follow up if a demonstration would be useful."
        )
    return " ".join(parts)


def _section_lookup(titles: list[str], knowledge_text: str) -> list[dict]:
    """Rebuild matched sections from the context text for the demo answer."""
    sections = []
    for title in titles:
        marker = f"## {title}\n"
        start = knowledge_text.find(marker)
        if start == -1:
            continue
        body_start = start + len(marker)
        next_heading = knowledge_text.find("\n## ", body_start)
        body = knowledge_text[body_start: next_heading if next_heading != -1 else None].strip()
        sections.append({"title": title, "body": body})
    return sections


def _call_gemini(settings: Settings, system_instruction: str, history: list[dict], message: str) -> str:
    from google import genai
    from google.genai import types

    client = genai.Client(
        api_key=settings.gemini_api_key,
        http_options=types.HttpOptions(timeout=20000),
    )
    contents = []
    for item in history:
        role = "user" if item["role"] == "user" else "model"
        contents.append(types.Content(role=role, parts=[types.Part.from_text(text=item["content"])]))
    contents.append(types.Content(role="user", parts=[types.Part.from_text(text=message)]))

    response = client.models.generate_content(
        model=settings.gemini_model,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.4,
            max_output_tokens=400,
            # Flash-Lite spends extra tokens on thinking by default. A short
            # sales reply should use the smallest thinking level so the answer
            # is not cut off. If a model rejects this setting, chat falls back
            # to demo mode.
            thinking_config=types.ThinkingConfig(
                thinking_level=types.ThinkingLevel.MINIMAL,
            ),
        ),
    )
    text = (response.text or "").strip()
    if not text:
        raise RuntimeError("Gemini returned an empty reply.")
    return text


def generate_reply(settings: Settings, message: str, history: list[dict]) -> dict:
    trimmed = _trim_history(history)
    # If the browser already appended the current message, do not send it twice.
    if trimmed and trimmed[-1]["role"] == "user" and trimmed[-1]["content"] == message:
        trimmed = trimmed[:-1]

    knowledge_text, titles = build_knowledge_context(message)
    overview = overview_section()
    hints = extract_lead_hints(_transcript(trimmed, message))
    system_instruction = SYSTEM_PROMPT.format(
        knowledge=knowledge_text,
        known=_known_lines(hints),
    )
    matched_sections = _section_lookup(titles, knowledge_text)

    if not settings.ai_configured:
        return {
            "response": build_demo_reply(message, trimmed, matched_sections, overview),
            "mode": "demo",
            "knowledge_sections": titles,
            "lead_hints": hints,
            "notice": None,
        }

    try:
        text = _call_gemini(settings, system_instruction, trimmed, message)
        return {
            "response": text,
            "mode": "gemini",
            "knowledge_sections": titles,
            "lead_hints": hints,
            "notice": None,
        }
    except Exception as exc:
        logger.warning("Gemini chat failed: %s", _redact(settings, f"{type(exc).__name__}: {exc}"))
        return {
            "response": build_demo_reply(message, trimmed, matched_sections, overview),
            "mode": "demo",
            "knowledge_sections": titles,
            "lead_hints": hints,
            "notice": "Gemini did not respond. This reply was generated by demo mode.",
        }


def _parse_json_object(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("Summary response did not contain JSON.")
    parsed = json.loads(cleaned[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("Summary response was not a JSON object.")
    return parsed


def _apply_known_facts(summary: dict, known: dict, score: dict | None) -> dict:
    """Python owns the score and the next action. The model only writes prose."""
    if known.get("interested_in_demo") is not None:
        summary["demo_interest"] = demo_interest_label(known.get("interested_in_demo"))
    if score:
        summary["next_action"] = score["recommended_next_action"]
        summary["lead_score"] = score["lead_score"]
        summary["qualification_status"] = score["qualification_status"]
        summary["score_breakdown"] = score["score_breakdown"]
        if score["recommended_next_action"] not in summary.get("summary", ""):
            summary["summary"] = (
                summary.get("summary", "").rstrip()
                + " Recommended next action: "
                + score["recommended_next_action"]
            )
    for key in ("summary", "customer_requirements", "pain_points", "demo_interest", "next_action"):
        value = summary.get(key)
        summary[key] = str(value).strip() if value else "Not stated"
    return summary


def _call_gemini_summary(settings: Settings, prompt: str) -> str:
    from google import genai
    from google.genai import types

    client = genai.Client(
        api_key=settings.gemini_api_key,
        http_options=types.HttpOptions(timeout=20000),
    )
    response = client.models.generate_content(
        model=settings.gemini_model,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.2,
            max_output_tokens=700,
            thinking_config=types.ThinkingConfig(
                thinking_level=types.ThinkingLevel.MINIMAL,
            ),
        ),
    )
    text = (response.text or "").strip()
    if not text:
        raise RuntimeError("Gemini returned an empty summary.")
    return text


def summarize_call(settings: Settings, payload: dict) -> dict:
    interested = payload.get("interested_in_demo")
    score = None
    if payload.get("vehicle_count") is not None or payload.get("customer_name") or payload.get("company_name"):
        score = score_lead(
            payload.get("vehicle_count"),
            payload.get("business_problem"),
            bool(interested),
            payload.get("email"),
        )

    fallback = build_fallback_summary(
        customer_name=payload.get("customer_name"),
        company_name=payload.get("company_name"),
        vehicle_count=payload.get("vehicle_count"),
        business_problem=payload.get("business_problem"),
        interested_in_demo=interested,
        transcript=payload.get("transcript") or "",
        score=score,
    )
    if not settings.ai_configured:
        return fallback

    prompt = f"""Write a short professional sales-call summary as JSON.
Use only the transcript and notes below. Do not invent facts.
Return one JSON object with these keys:
summary, customer_requirements, pain_points, demo_interest, next_action.
The summary must be under 120 words.

Transcript:
{payload.get("transcript")}

Notes:
Customer: {payload.get("customer_name") or "unknown"}
Company: {payload.get("company_name") or "unknown"}
Email: {payload.get("email") or "not provided"}
Vehicles: {payload.get("vehicle_count") if payload.get("vehicle_count") is not None else "unknown"}
Problem: {payload.get("business_problem") or "not stated"}
Demo interest: {demo_interest_label(interested)}
Lead score from rules: {None if score is None else score["lead_score"]}
Qualification: {None if score is None else score["qualification_status"]}
Next action from rules: {fallback["next_action"]}
"""
    try:
        raw = _call_gemini_summary(settings, prompt)
        parsed = _parse_json_object(raw)
        parsed["mode"] = "gemini"
        return _apply_known_facts(parsed, payload, score)
    except Exception as exc:
        logger.warning("Gemini summary failed: %s", _redact(settings, f"{type(exc).__name__}: {exc}"))
        return fallback
