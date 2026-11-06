#!/usr/bin/env python3
"""Sanitized OpenRouter response envelope analysis, without logging content or secrets.

Offline helper for comparing JSON_SCHEMA/Instructor experiments. No network or
production writes. Keep raw responses only in the ephemeral diagnostic runner.
"""
from __future__ import annotations

import json
from typing import Any

from diagnose_brief_contract import diagnose


def analyze(payload: dict[str, Any], *, variant: str, latency_ms: int | None = None) -> dict:
    choices = payload.get("choices") or []
    choice = choices[0] if choices and isinstance(choices[0], dict) else {}
    message = choice.get("message") or {}
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str):
        content = None
    usage = payload.get("usage") or {}
    if not isinstance(usage, dict):
        usage = {}
    result = diagnose(content, choice.get("finish_reason"))
    result.update({
        "variant": variant,
        "model": payload.get("model"),
        "provider": payload.get("provider"),
        "latency_ms": latency_ms,
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
        "actual_usage_cost_usd": usage.get("cost"),
        "actual_cost_available": isinstance(usage.get("cost"), (float, int)),
        "tool_calls_present": bool(message.get("tool_calls")) if isinstance(message, dict) else False,
    })
    # Never use the budget reservation as a substitute for usage.cost.
    return result


def self_test() -> None:
    base = {"model": "mock", "choices": [{"finish_reason": "stop", "message": {
        "content": json.dumps({"summary": "A" * 120})}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 50}}
    success = analyze(base, variant="json_schema_550", latency_ms=125)
    assert success["valid"] and success["actual_usage_cost_usd"] is None
    assert success["actual_cost_available"] is False
    assert success["prompt_tokens"] == 100
    truncated = analyze({"choices": [{"finish_reason": "length", "message": {
        "content": '{"summary":'}}], "usage": {"cost": 0.002}}, variant="json_schema_550")
    assert truncated["error_types"] == ["json_invalid"]
    assert truncated["finish_reason"] == "length"
    assert truncated["actual_usage_cost_usd"] == 0.002
    missing = analyze({"choices": []}, variant="instructor_tools")
    assert missing["error_types"] == ["missing_content"]
    assert missing["valid"] is False
    print(json.dumps({"status": "envelope_contract_passed", "cases": 3, "paid_requests": 0}))


if __name__ == "__main__":
    self_test()
