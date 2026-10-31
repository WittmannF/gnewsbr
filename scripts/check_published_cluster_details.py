#!/usr/bin/env python3
"""Fail a Pages deployment if its homepage references missing cluster details."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def missing_details(root: Path) -> list[str]:
    index = root / "data" / "latest.json"
    payload = json.loads(index.read_text(encoding="utf-8"))
    if not payload.get("clusters"):
        raise ValueError("Latest news index contains no clusters")
    return [
        str(cluster["detailPath"])
        for cluster in payload["clusters"]
        if not (root / cluster["detailPath"]).is_file()
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("dist"))
    args = parser.parse_args()
    missing = missing_details(args.root)
    if missing:
        raise SystemExit(
            f"FAIL: {len(missing)} homepage detail JSON files are missing: "
            + ", ".join(missing[:5])
        )
    print("PASS: all homepage cluster details exist in the Pages artifact")


if __name__ == "__main__":
    main()
