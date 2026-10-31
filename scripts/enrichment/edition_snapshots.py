"""Keep a small, factual cluster snapshot beside the generated news index.

The live Google News ranking changes hourly. An edition must not lose its
original image, source headlines or editorial metrics when a story drops out.
No article body is copied to the published index.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUCKETS = ("left", "centerLeft", "center", "centerRight", "right", "unknown")


def _load(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _real_cluster(value: dict, cluster_id: str) -> bool:
    return (
        value.get("id") == cluster_id
        and isinstance(value.get("articles"), list)
        and isinstance(value.get("spectrum"), dict)
        and isinstance(value.get("scores"), dict)
    )


def _from_archive(cluster_id: str, date: str, root: Path) -> dict:
    paths = [
        root / "public/data/archive" / date / f"{cluster_id}.json",
        root / "public/data/clusters/latest" / f"{cluster_id}.json",
    ]
    # A prior day's archive may still contain the cluster.
    paths += sorted(
        (root / "public/data/archive").glob(f"*/{cluster_id}.json"),
        reverse=True,
    )
    for path in paths:
        cluster = _load(path)
        if _real_cluster(cluster, cluster_id):
            # Allow only public metadata, never third-party article body text.
            return {
                key: cluster[key]
                for key in (
                    "id", "storyUrl", "title", "summary", "topic",
                    "topicKeywords", "imageUrl", "publishedAt", "updatedAt",
                    "sourceCount", "articleCount", "topSources", "articles",
                    "spectrum", "scores", "flags",
                )
                if key in cluster
            }
    return {}


def _from_article_archive(cluster_id: str, news: dict, date: str, root: Path) -> dict:
    meta = _load(root / "public/data/article-content" / date / "index.json")
    archived = next((c for c in meta.get("clusters", []) if c.get("id") == cluster_id), None)
    if not archived:
        return {}
    articles = []
    buckets = dict.fromkeys(BUCKETS, 0)
    for item in archived.get("articles", []):
        if not item.get("url"):
            continue
        bucket = item.get("bucket", "unknown")
        if bucket not in buckets:
            bucket = "unknown"
        buckets[bucket] += 1
        articles.append({
            "id": item.get("archiveId", ""),
            "title": item.get("title", ""),
            "description": "",
            "url": item["url"],
            "source": item.get("source", "Fonte original"),
            "publishedAt": item.get("publishedAt") or "",
            "postedLabel": "",
            "bucket": bucket,
        })
    if not articles:
        return {}
    known_count = sum(n for key, n in buckets.items() if key != "unknown")
    published_at = max((a["publishedAt"] for a in articles), default="")
    sources = list(dict.fromkeys(a["source"] for a in articles))
    return {
        "id": cluster_id,
        "storyUrl": archived.get("storyUrl") or articles[0]["url"],
        "title": archived.get("title") or news["headline"],
        "summary": news["subtitle"],
        "topic": "Cobertura arquivada",
        "topicKeywords": [],
        # No photo is available in this compact extraction archive; never invent it.
        "imageUrl": "",
        "publishedAt": published_at,
        "updatedAt": news.get("generatedAt", published_at),
        "sourceCount": len(sources),
        "articleCount": len(articles),
        "topSources": sources[:5],
        "articles": articles,
        "spectrum": {
            "knownCount": known_count,
            "unknownCount": buckets["unknown"],
            "buckets": buckets,
        },
        # These are the recorded archive scores, not re-estimated values.
        "scores": archived.get("scores", {}),
        "flags": [],
    }


def snapshot_for_story(cluster_id: str, news: dict, date: str, root: Path = ROOT) -> dict:
    """Prefer the real original cluster; otherwise use recorded archive metadata."""
    return _from_archive(cluster_id, date, root) or _from_article_archive(cluster_id, news, date, root)


def index_story_entry(payload: dict, existing: dict | None = None, root: Path = ROOT) -> dict:
    """Stable snapshot across index rebuilds, including later hourly refreshes."""
    news = payload["news"]
    cluster_id = payload["clusterId"]
    date = payload["generatedAt"][:10]
    snapshot = (existing or {}).get("clusterSnapshot") or snapshot_for_story(cluster_id, {
        **news, "generatedAt": payload["generatedAt"],
    }, date, root)
    entry = {
        "headline": news["headline"],
        "subtitle": news["subtitle"],
        "generatedAt": payload["generatedAt"],
        "sourceCount": len(payload.get("sourceArticles", [])),
        "sources": [
            {"source": article["source"], "url": article["url"], "articleId": article["articleId"]}
            for article in payload.get("sourceArticles", []) if article.get("url")
        ],
    }
    if snapshot:
        entry["clusterSnapshot"] = snapshot
    return entry
