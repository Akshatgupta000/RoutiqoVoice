"""Lead qualification rules.

The score is plain arithmetic so it can be explained in an interview.
A model does not decide the score.

Points
- 30 if the company manages 10 or more vehicles
- 30 if the customer described a logistics or fleet problem
- 25 if the customer wants a product demonstration
- 15 if the customer gave an email address

Maximum: 100

Status
- 70 to 100: Qualified
- 40 to 69: Potential
- 0 to 39: Not Qualified
"""

from __future__ import annotations

import re

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# These phrases mean the customer did not actually describe a problem.
_NO_PROBLEM = {
    "",
    "none",
    "n/a",
    "na",
    "no",
    "no problem",
    "no problems",
    "nothing",
    "no issues",
    "no issue",
}

_PROBLEM_CUES = (
    "struggle",
    "problem",
    "challenge",
    "manual",
    "late",
    "delay",
    "inefficien",
    "bottleneck",
    "difficult",
    "hard to",
    "waste",
    "fuel",
    "missed",
    "pain",
    "chaos",
    "spreadsheet",
)

_NAME_BLOCKLIST = {
    "interested",
    "looking",
    "calling",
    "here",
    "good",
    "fine",
    "yes",
    "no",
    "hello",
    "hi",
}

# The cue is matched either way ("I am" or "i am"). The name itself still
# needs a capital letter so words like "interested" are not captured.
_NAME_RE = re.compile(
    r"(?:[Mm]y name is|[Tt]his is|[Ii]['’]m|[Ii] am)\s+"
    r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})"
)
_COMPANY_RE = re.compile(
    r"(?:work(?:ing)? (?:at|for)|company(?: name)? is|from)\s+"
    r"([A-Z][A-Za-z0-9&.'\-]+(?:\s+[A-Z][A-Za-z0-9&.'\-]+){0,4})"
)
_VEHICLE_RE = re.compile(
    r"\b(\d{1,6})\s+(?:vehicles|vehicle|trucks|truck|vans|van|lorries|lorry|bikes|riders)\b",
    re.IGNORECASE,
)
_FLEET_OF_RE = re.compile(r"\bfleet of\s+(\d{1,6})\b", re.IGNORECASE)
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")

# Later matches win, so a customer can correct an earlier answer.
_DEMO_PATTERNS = (
    (
        re.compile(
            r"\b(?:not interested|no demo|don't want a demo|do not want a demo|no demonstration)\b",
            re.IGNORECASE,
        ),
        False,
    ),
    (
        re.compile(
            r"\b(?:interested in (?:a |the )?(?:product )?(?:demo|demonstration)"
            r"|would like (?:a |the )?(?:product )?(?:demo|demonstration)"
            r"|want (?:a |the )?(?:product )?(?:demo|demonstration)"
            r"|schedule a demo|book a demo)\b",
            re.IGNORECASE,
        ),
        True,
    ),
    (re.compile(r"\byes\b.{0,48}\b(?:demo|demonstration)\b", re.IGNORECASE), True),
    (re.compile(r"\b(?:demo|demonstration)\b.{0,24}\byes\b", re.IGNORECASE), True),
)


def has_business_problem(business_problem: str | None) -> bool:
    text = (business_problem or "").strip().lower()
    return text not in _NO_PROBLEM


def has_contact_information(email: str | None) -> bool:
    """Email is the follow-up contact. A name alone cannot receive a reply."""
    if not email:
        return False
    return EMAIL_RE.match(email.strip()) is not None


def classify_score(score: int) -> str:
    if score >= 70:
        return "Qualified"
    if score >= 40:
        return "Potential"
    return "Not Qualified"


def recommended_next_action(status: str, interested_in_demo: bool) -> str:
    """A recommendation for the sales team. This does not book a calendar slot."""
    if status == "Qualified" and interested_in_demo:
        return "Schedule a product demonstration with the sales team."
    if status == "Qualified":
        return "Contact the customer and invite them to a product demonstration."
    if status == "Potential" and interested_in_demo:
        return "Confirm the demonstration request and collect any missing qualification details."
    if status == "Potential":
        return "Send a follow-up with Routiqo information and ask if they want a demonstration."
    return "Thank the customer and keep the lead for a later follow-up. No immediate demo."


def score_lead(
    vehicle_count: int | None,
    business_problem: str | None,
    interested_in_demo: bool,
    email: str | None,
) -> dict:
    vehicle_points = 30 if vehicle_count is not None and vehicle_count >= 10 else 0
    problem_points = 30 if has_business_problem(business_problem) else 0
    demo_points = 25 if interested_in_demo else 0
    contact_points = 15 if has_contact_information(email) else 0
    total = min(100, vehicle_points + problem_points + demo_points + contact_points)
    status = classify_score(total)
    return {
        "lead_score": total,
        "qualification_status": status,
        "recommended_next_action": recommended_next_action(status, interested_in_demo),
        "score_breakdown": {
            "vehicle_count": vehicle_points,
            "business_problem": problem_points,
            "demo_interest": demo_points,
            "contact_information": contact_points,
        },
    }


def demo_interest_label(interested_in_demo: bool | None) -> str:
    if interested_in_demo is True:
        return "Demo requested"
    if interested_in_demo is False:
        return "No demo requested"
    return "Not discussed"


def build_fallback_summary(
    *,
    customer_name: str | None,
    company_name: str | None,
    vehicle_count: int | None,
    business_problem: str | None,
    interested_in_demo: bool | None,
    transcript: str,
    score: dict | None,
) -> dict:
    """Used when Gemini is not called or the summary request fails."""
    name = (customer_name or "The customer").strip()
    company = (company_name or "an unnamed company").strip()
    vehicles = "unknown" if vehicle_count is None else str(vehicle_count)
    problem = (business_problem or "").strip() or "Not stated"
    demo_label = demo_interest_label(interested_in_demo)
    requirements = problem if problem != "Not stated" else "Not stated in the captured notes"
    next_action = (
        score["recommended_next_action"]
        if score
        else "Review the call notes and follow up if the customer is a fit."
    )
    score_text = "not calculated"
    if score:
        score_text = f"{score['lead_score']} ({score['qualification_status']})"

    summary = (
        f"{name} from {company} spoke with the Routiqo sales assistant. "
        f"Fleet size: {vehicles} vehicles. "
        f"Pain point: {problem}. "
        f"Demo interest: {demo_label}. "
        f"Lead score: {score_text}. "
        f"Recommended next action: {next_action}"
    )
    if not customer_name and not company_name and transcript:
        excerpt = " ".join(transcript.split())
        if len(excerpt) > 400:
            excerpt = excerpt[:400].rstrip() + "..."
        summary = f"Call notes: {excerpt} Recommended next action: {next_action}"

    return {
        "summary": summary,
        "customer_requirements": requirements,
        "pain_points": problem,
        "demo_interest": demo_label,
        "next_action": next_action,
        "mode": "fallback",
        "lead_score": None if score is None else score["lead_score"],
        "qualification_status": None if score is None else score["qualification_status"],
        "score_breakdown": None if score is None else score["score_breakdown"],
    }


def _last_match(pattern: re.Pattern[str], text: str) -> str | None:
    found = list(pattern.finditer(text))
    if not found:
        return None
    return found[-1].group(1).strip()


def _clean_company(value: str) -> str:
    value = re.sub(r"\s+(and|we|our|with|who|the)$", "", value, flags=re.IGNORECASE).strip(" .,-")
    return value[:160]


def _problem_sentence(text: str) -> str | None:
    sentences = re.split(r"(?<=[.!?])\s+|\n+", text)
    match = None
    for sentence in sentences:
        lowered = sentence.lower()
        if any(cue in lowered for cue in _PROBLEM_CUES):
            match = sentence.strip(" \n")
    if not match:
        return None
    match = re.sub(r"\s+", " ", match).strip()
    return match[:300]


def extract_lead_hints(text: str) -> dict:
    """Read obvious lead facts from the transcript with regular expressions.

    This only pre-fills the form. The person running the demo can correct it.
    Qualification still uses the values sent to the save endpoint.
    """
    hints: dict = {}
    if not text or not text.strip():
        return hints

    name = _last_match(_NAME_RE, text)
    if name and name.split()[0].lower() not in _NAME_BLOCKLIST:
        hints["customer_name"] = name

    company = _last_match(_COMPANY_RE, text)
    if company:
        hints["company_name"] = _clean_company(company)

    emails = _EMAIL_RE.findall(text)
    if emails:
        hints["email"] = emails[-1]

    vehicle_matches = [int(item) for item in _VEHICLE_RE.findall(text)]
    fleet_matches = [int(item) for item in _FLEET_OF_RE.findall(text)]
    numbers = vehicle_matches or fleet_matches
    if numbers:
        hints["vehicle_count"] = numbers[-1]

    problem = _problem_sentence(text)
    if problem:
        hints["business_problem"] = problem

    demo_choice = None
    demo_position = -1
    for pattern, value in _DEMO_PATTERNS:
        for match in pattern.finditer(text):
            if match.start() >= demo_position:
                demo_position = match.start()
                demo_choice = value
    if demo_choice is not None:
        hints["interested_in_demo"] = demo_choice

    return hints
