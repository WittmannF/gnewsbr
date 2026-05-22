#!/usr/bin/env python3
"""Validate GNewsBR source spectrum files."""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SPECTRUM_PATH = ROOT / "data/sources/source-spectrum.yml"
ALIASES_PATH = ROOT / "data/sources/source-aliases.yml"
VALID_BUCKETS = {"left", "centerLeft", "center", "centerRight", "right"}
VALID_TYPES = {"editorial", "official", "business", "local", "aggregator", "entertainment", "sector"}
VALID_SCOPES = {"national", "regional", "local", "international"}
VALID_CONFIDENCE = {"low", "medium", "high"}
VALID_REVIEW = {"draft", "reviewed", "disputed"}


def score_to_bucket(score: int) -> str:
    if score <= 2:
        return "left"
    if score <= 4:
        return "centerLeft"
    if score <= 6:
        return "center"
    if score <= 8:
        return "centerRight"
    return "right"


def fail(errors: list[str]) -> int:
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    return 1 if errors else 0


def main() -> int:
    errors: list[str] = []
    spectrum_doc = yaml.safe_load(SPECTRUM_PATH.read_text(encoding="utf-8")) or {}
    aliases_doc = yaml.safe_load(ALIASES_PATH.read_text(encoding="utf-8")) or {}
    sources = spectrum_doc.get("sources") or []
    aliases = aliases_doc.get("aliases") or {}

    if not isinstance(sources, list):
        errors.append("source-spectrum.yml must contain a list under 'sources'")
        return fail(errors)

    names: set[str] = set()
    for idx, source in enumerate(sources, start=1):
        prefix = f"sources[{idx}]"
        if not isinstance(source, dict):
            errors.append(f"{prefix} must be a mapping")
            continue
        name = source.get("name")
        if not name:
            errors.append(f"{prefix}.name is required")
            continue
        if name in names:
            errors.append(f"duplicate source name: {name}")
        names.add(name)

        score = source.get("spectrum_score")
        if not isinstance(score, int) or not (1 <= score <= 10):
            errors.append(f"{name}: spectrum_score must be an integer from 1 to 10")
        else:
            expected = score_to_bucket(score)
            if source.get("spectrum_bucket") != expected:
                errors.append(f"{name}: spectrum_bucket should be {expected!r} for score {score}")

        if source.get("spectrum_bucket") not in VALID_BUCKETS:
            errors.append(f"{name}: invalid spectrum_bucket")
        if source.get("type") not in VALID_TYPES:
            errors.append(f"{name}: invalid type {source.get('type')!r}")
        if source.get("scope") not in VALID_SCOPES:
            errors.append(f"{name}: invalid scope {source.get('scope')!r}")
        if source.get("confidence") not in VALID_CONFIDENCE:
            errors.append(f"{name}: invalid confidence")
        if source.get("review_status") not in VALID_REVIEW:
            errors.append(f"{name}: invalid review_status")
        weight = source.get("political_weight")
        if not isinstance(weight, (int, float)) or not (0 <= float(weight) <= 1):
            errors.append(f"{name}: political_weight must be between 0 and 1")
        if not source.get("rationale"):
            errors.append(f"{name}: rationale is required")

    if not isinstance(aliases, dict):
        errors.append("source-aliases.yml must contain a mapping under 'aliases'")
    else:
        for alias, canonical in aliases.items():
            if canonical not in names:
                errors.append(f"alias {alias!r} points to unknown canonical source {canonical!r}")

    if errors:
        return fail(errors)
    print(f"OK: {len(sources)} sources and {len(aliases)} aliases validated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
