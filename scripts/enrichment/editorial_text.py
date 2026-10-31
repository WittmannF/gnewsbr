"""Remove internal article IDs from reader-facing AI prose, not structured references."""
from __future__ import annotations

import re
from typing import Any

# A generated model sometimes writes "(article_abc123...; article_def...)"
# inside paragraphs. The actual linked sources are stored separately.
_CITATION_GROUP = re.compile(
    r"\s*\(\s*article_[a-f0-9]{8,}(?:\s*[,;]\s*article_[a-f0-9]{8,})*\s*\)",
    re.IGNORECASE,
)
_ARTICLE_ID = re.compile(r"\barticle_[a-f0-9]{8,}\b", re.IGNORECASE)
_EMPTY_GROUP = re.compile(r"\(\s*[,;]?\s*\)")
_SPACE_BEFORE_PUNCTUATION = re.compile(r"\s+([,;:.!?])")


def clean_reader_text(value: str) -> str:
    """Preserve prose while stripping machine-only inline article references."""
    text = _CITATION_GROUP.sub("", value)
    text = _ARTICLE_ID.sub("", text)
    text = _EMPTY_GROUP.sub("", text)
    text = _SPACE_BEFORE_PUNCTUATION.sub(r"\1", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def clean_news_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Only clean editorial strings. Never change articleId, claimId or URLs."""
    news = payload.get("news")
    if not isinstance(news, dict):
        return payload
    for key in ("headline", "subtitle"):
        if isinstance(news.get(key), str):
            news[key] = clean_reader_text(news[key])
    for section in news.get("sections", []):
        if isinstance(section.get("heading"), str):
            section["heading"] = clean_reader_text(section["heading"])
        section["paragraphs"] = [
            clean_reader_text(text) if isinstance(text, str) else text
            for text in section.get("paragraphs", [])
        ]
    for claim in news.get("claims", []):
        if isinstance(claim.get("text"), str):
            claim["text"] = clean_reader_text(claim["text"])
    for angle in news.get("coverageAngles", []):
        if isinstance(angle.get("focus"), str):
            angle["focus"] = clean_reader_text(angle["focus"])
    news["openQuestions"] = [
        clean_reader_text(text) if isinstance(text, str) else text
        for text in news.get("openQuestions", [])
    ]
    return payload
