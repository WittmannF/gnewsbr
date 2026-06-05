#!/usr/bin/env python3
"""Publish enrichment outputs to public/data/enrichment."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR / "scripts"))

from enrichment.paths import ENRICHMENT_PUBLIC, article_summaries_dir, cluster_summaries_dir
from enrichment.schemas import ArticleSummary, ClusterSummary


def publish(
    date: str,
    art_summaries_dir: Path,
    clus_summaries_dir: Path,
    newsletter_json: Path,
    output_dir: Path,
    model: str,
    article_prompt_version: str,
    cluster_prompt_version: str,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    clusters_public = output_dir / "clusters"
    clusters_public.mkdir(parents=True, exist_ok=True)

    # Load article summaries
    article_count = 0
    for path in art_summaries_dir.glob("*.json"):
        try:
            summary = ArticleSummary.model_validate_json(path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  SKIP article summary {path.name}: {e}", file=sys.stderr)
            continue
        article_count += 1
        # Article summaries are NOT published individually (no full text in public)

    # Load cluster summaries and publish
    cluster_entries = []
    for path in clus_summaries_dir.glob("*.json"):
        try:
            cs = ClusterSummary.model_validate_json(path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  SKIP cluster summary {path.name}: {e}", file=sys.stderr)
            continue

        # Publish individual cluster file (no full article text)
        cluster_out = clusters_public / f"{cs.clusterId}.json"
        cluster_out.write_text(cs.model_dump_json(indent=2), encoding="utf-8")

        cluster_entries.append({
            "clusterId": cs.clusterId,
            "neutralHeadline": cs.neutralHeadline,
            "neutralSummary": cs.neutralSummary,
            "whyItMatters": cs.whyItMatters,
            "newsletterBlurb": cs.newsletterBlurb,
            "headlineDivergenceLevel": cs.headlineDivergence.level,
            "confidence": cs.confidence,
            "articleSummaryCount": article_count,
        })

    newsletter_ref: dict = {}
    if newsletter_json.exists():
        newsletter_ref = {
            "json": f"/data/enrichment/newsletters/{date}.json",
            "markdown": f"/data/enrichment/newsletters/{date}.md",
        }

    latest = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "date": date,
        "model": model,
        "promptVersions": {
            "article": article_prompt_version,
            "cluster": cluster_prompt_version,
        },
        "clusterCount": len(cluster_entries),
        "articleSummaryCount": article_count,
        "newsletter": newsletter_ref,
        "clusters": cluster_entries,
    }

    (output_dir / "latest.json").write_text(
        json.dumps(latest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Published: {len(cluster_entries)} clusters, {article_count} article summaries")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None)
    parser.add_argument("--article-summaries-dir", default=None)
    parser.add_argument("--cluster-summaries-dir", default=None)
    parser.add_argument("--newsletter-json", default=None)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--model", default="llama3.2:3b")
    parser.add_argument("--article-prompt-version", default="article-summary-v1")
    parser.add_argument("--cluster-prompt-version", default="cluster-summary-v1")
    args = parser.parse_args()

    from datetime import datetime, timezone
    date = args.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    art_dir = Path(args.article_summaries_dir) if args.article_summaries_dir else article_summaries_dir(date)
    clu_dir = Path(args.cluster_summaries_dir) if args.cluster_summaries_dir else cluster_summaries_dir(date)
    nl_json = Path(args.newsletter_json) if args.newsletter_json else ENRICHMENT_PUBLIC / "newsletters" / f"{date}.json"
    out_dir = Path(args.output_dir) if args.output_dir else ENRICHMENT_PUBLIC

    publish(date, art_dir, clu_dir, nl_json, out_dir, args.model, args.article_prompt_version, args.cluster_prompt_version)


if __name__ == "__main__":
    main()
