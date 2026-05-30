#!/usr/bin/env python3
"""Migrate legacy monolithic archive snapshots to partitioned daily folders.

Legacy format:
  public/data/archive/YYYY-MM-DD.json

Partitioned format:
  public/data/archive/YYYY-MM-DD/index.json
  public/data/archive/YYYY-MM-DD/story_xxx.json
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path
from typing import Any

from generate_news_data import build_cluster_summary, with_source_coverage

DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def unique_detail_filename(cluster: dict[str, Any], used_names: dict[str, int], fallback_index: int) -> str:
    base = cluster.get("id")
    if not isinstance(base, str) or not base.strip():
        base = f"cluster_{fallback_index:04d}"

    count = used_names.get(base, 0)
    used_names[base] = count + 1
    if count == 0:
        return f"{base}.json"
    return f"{base}__{count+1}.json"


def build_index_payload(legacy_payload: dict[str, Any], date_key: str) -> tuple[dict[str, Any], list[tuple[str, dict[str, Any]]]]:
    clusters = legacy_payload.get("clusters", [])
    if not isinstance(clusters, list) or not clusters:
        raise ValueError(f"Archive {date_key} has no clusters")

    sources = legacy_payload.get("sources", [])
    if isinstance(sources, list):
        sources = with_source_coverage(sources, clusters)
    else:
        sources = []

    summaries = []
    detail_pairs: list[tuple[str, dict[str, Any]]] = []
    used_names: dict[str, int] = {}
    for idx, cluster in enumerate(clusters):
        filename = unique_detail_filename(cluster, used_names, idx)
        detail_path = f"data/archive/{date_key}/{filename}"
        summaries.append(build_cluster_summary(cluster, detail_path))
        detail_pairs.append((filename, cluster))

    index_payload = {
        "generatedAt": legacy_payload.get("generatedAt"),
        "version": legacy_payload.get("version", "0.2.0-editorial-collection"),
        "source": legacy_payload.get("source", "Coleta editorial"),
        "stats": legacy_payload.get("stats", {}),
        "sources": sources,
        "clusters": summaries,
    }
    return index_payload, detail_pairs


def migrate_snapshot(archive_dir: Path, legacy_file: Path, delete_legacy: bool) -> tuple[str, int]:
    date_key = legacy_file.stem
    if not DATE_PATTERN.match(date_key):
        raise ValueError(f"Unexpected filename format: {legacy_file.name}")

    payload = json.loads(legacy_file.read_text(encoding="utf-8"))
    index_payload, detail_pairs = build_index_payload(payload, date_key)

    day_dir = archive_dir / date_key
    day_tmp = archive_dir / f".{date_key}.tmp"

    if day_tmp.exists():
        shutil.rmtree(day_tmp)
    day_tmp.mkdir(parents=True, exist_ok=True)

    for filename, cluster in detail_pairs:
        detail_path = day_tmp / filename
        detail_path.write_text(json.dumps(cluster, ensure_ascii=False, indent=2), encoding="utf-8")

    index_path = day_tmp / "index.json"
    index_path.write_text(json.dumps(index_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    loaded = json.loads(index_path.read_text(encoding="utf-8"))
    if not loaded.get("clusters"):
        raise ValueError(f"Invalid generated index for {date_key}")

    if day_dir.exists():
        shutil.rmtree(day_dir)
    day_tmp.rename(day_dir)

    missing = [filename for filename, _ in detail_pairs if not (day_dir / filename).exists()]
    if missing:
        raise ValueError(f"Missing detail files for {date_key}: {', '.join(missing[:5])}")

    if delete_legacy:
        legacy_file.unlink()

    return date_key, len(detail_pairs)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive-dir", default="public/data/archive")
    parser.add_argument("--delete-legacy", action="store_true")
    args = parser.parse_args()

    archive_dir = Path(args.archive_dir)
    if not archive_dir.exists():
        raise SystemExit(f"Archive directory not found: {archive_dir}")

    legacy_files = sorted(
        path
        for path in archive_dir.glob("*.json")
        if DATE_PATTERN.match(path.stem)
    )
    if not legacy_files:
        print("No legacy archive JSON files found")
        return 0

    migrated = []
    for legacy in legacy_files:
        date_key, cluster_count = migrate_snapshot(archive_dir, legacy, args.delete_legacy)
        migrated.append((date_key, cluster_count))
        print(f"Migrated {legacy.name} -> {date_key}/index.json ({cluster_count} clusters)")

    print(f"Done. Migrated {len(migrated)} day(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
