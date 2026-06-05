from __future__ import annotations

from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]

ARTICLE_CONTENT_ROOT = ROOT_DIR / "public" / "data" / "article-content"
CLUSTERS_LATEST = ROOT_DIR / "public" / "data" / "clusters" / "latest"
ENRICHMENT_DATA = ROOT_DIR / "data" / "enrichment"
ENRICHMENT_PUBLIC = ROOT_DIR / "public" / "data" / "enrichment"


def normalized_articles_dir(date: str) -> Path:
    return ENRICHMENT_DATA / "normalized-articles" / date


def article_summaries_dir(date: str) -> Path:
    return ENRICHMENT_DATA / "article-summaries" / date


def cluster_summaries_dir(date: str) -> Path:
    return ENRICHMENT_DATA / "cluster-summaries" / date


def newsletters_dir() -> Path:
    return ENRICHMENT_DATA / "newsletters"


def logs_dir() -> Path:
    return ENRICHMENT_DATA / "logs"


def article_content_dir(date: str) -> Path:
    return ARTICLE_CONTENT_ROOT / date / "articles"
