#!/usr/bin/env python3
"""Orchestrator for the daily LLM enrichment pipeline."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR / "scripts"))

from enrichment.llm_client import make_client
from enrichment.paths import (
    CLUSTERS_LATEST,
    ENRICHMENT_DATA,
    ENRICHMENT_PUBLIC,
    article_content_dir,
    article_summaries_dir,
    cluster_summaries_dir,
    logs_dir,
    normalized_articles_dir,
)
from generate_daily_newsletter import generate_newsletter
from ingest_article_content import ingest
from publish_enrichment_data import publish
from select_articles_for_enrichment import select
from summarize_articles_llm import summarize_articles
from summarize_clusters_llm import summarize_clusters

MIN_CLUSTERS = 5


def run(
    date: str,
    article_content_src: Path,
    max_clusters: int,
    articles_per_cluster: int,
    model: str,
    article_prompt_version: str,
    cluster_prompt_version: str,
    mock_llm: bool = False,
) -> None:
    logs_dir().mkdir(parents=True, exist_ok=True)
    log: dict = {
        "date": date,
        "articlesRead": 0,
        "articlesValid": 0,
        "articlesSelected": 0,
        "articleSummariesGenerated": 0,
        "clusterSummariesGenerated": 0,
        "newsletterGenerated": False,
        "errors": [],
    }

    # --- Phase 1: Ingest ---
    norm_dir = normalized_articles_dir(date)
    normalized = ingest(date, article_content_src, norm_dir)
    log["articlesRead"] = len(list(article_content_src.glob("*/content.json")))
    log["articlesValid"] = len(normalized)

    # --- Phase 2: Select ---
    selected_path = ENRICHMENT_DATA / "selected-articles" / f"{date}.json"
    selection = select(norm_dir, CLUSTERS_LATEST, max_clusters, articles_per_cluster)
    selected_path.parent.mkdir(parents=True, exist_ok=True)
    selected_path.write_text(json.dumps(selection, ensure_ascii=False, indent=2), encoding="utf-8")
    log["articlesSelected"] = sum(c["articleCount"] for c in selection.get("clusters", []))

    # --- Phase 3: Article summaries ---
    client = make_client(model=model, mock=mock_llm)
    art_summaries_dir = article_summaries_dir(date)
    art_summaries, art_errors = summarize_articles(
        date, selected_path, norm_dir, art_summaries_dir, client, model, article_prompt_version
    )
    log["articleSummariesGenerated"] = len(art_summaries)
    log["errors"].extend(art_errors)

    # --- Phase 4: Cluster summaries ---
    clu_summaries_dir = cluster_summaries_dir(date)
    clu_summaries, clu_errors = summarize_clusters(
        date, selected_path, art_summaries_dir, clu_summaries_dir, client, model, cluster_prompt_version
    )
    log["clusterSummariesGenerated"] = len(clu_summaries)
    log["errors"].extend(clu_errors)

    if len(clu_summaries) < MIN_CLUSTERS:
        msg = f"Only {len(clu_summaries)} cluster summaries generated (minimum {MIN_CLUSTERS})"
        print(f"FATAL: {msg}", file=sys.stderr)
        log["errors"].append({"stage": "pipeline", "error": msg})
        _save_log(date, log)
        sys.exit(1)

    # --- Phase 5: Newsletter ---
    nl_json = ENRICHMENT_PUBLIC / "newsletters" / f"{date}.json"
    nl_md = ENRICHMENT_PUBLIC / "newsletters" / f"{date}.md"
    generate_newsletter(date, clu_summaries_dir, nl_json, nl_md)
    log["newsletterGenerated"] = nl_json.exists()

    if not log["newsletterGenerated"]:
        print("FATAL: newsletter was not generated", file=sys.stderr)
        _save_log(date, log)
        sys.exit(1)

    # --- Phase 6: Publish ---
    publish(date, art_summaries_dir, clu_summaries_dir, nl_json, ENRICHMENT_PUBLIC, model, article_prompt_version, cluster_prompt_version)

    _save_log(date, log)
    print(f"\nEnrichment complete for {date}")
    print(f"  Articles: {log['articlesValid']} valid, {log['articlesSelected']} selected")
    print(f"  Summaries: {log['articleSummariesGenerated']} articles, {log['clusterSummariesGenerated']} clusters")
    print(f"  Errors: {len(log['errors'])}")


def _save_log(date: str, log: dict) -> None:
    path = logs_dir() / f"{date}.json"
    path.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run full daily LLM enrichment pipeline")
    parser.add_argument("--date", default=None)
    parser.add_argument("--article-content-dir", default=None)
    parser.add_argument("--max-clusters", type=int, default=20)
    parser.add_argument("--articles-per-cluster", type=int, default=5)
    parser.add_argument("--model", default=None)
    parser.add_argument("--article-prompt-version", default="article-summary-v1")
    parser.add_argument("--cluster-prompt-version", default="cluster-summary-v1")
    parser.add_argument("--mock", action="store_true", help="Use mock LLM (no Ollama needed)")
    args = parser.parse_args()

    date = args.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    model = args.model or "llama3.2:3b"
    src = Path(args.article_content_dir) if args.article_content_dir else article_content_dir(date)

    if not src.exists():
        print(f"Article content dir not found: {src}", file=sys.stderr)
        sys.exit(1)

    run(
        date=date,
        article_content_src=src,
        max_clusters=args.max_clusters,
        articles_per_cluster=args.articles_per_cluster,
        model=model,
        article_prompt_version=args.article_prompt_version,
        cluster_prompt_version=args.cluster_prompt_version,
        mock_llm=args.mock,
    )


if __name__ == "__main__":
    main()
