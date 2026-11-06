#!/usr/bin/env python3
"""Offline-only diagnostics for the production Brief response contract.

Never calls a provider or writes production cache/ledger. Uses the production
Pydantic schema to avoid an independently drifting validation contract.
"""
from __future__ import annotations

import json
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = spec_from_file_location("summarize_home", ROOT / "scripts/summarize_home.py")
module = module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)
Brief = module.Brief


def diagnose(raw: str | None, finish_reason: str | None = None) -> dict:
    """Return sanitized diagnostic metadata; never log raw model content."""
    result = {
        "finish_reason": finish_reason,
        "content_characters": len(raw) if isinstance(raw, str) else None,
        "valid": False,
        "error_types": [],
        "error_locations": [],
    }
    if raw is None:
        result["error_types"] = ["missing_content"]
        return result
    try:
        parsed = Brief.model_validate_json(raw)
    except ValueError as exc:
        if hasattr(exc, "errors"):
            errors = exc.errors(include_input=False, include_url=False)
            result["error_types"] = [str(e["type"]) for e in errors]
            result["error_locations"] = [list(e["loc"]) for e in errors]
        else:
            result["error_types"] = [type(exc).__name__]
        return result
    result["valid"] = True
    result["summary_characters"] = len(parsed.summary)
    return result


def self_test() -> None:
    cases = [
        (json.dumps({"summary": "A" * 120}), True, []),
        (json.dumps({"summary": "short"}), False, ["string_too_short"]),
        (json.dumps({"summary": "A" * 1701}), False, ["string_too_long"]),
        (json.dumps({"wrong": "A" * 120}), False, ["missing"]),
        ('{"summary":', False, ["json_invalid"]),
        (None, False, ["missing_content"]),
    ]
    for raw, valid, expected_errors in cases:
        observed = diagnose(raw, "length" if raw == '{"summary":' else "stop")
        assert observed["valid"] is valid, observed
        assert observed["error_types"] == expected_errors, observed
    print(json.dumps({
        "status": "offline_contract_tests_passed",
        "cases": len(cases),
        "schema": Brief.model_json_schema(),
        "paid_requests": 0,
    }, ensure_ascii=False))


if __name__ == "__main__":
    self_test()
