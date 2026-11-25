"""Keyword retrieval over the Routiqo knowledge file.

This is not a vector database and it does not use embeddings.
Each section gets a score from overlapping words. Heading matches count
more than body matches. The top sections are added to the prompt.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.config import KNOWLEDGE_PATH

_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "your", "you", "are",
    "was", "were", "have", "has", "had", "not", "but", "can", "our", "about",
    "what", "how", "does", "did", "who", "why", "when", "where", "which",
    "into", "onto", "per", "via", "its", "their", "they", "them", "she", "him",
    "her", "his", "any", "all", "use", "using", "used", "than", "then", "also",
    "just", "like", "will", "would", "could", "should", "please", "tell", "me",
    "a", "an", "of", "to", "in", "on", "at", "is", "it", "or", "be", "as", "by",
    "do", "we", "i", "my", "if", "product", "work", "works",
}

# Obvious word variants only. This is still keyword overlap, not semantic search.
_SYNONYMS = {
    "optimize": "optimization",
    "optimise": "optimization",
    "optimized": "optimization",
    "optimised": "optimization",
    "optimizing": "optimization",
    "routes": "route",
    "routing": "route",
    "vehicles": "vehicle",
    "fleets": "fleet",
    "deliveries": "delivery",
    "prices": "pricing",
    "price": "pricing",
    "cost": "pricing",
    "costs": "pricing",
    "savings": "pricing",
    "saving": "pricing",
}

_cache: dict = {"mtime": None, "sections": []}


def _tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9][a-z0-9+\-]{1,}", text.lower())
    tokens = set()
    for word in words:
        if word in _STOPWORDS or len(word) < 3:
            continue
        tokens.add(_SYNONYMS.get(word, word))
    return tokens


def _parse_sections(text: str) -> list[dict]:
    chunks = re.split(r"\n(?=## )", text)
    sections = []
    for chunk in chunks:
        lines = chunk.strip().splitlines()
        if not lines or not lines[0].startswith("## "):
            continue
        title = lines[0][3:].strip()
        body = "\n".join(lines[1:]).strip()
        if title and body:
            sections.append({"title": title, "body": body})
    return sections


def load_sections(path: Path | None = None) -> list[dict]:
    knowledge_path = path or KNOWLEDGE_PATH
    if not knowledge_path.exists():
        return []
    mtime = knowledge_path.stat().st_mtime
    if path is None and _cache["mtime"] == mtime:
        return _cache["sections"]
    sections = _parse_sections(knowledge_path.read_text(encoding="utf-8"))
    if path is None:
        _cache["mtime"] = mtime
        _cache["sections"] = sections
    return sections


def meaningful_terms(query: str) -> set[str]:
    """Query words that retrieval actually uses. Exported for the demo replies."""
    return _tokens(query)


def retrieve(query: str, top_k: int = 3, path: Path | None = None) -> list[dict]:
    """Return the sections whose words overlap the customer message."""
    sections = load_sections(path)
    query_tokens = _tokens(query)
    if not query_tokens:
        return []

    ranked: list[tuple[int, dict]] = []
    for section in sections:
        title_tokens = _tokens(section["title"])
        body_tokens = _tokens(section["body"])
        score = 0
        for token in query_tokens:
            if token in title_tokens:
                score += 3
            elif token in body_tokens:
                score += 1
        if score:
            ranked.append((score, section))

    ranked.sort(key=lambda item: item[0], reverse=True)
    return [section for _, section in ranked[:top_k]]


def overview_section(path: Path | None = None) -> dict | None:
    for section in load_sections(path):
        if section["title"].lower().startswith("what routiqo is"):
            return section
    sections = load_sections(path)
    return sections[0] if sections else None


def build_knowledge_context(query: str, path: Path | None = None) -> tuple[str, list[str]]:
    """Always include the product overview, plus keyword matches.

    The returned titles are only the keyword matches. The overview is context,
    not a claim that the customer's words matched that section.
    """
    matches = retrieve(query, path=path)
    overview = overview_section(path)
    parts: list[str] = []
    titles: list[str] = []
    seen: set[str] = set()

    if overview:
        parts.append(f"## {overview['title']}\n{overview['body']}")
        seen.add(overview["title"])

    for section in matches:
        titles.append(section["title"])
        if section["title"] in seen:
            continue
        parts.append(f"## {section['title']}\n{section['body']}")
        seen.add(section["title"])

    if not parts:
        return "No product knowledge file was found.", []
    return "\n\n".join(parts), titles
