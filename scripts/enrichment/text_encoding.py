from __future__ import annotations

import re

try:
    import ftfy

    _FTFY_AVAILABLE = True
except ImportError:
    _FTFY_AVAILABLE = False

_MOJIBAKE_PATTERN = re.compile(r"[ÃÂâ�]")


def _mojibake_score(text: str) -> float:
    if not text:
        return 0.0
    hits = len(_MOJIBAKE_PATTERN.findall(text))
    return hits / len(text)


def has_mojibake(text: str) -> bool:
    return _mojibake_score(text) > 0.005


def repair_mojibake(text: str) -> tuple[str, bool]:
    """Return (repaired_text, repair_was_applied).

    Uses ftfy when available. Falls back to a manual latin-1 round-trip.
    Always keeps the version with fewer mojibake characters.
    """
    if not has_mojibake(text):
        return text, False

    before_score = _mojibake_score(text)
    best = text

    if _FTFY_AVAILABLE:
        candidate = ftfy.fix_text(text)
        if _mojibake_score(candidate) < before_score:
            best = candidate

    # Manual latin-1 round-trip as fallback / additional pass
    try:
        candidate = text.encode("latin-1").decode("utf-8")
        if _mojibake_score(candidate) < _mojibake_score(best):
            best = candidate
    except (UnicodeDecodeError, UnicodeEncodeError):
        pass

    applied = best != text
    return best, applied
