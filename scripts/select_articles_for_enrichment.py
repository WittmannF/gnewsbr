#!/usr/bin/env python3
"""Select top clusters and up to N articles per cluster for LLM enrichment."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR / "scripts"))

from enrichment.paths import (
    CLUSTERS_LATEST,
    normalized_articles_dir,
)
from enrichment.schemas import NormalizedArticle

MIN_WORD_COUNT = 250


def _cluster_score(articles: list[NormalizedArticle]) -> float:
    valid = [a for a in articles if a.quality.status == "ok" and a.cleanWordCount >= MIN_WORD_COUNT]
    domains = {a.sourceDomain for a in valid if a.sourceDomain}
    buckets = {a.bucket for a in valid if a.bucket and a.bucket != "unknown"}
    known_buckets = len([a for a in valid if a.bucket and a.bucket != "unknown"])
    return (
        len(valid) * 1.0
        + len(domains) * 1.0
        + len(buckets) * 2.0
        + known_buckets * 0.5
    )


def _select_articles(articles: list[NormalizedArticle], max_per_cluster: int) -> list[NormalizedArticle]:
    """Select up to max_per_cluster articles, prioritizing domain and bucket diversity."""
    valid = [a for a in articles if a.quality.status == "ok" and a.cleanWordCount >= MIN_WORD_COUNT]
    valid.sort(key=lambda a: (a.articleRank if a.articleRank is not None else 999))

    selected: list[NormalizedArticle] = []
    used_domains: set[str] = set()
    used_buckets: set[str] = set()

    # First pass: one article per domain, prefer diverse buckets
    for article in valid:
        if len(selected) >= max_per_cluster:
            break
        domain = article.sourceDomain or ""
        bucket = article.bucket or "unknown"
        if domain not in used_domains:
            selected.append(article)
            used_domains.add(domain)
            used_buckets.add(bucket)

    # Second pass: fill remaining slots with best remaining
    for article in valid:
        if len(selected) >= max_per_cluster:
            break
        if article not in selected:
            selected.append(article)

    return selected


def select(
    normalized_dir: Path,
    clusters_dir: Path,
    max_clusters: int,
    articles_per_cluster: int,
) -> dict:
    # Load all normalized articles grouped by cluster
    cluster_map: dict[str, list[NormalizedArticle]] = {}
    for path in normalized_dir.glob("*.json"):
        try:
            article = NormalizedArticle.model_validate_json(path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  SKIP {path.name}: {e}", file=sys.stderr)
            continue
        cluster_map.setdefault(article.clusterId, []).append(article)

    # Score clusters
    scored = sorted(
        cluster_map.items(),
        key=lambda kv: _cluster_score(kv[1]),
        reverse=True,
    )
    top = scored[:max_clusters]

    result: dict = {"clusters": []}
    for cluster_id, articles in top:
        selected = _select_articles(articles, articles_per_cluster)

        # Try to load cluster metadata
        cluster_meta: dict = {}
        cluster_file = clusters_dir / f"{cluster_id}.json"
        if cluster_file.exists():
            try:
                cluster_meta = json.loads(cluster_file.read_text(encoding="utf-8"))
            except Exception:
                pass

        result["clusters"].append({
            "clusterId": cluster_id,
            "clusterTitle": cluster_meta.get("title", ""),
            "clusterTopic": cluster_meta.get("topic", ""),
            "score": _cluster_score(articles),
            "selectedArticles": [a.archiveId for a in selected],
            "articleCount": len(selected),
        })

    print(f"Selected {len(result['clusters'])} clusters")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Select top articles for LLM enrichment")
    parser.add_argument("--date", default=None)
    parser.add_argument("--normalized-articles-dir", default=None)
    parser.add_argument("--clusters-dir", default=None)
    parser.add_argument("--output", default=None)
    parser.add_argument("--max-clusters", type=int, default=20)
    parser.add_argument("--articles-per-cluster", type=int, default=5)
    args = parser.parse_args()

    from datetime import datetime, timezone
    date = args.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    norm_dir = Path(args.normalized_articles_dir) if args.normalized_articles_dir else normalized_articles_dir(date)
    clusters_dir = Path(args.clusters_dir) if args.clusters_dir else CLUSTERS_LATEST

    from enrichment.paths import ENRICHMENT_DATA
    default_output = ENRICHMENT_DATA / "selected-articles" / f"{date}.json"
    output = Path(args.output) if args.output else default_output
    output.parent.mkdir(parents=True, exist_ok=True)

    result = select(norm_dir, clusters_dir, args.max_clusters, args.articles_per_cluster)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved to {output}")


if __name__ == "__main__":
    main()
