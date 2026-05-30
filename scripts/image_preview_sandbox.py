#!/usr/bin/env python3
"""Sandbox MVP for testing real news preview images.

This script is intentionally separate from the production collector. It reads
the current static payload, fetches a small number of original article pages,
extracts public preview images from Open Graph/Twitter metadata, and shows how
cluster and bucket-level images could be derived from article.imageUrl.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT_DIR / "public/data/latest.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.6",
}

META_PRIORITY = (
    ("property", "og:image:secure_url"),
    ("property", "og:image:url"),
    ("property", "og:image"),
    ("name", "twitter:image"),
    ("name", "twitter:image:src"),
)

BUCKET_ORDER = ("left", "centerLeft", "center", "centerRight", "right", "unknown")


@dataclass
class PreviewResult:
    image_url: str | None
    source: str
    error: str | None = None


def attrs_from_tag(tag: str) -> dict[str, str]:
    attrs: dict[str, str] = {}
    for match in re.finditer(r"""([:\w-]+)\s*=\s*(['"])(.*?)\2""", tag, re.I | re.S):
        attrs[match.group(1).lower()] = html.unescape(match.group(3)).strip()
    return attrs


def normalize_image_url(raw_url: str, base_url: str) -> str | None:
    candidate = html.unescape(raw_url or "").strip()
    if not candidate:
        return None
    if candidate.startswith("//"):
        candidate = "https:" + candidate
    candidate = urljoin(base_url, candidate)
    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    lower = candidate.lower()
    if any(token in lower for token in ("favicon", "apple-touch-icon", "logo.svg", "placeholder")):
        return None
    return candidate


def preview_image_from_html(page_html: str, base_url: str) -> str | None:
    meta_tags = re.findall(r"<meta\b[^>]*>", page_html, re.I | re.S)
    parsed_tags = [attrs_from_tag(tag) for tag in meta_tags]
    for attr_name, attr_value in META_PRIORITY:
        for attrs in parsed_tags:
            if attrs.get(attr_name) == attr_value and attrs.get("content"):
                image_url = normalize_image_url(attrs["content"], base_url)
                if image_url:
                    return image_url
    return None


def fetch_open_graph_image(article_url: str, timeout: float) -> PreviewResult:
    try:
        request = Request(article_url, headers=HEADERS)
        with urlopen(request, timeout=timeout) as response:
            body = response.read()
            final_url = response.geturl()
            charset = response.headers.get_content_charset() or "utf-8"
        page_html = body.decode(charset, errors="replace")
    except Exception as exc:
        return PreviewResult(None, "open-graph", str(exc))

    image_url = preview_image_from_html(page_html, final_url)
    if not image_url:
        return PreviewResult(None, "open-graph", "no preview image metadata found")
    return PreviewResult(image_url, "open-graph")


def google_news_image_candidates(story_url: str, timeout: float, limit: int = 8) -> list[str]:
    """Collect likely Google News CDN image URLs from a story page.

    This is a debugging aid, not the final parser. If this finds useful lh3
    images, the production scraper can later map them to article rows in the
    AF_initDataCallback blobs.
    """
    try:
        request = Request(story_url, headers=HEADERS)
        with urlopen(request, timeout=timeout) as response:
            body = response.read()
            charset = response.headers.get_content_charset() or "utf-8"
    except Exception:
        return []

    text = html.unescape(body.decode(charset, errors="replace"))
    text = text.replace("\\u003d", "=").replace("\\u0026", "&").replace("\\/", "/")
    matches = re.findall(r"https://lh3\.googleusercontent\.com/[A-Za-z0-9_./=%?&;:+-]+", text)
    unique: list[str] = []
    seen = set()
    for url in matches:
        cleaned = url.rstrip("\\'\"),;]")
        if cleaned in seen:
            continue
        seen.add(cleaned)
        unique.append(cleaned)
        if len(unique) >= limit:
            break
    return unique


def first_images_by_bucket(articles: list[dict[str, Any]]) -> dict[str, str]:
    images: dict[str, str] = {}
    for article in articles:
        bucket = article.get("bucket") or "unknown"
        image_url = article.get("imageUrl")
        if bucket in BUCKET_ORDER and image_url and bucket not in images:
            images[bucket] = image_url
    return images


def choose_cluster_image(articles: list[dict[str, Any]], current_fallback: str | None) -> str | None:
    for article in articles:
        image_url = article.get("imageUrl")
        if image_url and article.get("bucket") != "unknown":
            return image_url
    for article in articles:
        image_url = article.get("imageUrl")
        if image_url:
            return image_url
    return current_fallback


def enrich_cluster_preview(cluster: dict[str, Any], articles_per_cluster: int, timeout: float) -> dict[str, Any]:
    sampled_articles = [dict(article) for article in cluster.get("articles", [])[:articles_per_cluster]]
    for article in sampled_articles:
        if article.get("imageUrl"):
            article["imageSource"] = "existing"
            continue
        result = fetch_open_graph_image(article["url"], timeout)
        article["imageUrl"] = result.image_url
        article["imageSource"] = result.source if result.image_url else "missing"
        article["imageError"] = result.error

    return {
        "clusterId": cluster.get("id"),
        "title": cluster.get("title"),
        "currentImageUrl": cluster.get("imageUrl"),
        "suggestedImageUrl": choose_cluster_image(sampled_articles, cluster.get("imageUrl")),
        "bucketImages": first_images_by_bucket(sampled_articles),
        "articlesChecked": [
            {
                "source": article.get("source"),
                "bucket": article.get("bucket"),
                "title": article.get("title"),
                "url": article.get("url"),
                "imageUrl": article.get("imageUrl"),
                "imageSource": article.get("imageSource"),
                "imageError": article.get("imageError"),
            }
            for article in sampled_articles
        ],
    }


def print_cluster_report(result: dict[str, Any], google_candidates: list[str]) -> None:
    print("\n" + "=" * 88)
    print(result["title"])
    print("-" * 88)
    print(f"Current cluster image:   {result['currentImageUrl']}")
    print(f"Suggested cluster image: {result['suggestedImageUrl']}")
    if google_candidates:
        print("Google News candidates:")
        for candidate in google_candidates[:3]:
            print(f"  - {candidate}")
    print("Bucket images:")
    if result["bucketImages"]:
        for bucket in BUCKET_ORDER:
            if bucket in result["bucketImages"]:
                print(f"  - {bucket}: {result['bucketImages'][bucket]}")
    else:
        print("  none found")
    print("Articles checked:")
    for article in result["articlesChecked"]:
        status = "FOUND" if article["imageUrl"] else "MISS"
        print(f"  [{status}] {article['bucket']} · {article['source']} · {article['title']}")
        if article["imageUrl"]:
            print(f"        {article['imageUrl']}")
        elif article.get("imageError"):
            print(f"        {article['imageError']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Sandbox MVP for real news preview images.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Path to latest.json-like payload.")
    parser.add_argument("--clusters", type=int, default=3, help="Number of clusters to sample.")
    parser.add_argument("--articles-per-cluster", type=int, default=5, help="Articles to inspect per cluster.")
    parser.add_argument("--timeout", type=float, default=7.0, help="HTTP timeout per article request.")
    parser.add_argument("--output", type=Path, default=Path("/Users/wittmannf/repos/gnewsbr/scripts/results.json"), help="Optional path for JSON demo output.")
    parser.add_argument("--skip-google-news-scan", action="store_true", help="Skip broad Google News image URL scan.")
    args = parser.parse_args()

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    clusters = payload.get("clusters", [])[:args.clusters]
    results = []

    print(f"Loaded {len(payload.get('clusters', []))} clusters from {args.input}")
    print(f"Sampling {len(clusters)} clusters x {args.articles_per_cluster} articles")

    for cluster in clusters:
        result = enrich_cluster_preview(cluster, args.articles_per_cluster, args.timeout)
        google_candidates = []
        if not args.skip_google_news_scan and cluster.get("storyUrl"):
            google_candidates = google_news_image_candidates(cluster["storyUrl"], args.timeout)
        result["googleNewsImageCandidates"] = google_candidates
        results.append(result)
        print_cluster_report(result, google_candidates)

    found_articles = sum(
        1
        for result in results
        for article in result["articlesChecked"]
        if article.get("imageUrl")
    )
    checked_articles = sum(len(result["articlesChecked"]) for result in results)
    real_cluster_images = sum(
        1
        for result in results
        if result["suggestedImageUrl"] and result["suggestedImageUrl"] != result["currentImageUrl"]
    )
    print("\nSummary")
    print(f"- Article preview images found: {found_articles}/{checked_articles}")
    print(f"- Clusters with a real image suggestion replacing fallback: {real_cluster_images}/{len(results)}")

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"- Wrote demo JSON: {args.output}")

    return 0 if found_articles else 2


if __name__ == "__main__":
    raise SystemExit(main())
