"""Recover historical cluster inputs without contacting an LLM or production APIs.

Requires a full local Git checkout containing the two immutable pre-inference
collection commits. Only public, committed news snapshots are inspected.
The result is a local JSON artifact; no automatic publishing or paid requests.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "engineering/fixtures/2026-11-05-cluster-replay-manifest.json"
PRE_INFERENCE_REFS = {
    "2026-11-05T11": "aff04e195cef4c17ab8e56bbbdd981f480f51bfe",
    "2026-11-05T17": "be66cf5d18a9451cb9fed8c0886fc3c9a1db92e0",
}


def git_json(ref: str, path: str):
    if not path.startswith("public/data/") or ".." in Path(path).parts:
        raise ValueError("Unexpected path")
    result = subprocess.run(
        ["git", "show", f"{ref}:{path}"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        return None
    return json.loads(result.stdout)


def candidate_refs(first_reserved_at: str) -> list[str]:
    """Find bounded immutable collection snapshots strictly before reservation."""
    reservation = datetime.fromisoformat(first_reserved_at.replace("Z", "+00:00"))
    if reservation.tzinfo is None:
        raise ValueError("Reservation timestamp must include timezone")
    result = subprocess.run(
        ["git", "log", "--format=%H", "--max-count=80",
         f"--before={reservation.isoformat()}",
         f"--after={(reservation - timedelta(hours=24)).isoformat()}",
         "--", "public/data/latest.json"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    )
    return [x for x in result.stdout.splitlines() if x]


def recover(manifest: dict):
    recovered, missing = [], []
    index_cache = {}
    candidate_cache = {}
    for entry in manifest["clusters"]:
        cid = entry["cluster_id"]
        batch = entry["batch_utc"]
        ref = PRE_INFERENCE_REFS.get(batch)
        if not ref:
            missing.append({"cluster_id": cid, "reason": "unknown_batch"})
            continue
        if ref not in index_cache:
            index_cache[ref] = git_json(ref, "public/data/latest.json")
        latest = index_cache[ref]
        if not latest:
            missing.append({"cluster_id": cid, "reason": "snapshot_not_in_checkout", "ref": ref})
            continue
        item = next((x for x in latest.get("clusters", []) if x.get("id") == cid), None)
        if not item:
            # Only inspect history committed BEFORE the first reservation.
            # Adjacent snapshots are useful controls, not guaranteed exact inputs.
            batch_key = entry["batch_utc"]
            if batch_key not in candidate_cache:
                candidate_cache[batch_key] = candidate_refs(entry["first_reserved_at"])
            for candidate_ref in candidate_cache[batch_key]:
                if candidate_ref == ref:
                    continue
                if candidate_ref not in index_cache:
                    index_cache[candidate_ref] = git_json(candidate_ref, "public/data/latest.json")
                candidate_index = index_cache[candidate_ref] or {}
                match = next(
                    (x for x in candidate_index.get("clusters", []) if x.get("id") == cid),
                    None,
                )
                if match:
                    ref, item = candidate_ref, match
                    break
        if not item:
            missing.append({
                "cluster_id": cid, "reason": "absent_from_bounded_pre_reservation_history",
                "primary_ref": PRE_INFERENCE_REFS[batch],
                "searched_window_hours": 24,
            })
            continue
        detail_path = item.get("detailPath", "")
        if not detail_path.startswith("data/clusters/latest/"):
            missing.append({"cluster_id": cid, "reason": "invalid_detail_path", "ref": ref})
            continue
        detail = git_json(ref, "public/" + detail_path)
        if not detail:
            missing.append({"cluster_id": cid, "reason": "detail_not_in_commit", "ref": ref})
            continue
        articles = detail.get("articles", [])
        # Replay the exact production selection policy, not every article in
        # the detail file. Otherwise provider comparisons use different inputs.
        from scripts.summarize_home import sources_for
        sources = sources_for(detail)
        if len(sources) < 2:
            missing.append({"cluster_id": cid, "reason": "insufficient_distinct_sources", "ref": ref})
            continue
        recovered.append({
            "cluster_id": cid, "historical_outcome": entry["outcome"],
            "snapshot_sha": ref, "snapshot_provenance": ("primary_pre_inference" if ref == PRE_INFERENCE_REFS[batch] else "adjacent_pre_reservation"), "title": item.get("title", ""),
            "sources": sources,
        })
    return {"schema_version": 1, "historical_responses_available": False,
            "recovered": recovered, "missing": missing,
            "total_requested": len(manifest["clusters"])}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = recover(json.loads(MANIFEST.read_text(encoding="utf-8")))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Recovered {len(result['recovered'])}/{result['total_requested']} historical inputs")
    counts = {}
    for item in result["missing"]:
        counts[item["reason"]] = counts.get(item["reason"], 0) + 1
    print("Missing reasons:", json.dumps(counts, sort_keys=True))
    if not result["recovered"]:
        raise SystemExit("No historical inputs recovered; investigate checkout and refs")


if __name__ == "__main__":
    main()
