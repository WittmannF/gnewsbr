#!/usr/bin/env python3
"""Prune generated publish output while keeping the full source archive in git.

The repository keeps all historical data under public/data. GitHub Pages does not
need to publish every historical JSON file on every deploy, though: a large Pages
artifact makes deployments slower and less reliable. This script runs after the
Vite build and removes old date-partitioned data from dist/ only.
"""

from __future__ import annotations

import argparse
import re
import shutil
from datetime import date, timedelta
from pathlib import Path

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DATE_FILE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.(json|md)$")

DATE_DIR_ROOTS = (
    Path("archive"),
    Path("article-content"),
)
DATE_FILE_ROOTS = (
    Path("enrichment/newsletters"),
)


def parse_date(value: str) -> date:
    return date.fromisoformat(value)


def discover_newest_date(dist_dir: Path) -> date | None:
    dates: list[date] = []
    for relative_root in DATE_DIR_ROOTS:
        root = dist_dir / relative_root
        if not root.exists():
            continue
        for child in root.iterdir():
            if child.is_dir() and DATE_RE.match(child.name):
                dates.append(parse_date(child.name))
    for relative_root in DATE_FILE_ROOTS:
        root = dist_dir / relative_root
        if not root.exists():
            continue
        for child in root.iterdir():
            if child.is_file():
                match = DATE_FILE_RE.match(child.name)
                if match:
                    dates.append(parse_date(match.group(1)))
    return max(dates) if dates else None


def prune_date_dirs(dist_dir: Path, cutoff: date) -> list[Path]:
    removed: list[Path] = []
    for relative_root in DATE_DIR_ROOTS:
        root = dist_dir / relative_root
        if not root.exists():
            continue
        for child in root.iterdir():
            if not child.is_dir() or not DATE_RE.match(child.name):
                continue
            if parse_date(child.name) < cutoff:
                shutil.rmtree(child)
                removed.append(child)
    return removed


def prune_date_files(dist_dir: Path, cutoff: date) -> list[Path]:
    removed: list[Path] = []
    for relative_root in DATE_FILE_ROOTS:
        root = dist_dir / relative_root
        if not root.exists():
            continue
        for child in root.iterdir():
            if not child.is_file():
                continue
            match = DATE_FILE_RE.match(child.name)
            if match and parse_date(match.group(1)) < cutoff:
                child.unlink()
                removed.append(child)
    return removed


def prune_published_data(dist_dir: Path, days: int) -> dict[str, object]:
    if days < 1:
        raise ValueError("days must be >= 1")

    data_dir = dist_dir / "data"
    if not data_dir.exists():
        return {"status": "skipped", "reason": "no dist/data directory", "removed": 0}

    newest = discover_newest_date(data_dir)
    if newest is None:
        return {"status": "skipped", "reason": "no dated published data found", "removed": 0}

    cutoff = newest - timedelta(days=days - 1)
    removed_dirs = prune_date_dirs(data_dir, cutoff)
    removed_files = prune_date_files(data_dir, cutoff)

    return {
        "status": "ok",
        "newest_date": newest.isoformat(),
        "cutoff_date": cutoff.isoformat(),
        "retention_days": days,
        "removed": len(removed_dirs) + len(removed_files),
        "removed_dirs": [str(path.relative_to(dist_dir)) for path in removed_dirs],
        "removed_files": [str(path.relative_to(dist_dir)) for path in removed_files],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Prune old date-partitioned data from dist/ before Pages upload.")
    parser.add_argument("--dist-dir", default="dist", type=Path, help="Built output directory to prune.")
    parser.add_argument("--days", default=30, type=int, help="Number of recent days to keep, inclusive.")
    args = parser.parse_args()

    result = prune_published_data(args.dist_dir, args.days)
    print(
        "Pruned published data: "
        f"status={result['status']} "
        f"retention_days={result.get('retention_days', args.days)} "
        f"cutoff={result.get('cutoff_date', 'n/a')} "
        f"removed={result['removed']}"
    )


if __name__ == "__main__":
    main()
