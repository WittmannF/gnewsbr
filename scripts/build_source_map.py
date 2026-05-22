#!/usr/bin/env python3
"""Build the source spectrum JSON consumed by the static app/data pipeline."""
from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SPECTRUM_PATH = ROOT / "data/sources/source-spectrum.yml"
ALIASES_PATH = ROOT / "data/sources/source-aliases.yml"
OUTPUT_PATH = ROOT / "public/data/source-spectrum.json"


def main() -> int:
    spectrum_doc = yaml.safe_load(SPECTRUM_PATH.read_text(encoding="utf-8")) or {}
    aliases_doc = yaml.safe_load(ALIASES_PATH.read_text(encoding="utf-8")) or {}
    payload = {
        "version": 1,
        "methodology": "data/sources/methodology.md",
        "sources": spectrum_doc.get("sources") or [],
        "aliases": aliases_doc.get("aliases") or {},
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH.relative_to(ROOT)} with {len(payload['sources'])} sources and {len(payload['aliases'])} aliases.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
