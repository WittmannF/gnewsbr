"""Recover historical cluster inputs without contacting an LLM or production APIs.

Requires a full local Git checkout containing the two immutable pre-inference
collection commits. Only public, committed news snapshots are inspected.
The result is a local JSON artifact; no automatic publishing or paid requests.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

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


def recover(manifest: dict):
    recovered, missing = [], []
    for entry in manifest["clusters"]:
        cid = entry["cluster_id"]
        batch = entry["batch_utc"]
        ref = PRE_INFERENCE_REFS.get(batch)
        if not ref:
            missing.append({"cluster_id": cid, "reason": "unknown_batch"})
            continue
        latest = git_json(ref, "public/data/latest.json")
        if not latest:
            missing.append({"cluster_id": cid, "reason": "snapshot_not_in_checkout", "ref": ref})
            continue
        item = next((c for c in latest.get("clusters", []) if c.get("id") == cid), None)
        if not item:
            missing.append({"cluster_id": cid, "reason": "absent_from_pre_inference_snapshot", "ref": ref})
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
        sources = [
            {"source": a.get("source", ""), "title": a.get("title", ""),
             "description": a.get("description", "")}
            for a in articles
        ]
        if not sources:
            missing.append({"cluster_id": cid, "reason": "no_articles", "ref": ref})
            continue
        recovered.append({
            "cluster_id": cid, "historical_outcome": entry["outcome"],
            "snapshot_sha": ref, "title": item.get("title", ""),
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
