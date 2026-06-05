#!/usr/bin/env python3
"""Archive clean text for the most relevant original articles in daily GNewsBR clusters.

The collector intentionally stores *clean text + metadata*, not raw HTML. It is designed
as a prerequisite for editorial newsletters and richer cluster summaries that should be
based on original article content rather than only Google News metadata.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import html
import json
import re
import sys
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_ARCHIVE_ROOT = ROOT_DIR / "public" / "data" / "archive"
DEFAULT_OUTPUT_ROOT = ROOT_DIR / "public" / "data" / "article-content"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36 GNewsBRBot/0.1",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.6",
}
PRIMARY_SEED_PAGES = {"home", "topstories"}
SKIP_TAGS = {"script", "style", "noscript", "svg", "canvas", "template", "nav", "footer", "header", "aside"}
TEXT_BLOCK_TAGS = {"p", "h1", "h2", "h3", "li", "blockquote", "article", "section", "br"}


class CleanTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_stack: list[str] = []
        self._parts: list[str] = []
        self.title_parts: list[str] = []
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in SKIP_TAGS:
            self._skip_stack.append(tag)
            return
        if tag == "title":
            self._in_title = True
        if not self._skip_stack and tag in TEXT_BLOCK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self._skip_stack and self._skip_stack[-1] == tag:
            self._skip_stack.pop()
            return
        if tag == "title":
            self._in_title = False
        if not self._skip_stack and tag in TEXT_BLOCK_TAGS:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_stack:
            return
        text = data.strip()
        if not text:
            return
        if self._in_title:
            self.title_parts.append(text)
        self._parts.append(text)
        self._parts.append(" ")

    def text(self) -> str:
        return normalize_text("".join(self._parts))

    def title(self) -> str | None:
        title = normalize_text(" ".join(self.title_parts))
        return title or None


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_id(value: str, prefix: str = "article") -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def normalize_text(text: str) -> str:
    text = html.unescape(text or "")
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def word_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text or "", re.UNICODE))


def article_domain(article: dict[str, Any]) -> str:
    if article.get("sourceDomain"):
        return str(article["sourceDomain"]).lower()
    parsed = urlparse(str(article.get("url", "")))
    return parsed.netloc.replace("www.", "").lower()


def cluster_seed_pages(cluster: dict[str, Any]) -> set[str]:
    pages = cluster.get("seedPages") or cluster.get("discovery", {}).get("seedPages") or []
    return {str(page) for page in pages}


def cluster_score(cluster: dict[str, Any]) -> tuple[int, int, float, int]:
    pages = cluster_seed_pages(cluster)
    primary_rank = 1 if pages & PRIMARY_SEED_PAGES else 0
    discovery = cluster.get("discovery") or {}
    best_seed_rank = discovery.get("bestSeedRank")
    # Lower Google News page rank is better; use a reverse-sort-friendly score.
    rank_score = 0
    if isinstance(best_seed_rank, (int, float)):
        rank_score = max(0, 10_000 - int(best_seed_rank))
    scores = cluster.get("scores") or {}
    confidence = float(scores.get("confidence") or 0)
    diversity = float(scores.get("coverageDiversity") or 0)
    headline = float(scores.get("headlineDivergence") or 0)
    article_count = int(cluster.get("articleCount") or len(cluster.get("articles") or []))
    internal = confidence * 2 + diversity + headline * 0.5 + min(article_count, 20)
    return (primary_rank, rank_score, internal, article_count)


def select_clusters_for_archive(clusters: list[dict[str, Any]], max_clusters: int = 20) -> list[dict[str, Any]]:
    eligible = [cluster for cluster in clusters if cluster.get("articles")]
    return sorted(eligible, key=cluster_score, reverse=True)[:max_clusters]


def select_articles_for_cluster(cluster: dict[str, Any], min_articles: int = 5, max_articles: int = 8) -> list[dict[str, Any]]:
    articles = [article for article in cluster.get("articles", []) if article.get("url")]
    unique: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for article in articles:
        url = str(article.get("url"))
        if url in seen_urls:
            continue
        seen_urls.add(url)
        unique.append(article)

    selected: list[dict[str, Any]] = []
    seen_domains: set[str] = set()
    seen_sources: set[str] = set()
    seen_buckets: set[str] = set()

    def add(article: dict[str, Any]) -> bool:
        if any(existing.get("url") == article.get("url") for existing in selected):
            return False
        selected.append(article)
        seen_domains.add(article_domain(article))
        if article.get("source"):
            seen_sources.add(str(article["source"]))
        if article.get("bucket"):
            seen_buckets.add(str(article["bucket"]))
        return True

    # First pass: maximize source/domain/editorial diversity.
    for article in unique:
        domain = article_domain(article)
        source = str(article.get("source") or "")
        bucket = str(article.get("bucket") or "")
        if domain not in seen_domains or source not in seen_sources or bucket not in seen_buckets:
            add(article)
        if len(selected) >= max_articles:
            return selected

    # Second pass: satisfy minimum when possible, preserving the original upstream order.
    for article in unique:
        add(article)
        if len(selected) >= min(min_articles, max_articles, len(unique)):
            break

    # Optional fill up to max_articles; more depth can help editorial synthesis.
    for article in unique:
        add(article)
        if len(selected) >= min(max_articles, len(unique)):
            break

    return selected


def parse_html_text(page_html: str) -> tuple[str, str | None]:
    parser = CleanTextParser()
    parser.feed(page_html)
    return parser.text(), parser.title()


async def extract_with_crawl4ai(url: str) -> dict[str, Any] | None:
    try:
        from crawl4ai import AsyncWebCrawler  # type: ignore
    except Exception:
        return None

    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(url=url)
        text = normalize_text(getattr(result, "markdown", None) or getattr(result, "cleaned_html", None) or "")
        if not text:
            return None
        return {
            "status": "ok",
            "method": "crawl4ai",
            "resolvedUrl": url,
            "title": None,
            "text": text,
            "wordCount": word_count(text),
            "fetchedAt": now_iso(),
        }


def extract_article(url: str, timeout: float = 15.0, enable_crawl4ai: bool = False, min_words: int = 80) -> dict[str, Any]:
    fetched_at = now_iso()
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "")
        if "html" not in content_type and resp.text.lstrip()[:1] != "<":
            return {
                "status": "unsupported_content_type",
                "method": "light-html",
                "resolvedUrl": resp.url,
                "contentType": content_type,
                "text": "",
                "wordCount": 0,
                "fetchedAt": fetched_at,
            }
        text, title = parse_html_text(resp.text)
        words = word_count(text)
        if enable_crawl4ai and words < min_words:
            try:
                fallback = asyncio.run(extract_with_crawl4ai(resp.url))
                if fallback and fallback.get("wordCount", 0) > words:
                    return fallback
            except Exception as exc:
                return {
                    "status": "partial",
                    "method": "light-html",
                    "resolvedUrl": resp.url,
                    "title": title,
                    "text": text,
                    "wordCount": words,
                    "fetchedAt": fetched_at,
                    "fallbackError": str(exc),
                }
        return {
            "status": "ok" if words else "empty",
            "method": "light-html",
            "resolvedUrl": resp.url,
            "title": title,
            "contentType": content_type,
            "text": text,
            "wordCount": words,
            "fetchedAt": fetched_at,
        }
    except Exception as exc:
        return {
            "status": "error",
            "method": "light-html",
            "resolvedUrl": url,
            "text": "",
            "wordCount": 0,
            "fetchedAt": fetched_at,
            "error": str(exc),
        }


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_public_data_path(detail_path: str) -> Path:
    if detail_path.startswith("data/"):
        return ROOT_DIR / "public" / detail_path
    return ROOT_DIR / detail_path


def load_archive_clusters(archive_root: Path, date_key: str) -> list[dict[str, Any]]:
    day_dir = archive_root / date_key
    index_path = day_dir / "index.json"
    if not index_path.exists():
        raise SystemExit(f"Archive index not found: {index_path}")
    index = load_json(index_path)
    clusters: list[dict[str, Any]] = []
    for summary in index.get("clusters", []):
        detail_path = summary.get("detailPath")
        if detail_path:
            path = resolve_public_data_path(str(detail_path))
        else:
            path = day_dir / f"{summary['id']}.json"
        if not path.exists():
            print(f"WARN missing cluster detail {path}", file=sys.stderr)
            continue
        cluster = load_json(path)
        # Preserve rank/discovery fields from the summary if an older detail lacks them.
        for key in ("seedPages", "discovery", "scores"):
            if key in summary and key not in cluster:
                cluster[key] = summary[key]
        clusters.append(cluster)
    return clusters


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def article_archive_record(
    cluster: dict[str, Any],
    article: dict[str, Any],
    extracted: dict[str, Any],
    archive_id: str,
) -> dict[str, Any]:
    return {
        "archiveId": archive_id,
        "clusterId": cluster.get("id"),
        "article": {
            "id": article.get("id"),
            "title": article.get("title"),
            "description": article.get("description"),
            "url": article.get("url"),
            "source": article.get("source"),
            "sourceCanonical": article.get("sourceCanonical"),
            "sourceDomain": article.get("sourceDomain") or article_domain(article),
            "bucket": article.get("bucket"),
            "publishedAt": article.get("publishedAt"),
        },
        "extraction": {key: value for key, value in extracted.items() if key != "text"},
        "content": {
            "text": extracted.get("text", ""),
            "wordCount": extracted.get("wordCount", 0),
        },
    }


def write_article_archive(
    out_dir: Path,
    date_key: str,
    selected_clusters: list[dict[str, Any]],
    selected_articles_by_cluster: dict[str, list[dict[str, Any]]],
    extracted_by_url: dict[str, dict[str, Any]],
    generated_at: str,
) -> None:
    day_dir = out_dir / date_key
    articles_dir = day_dir / "articles"
    clusters_dir = day_dir / "clusters"
    day_dir.mkdir(parents=True, exist_ok=True)
    articles_dir.mkdir(parents=True, exist_ok=True)
    clusters_dir.mkdir(parents=True, exist_ok=True)

    index_clusters: list[dict[str, Any]] = []
    stats = {
        "clusterCount": len(selected_clusters),
        "articleCount": 0,
        "okArticleCount": 0,
        "errorArticleCount": 0,
    }

    for cluster_rank, cluster in enumerate(selected_clusters, start=1):
        cluster_id = str(cluster["id"])
        selected_articles = selected_articles_by_cluster.get(cluster_id, [])
        cluster_articles: list[dict[str, Any]] = []
        for article_rank, article in enumerate(selected_articles, start=1):
            url = str(article["url"])
            archive_id = stable_id(url)
            extracted = extracted_by_url.get(url, {"status": "not_fetched", "text": "", "wordCount": 0, "fetchedAt": generated_at})
            record = article_archive_record(cluster, article, extracted, archive_id)
            record["articleRank"] = article_rank
            write_json(articles_dir / archive_id / "content.json", record)
            status = str(extracted.get("status") or "unknown")
            stats["articleCount"] += 1
            if status == "ok" or status == "partial":
                stats["okArticleCount"] += 1
            else:
                stats["errorArticleCount"] += 1
            cluster_articles.append(
                {
                    "archiveId": archive_id,
                    "path": f"data/article-content/{date_key}/articles/{archive_id}/content.json",
                    "title": article.get("title"),
                    "url": url,
                    "source": article.get("source"),
                    "sourceDomain": article.get("sourceDomain") or article_domain(article),
                    "bucket": article.get("bucket"),
                    "publishedAt": article.get("publishedAt"),
                    "status": status,
                    "method": extracted.get("method"),
                    "wordCount": extracted.get("wordCount", 0),
                }
            )

        cluster_payload = {
            "id": cluster_id,
            "rank": cluster_rank,
            "title": cluster.get("title"),
            "summary": cluster.get("summary"),
            "storyUrl": cluster.get("storyUrl"),
            "seedPages": sorted(cluster_seed_pages(cluster)),
            "scores": cluster.get("scores", {}),
            "selectedArticleCount": len(cluster_articles),
            "articles": cluster_articles,
        }
        write_json(clusters_dir / f"{cluster_id}.json", cluster_payload)
        index_clusters.append(
            {
                "id": cluster_id,
                "rank": cluster_rank,
                "title": cluster.get("title"),
                "detailPath": f"data/article-content/{date_key}/clusters/{cluster_id}.json",
                "sourceClusterPath": f"data/archive/{date_key}/{cluster_id}.json",
                "seedPages": sorted(cluster_seed_pages(cluster)),
                "scores": cluster.get("scores", {}),
                "selectedArticleCount": len(cluster_articles),
                "okArticleCount": sum(1 for item in cluster_articles if item["status"] in {"ok", "partial"}),
                "articles": cluster_articles,
            }
        )

    index_payload = {
        "generatedAt": generated_at,
        "date": date_key,
        "version": "article-content-archive-v1",
        "source": "GNewsBR daily cluster archive",
        "policy": {
            "maxClustersPerDay": 20,
            "minArticlesPerClusterWhenAvailable": 5,
            "maxArticlesPerCluster": 8,
            "storesRawHtml": False,
        },
        "stats": stats,
        "clusters": index_clusters,
    }
    write_json(day_dir / "index.json", index_payload)


def run_archive(
    date_key: str,
    archive_root: Path = DEFAULT_ARCHIVE_ROOT,
    out_dir: Path = DEFAULT_OUTPUT_ROOT,
    max_clusters: int = 20,
    min_articles_per_cluster: int = 5,
    max_articles_per_cluster: int = 8,
    timeout: float = 15.0,
    sleep: float = 0.2,
    enable_crawl4ai: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    clusters = load_archive_clusters(archive_root, date_key)
    selected_clusters = select_clusters_for_archive(clusters, max_clusters=max_clusters)
    selected_articles_by_cluster = {
        str(cluster["id"]): select_articles_for_cluster(cluster, min_articles=min_articles_per_cluster, max_articles=max_articles_per_cluster)
        for cluster in selected_clusters
    }
    extracted_by_url: dict[str, dict[str, Any]] = {}
    urls = []
    for articles in selected_articles_by_cluster.values():
        for article in articles:
            url = str(article["url"])
            if url not in extracted_by_url:
                urls.append(url)

    if not dry_run:
        for idx, url in enumerate(urls, start=1):
            print(f"[{idx}/{len(urls)}] fetching {url}")
            extracted_by_url[url] = extract_article(url, timeout=timeout, enable_crawl4ai=enable_crawl4ai)
            if sleep:
                time.sleep(sleep)
        write_article_archive(out_dir, date_key, selected_clusters, selected_articles_by_cluster, extracted_by_url, now_iso())

    return {
        "date": date_key,
        "selectedClusterCount": len(selected_clusters),
        "selectedArticleCount": sum(len(items) for items in selected_articles_by_cluster.values()),
        "outputDir": str(out_dir / date_key),
        "dryRun": dry_run,
    }


def default_date_key() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def main() -> int:
    parser = argparse.ArgumentParser(description="Archive clean article content for daily GNewsBR clusters")
    parser.add_argument("--date", default=default_date_key(), help="Archive date key, e.g. 2026-06-05")
    parser.add_argument("--archive-root", type=Path, default=DEFAULT_ARCHIVE_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--max-clusters", type=int, default=20)
    parser.add_argument("--min-articles-per-cluster", type=int, default=5)
    parser.add_argument("--max-articles-per-cluster", type=int, default=8)
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--sleep", type=float, default=0.2)
    parser.add_argument("--enable-crawl4ai-fallback", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    result = run_archive(
        date_key=args.date,
        archive_root=args.archive_root,
        out_dir=args.output_root,
        max_clusters=args.max_clusters,
        min_articles_per_cluster=args.min_articles_per_cluster,
        max_articles_per_cluster=args.max_articles_per_cluster,
        timeout=args.timeout,
        sleep=args.sleep,
        enable_crawl4ai=args.enable_crawl4ai_fallback,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
