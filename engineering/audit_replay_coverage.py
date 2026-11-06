"""Summarize historical replay coverage without printing article text or prompts.

Offline only. Does not contact providers or mutate production.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def summarize(data: dict, manifest: dict | None = None) -> dict:
    recovered = data.get("recovered", [])
    missing = data.get("missing", [])
    requested = data.get("total_requested")
    ids = [x["cluster_id"] for x in recovered + missing]
    if not isinstance(requested, int) or requested < 0:
        raise ValueError("total_requested must be a nonnegative integer")
    if len(ids) != requested or len(set(ids)) != len(ids):
        raise ValueError("Recovery result must partition all requested cluster IDs exactly once")
    if manifest is not None:
        expected = {entry["cluster_id"]: entry["outcome"] for entry in manifest["clusters"]}
        if len(expected) != len(manifest["clusters"]) or set(ids) != set(expected):
            raise ValueError("Recovered cluster IDs differ from canonical manifest")
        if any(item.get("historical_outcome") != expected[item["cluster_id"]]
               for item in recovered):
            raise ValueError("Recovered historical outcomes differ from canonical manifest")
    provenance = Counter(x.get("snapshot_provenance", "unspecified") for x in recovered)
    if set(provenance) - {"primary_pre_inference", "adjacent_pre_reservation"}:
        raise ValueError("Unexpected snapshot provenance")
    outcomes = Counter(x.get("historical_outcome", "unspecified") for x in recovered)
    missing_reasons = Counter(x.get("reason", "unspecified") for x in missing)
    article_counts = [len(x.get("sources", [])) for x in recovered]
    if any(n <= 0 for n in article_counts):
        raise ValueError("Recovered input without source articles")
    return {
        "total_requested": requested,
        "recovered": len(recovered),
        "missing": len(missing),
        "recovered_outcomes": dict(sorted(outcomes.items())),
        "recovered_provenance": dict(sorted(provenance.items())),
        "missing_reasons": dict(sorted(missing_reasons.items())),
        "article_count_min": min(article_counts, default=0),
        "article_count_max": max(article_counts, default=0),
        "replay_equivalence": "not_proven",
        "historical_model_completions_available": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    summary = summarize(json.loads(args.input.read_text(encoding="utf-8")),
                        json.loads(args.manifest.read_text(encoding="utf-8")))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
