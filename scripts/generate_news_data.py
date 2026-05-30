#!/usr/bin/env python3
"""Generate GNewsBR static JSON from collected news stories.

This intentionally starts from the reference script Fernando provided:
- discover /stories/<id> links from news index pages;
- open each story page;
- parse AF_initDataCallback JSON;
- extract article-like arrays with title/description/time/url/source;
- enrich sources with the manual 1-10 editorial spectrum map;
- export a frontend-friendly camelCase JSON payload.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import shutil
import statistics
import sys
import time
from collections import Counter, OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse

import requests
import yaml

ROOT_DIR = Path(__file__).resolve().parents[1]
SOURCE_SPECTRUM_PATH = ROOT_DIR / "data/sources/source-spectrum.yml"
SOURCE_ALIASES_PATH = ROOT_DIR / "data/sources/source-aliases.yml"

GOOGLE_NEWS_BASE = "https://news.google.com"
COMMON_PARAMS = "hl=pt-BR&gl=BR&ceid=BR:pt-419"
STORY_URL_TEMPLATE = GOOGLE_NEWS_BASE + "/stories/{}?ceid=BR:pt-419&oc=3&hl=pt-BR&gl=BR"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.6",
}

def load_source_config() -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    """Load the reviewable source spectrum and alias files."""
    spectrum_doc = yaml.safe_load(SOURCE_SPECTRUM_PATH.read_text(encoding="utf-8")) or {}
    aliases_doc = yaml.safe_load(SOURCE_ALIASES_PATH.read_text(encoding="utf-8")) or {}
    records = {item["name"]: item for item in spectrum_doc.get("sources", [])}
    aliases = aliases_doc.get("aliases", {}) or {}
    return records, aliases


NEWS_SOURCE_CONFIG, SOURCE_ALIASES = load_source_config()
NEWS_POLITICAL_SPECTRUM = {
    name: int(config["spectrum_score"])
    for name, config in NEWS_SOURCE_CONFIG.items()
}

STOPWORDS = set("""
a o os as um uma uns umas de da do das dos em no na nos nas para por com sem sobre entre
que quem qual quais quando onde como mais menos ao aos à às e ou mas se seu sua seus suas
é foi são ser está estão após antes contra diz disse afirma segundo veja novo nova hoje ontem
brasil brasileira brasileiro governo ano anos dia dias hora horas
""".split())

FALLBACK_IMAGES = [
    "https://images.unsplash.com/photo-1504711434969-e33886168f5c?auto=format&fit=crop&w=1200&q=80",
    "https://images.unsplash.com/photo-1495020689067-958852a7765e?auto=format&fit=crop&w=1200&q=80",
    "https://images.unsplash.com/photo-1529107386315-e1a2ed48a620?auto=format&fit=crop&w=1200&q=80",
    "https://images.unsplash.com/photo-1585829365295-ab7cd400c167?auto=format&fit=crop&w=1200&q=80",
]

PREVIEW_IMAGE_META_PRIORITY = (
    ("property", "og:image:secure_url"),
    ("property", "og:image:url"),
    ("property", "og:image"),
    ("name", "twitter:image"),
    ("name", "twitter:image:src"),
)


def fetch(url: str, timeout: int = 25) -> str:
    resp = requests.get(url, headers=HEADERS, timeout=timeout)
    resp.raise_for_status()
    return resp.text


def tag_attrs(tag: str) -> dict[str, str]:
    attrs: dict[str, str] = {}
    for match in re.finditer(r"""([:\w-]+)\s*=\s*(['"])(.*?)\2""", tag, re.I | re.S):
        attrs[match.group(1).lower()] = html.unescape(match.group(3)).strip()
    return attrs


def normalize_preview_image_url(raw_url: str | None, base_url: str) -> str | None:
    if not raw_url:
        return None
    candidate = html.unescape(raw_url).strip()
    if not candidate:
        return None
    if candidate.startswith("//"):
        candidate = "https:" + candidate
    candidate = urljoin(base_url, candidate)
    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None

    lower = candidate.lower()
    rejected_tokens = ("favicon", "apple-touch-icon", "logo.svg", "placeholder")
    if any(token in lower for token in rejected_tokens):
        return None
    return candidate


def preview_image_from_html(page_html: str, base_url: str) -> str | None:
    parsed_tags = [tag_attrs(tag) for tag in re.findall(r"<meta\b[^>]*>", page_html, re.I | re.S)]
    for attr_name, attr_value in PREVIEW_IMAGE_META_PRIORITY:
        for attrs in parsed_tags:
            if attrs.get(attr_name) == attr_value:
                image_url = normalize_preview_image_url(attrs.get("content"), base_url)
                if image_url:
                    return image_url
    return None


def fetch_preview_image(article_url: str, timeout: float) -> str | None:
    resp = requests.get(article_url, headers=HEADERS, timeout=timeout)
    resp.raise_for_status()
    return preview_image_from_html(resp.text, resp.url)


def story_id_from_url(url: str) -> str | None:
    parsed = urlparse(url)
    if "/stories/" not in parsed.path:
        return None
    sid = parsed.path.rsplit("/stories/", 1)[-1].strip("/")
    return sid if len(sid) > 20 else None


def discover_seed_pages() -> list[tuple[str, str]]:
    pages: list[tuple[str, str]] = [
        ("home", f"{GOOGLE_NEWS_BASE}/home?{COMMON_PARAMS}"),
        ("topstories", f"{GOOGLE_NEWS_BASE}/topstories?{COMMON_PARAMS}"),
    ]
    try:
        home = fetch(pages[0][1])
        topic_ids = sorted(set(re.findall(r'(?:\./|/)topics/([A-Za-z0-9_-]{20,})', home)))
        for idx, topic_id in enumerate(topic_ids):
            pages.append((f"topic-{idx+1}", f"{GOOGLE_NEWS_BASE}/topics/{topic_id}?{COMMON_PARAMS}"))
    except Exception as exc:
        print(f"WARN failed to discover topics: {exc}", file=sys.stderr)
    return pages


def discover_story_ids(max_seed_pages: int | None = None) -> OrderedDict[str, set[str]]:
    story_sources: OrderedDict[str, set[str]] = OrderedDict()
    seed_pages = discover_seed_pages()
    if max_seed_pages:
        seed_pages = seed_pages[:max_seed_pages]

    for label, url in seed_pages:
        try:
            html = fetch(url)
        except Exception as exc:
            print(f"WARN seed page failed {label}: {exc}", file=sys.stderr)
            continue
        ids = set(re.findall(r'(?:\./|/)stories/([A-Za-z0-9_-]{20,})', html))
        # Some upstream markup puts escaped URLs in data blobs. This catches those too.
        ids |= set(re.findall(r'stories/([A-Za-z0-9_-]{20,})\?', html))
        for sid in sorted(ids):
            story_sources.setdefault(sid, set()).add(label)
        print(f"{label}: {len(ids)} stories")
    return story_sources


def extract_json_blobs(html: str) -> list[Any]:
    blobs = []
    for script in re.findall(r"<script[^>]*>(.*?)</script>", html, re.S):
        if "AF_initDataCallback" not in script or "data:" not in script:
            continue
        try:
            payload = script.split("data:", 1)[1].rsplit(", sideChannel:", 1)[0]
            blobs.append(json.loads(payload))
        except Exception:
            continue
    return blobs


def source_name_from_article_list(row: list[Any]) -> str:
    # Observed upstream structure: row[10][2] = source name; row[36][1][0][0] = "Acessar Fonte".
    try:
        val = row[10][2]
        if isinstance(val, str) and val.strip():
            return val.strip()
    except Exception:
        pass
    try:
        val = row[36][1][0][0]
        if isinstance(val, str):
            return val.replace("Acessar ", "").strip()
    except Exception:
        pass
    return "Fonte desconhecida"


def extract_articles_from_blob(blob: Any) -> list[dict[str, Any]]:
    candidates: list[list[Any]] = []

    def walk(node: Any) -> None:
        if isinstance(node, list):
            if (
                len(node) >= 39
                and isinstance(node[2], str)
                and isinstance(node[6], str)
                and node[6].startswith("http")
                and len(node[2]) > 12
            ):
                candidates.append(node)
            for child in node:
                walk(child)
        elif isinstance(node, dict):
            for child in node.values():
                walk(child)

    walk(blob)
    articles = []
    seen_urls = set()
    for row in candidates:
        url = row[38] if len(row) > 38 and isinstance(row[38], str) and row[38].startswith("http") else row[6]
        if url in seen_urls:
            continue
        seen_urls.add(url)
        timestamp = None
        try:
            if isinstance(row[4], list) and row[4] and isinstance(row[4][0], (int, float)):
                timestamp = datetime.fromtimestamp(row[4][0], tz=timezone.utc).isoformat()
        except Exception:
            timestamp = None
        source = source_name_from_article_list(row)
        domain = urlparse(url).netloc.replace("www.", "")
        articles.append({
            "title": row[2].strip(),
            "description": row[3].strip() if isinstance(row[3], str) else "",
            "url": url,
            "source": source,
            "sourceDomain": domain,
            "publishedAt": timestamp or datetime.now(timezone.utc).isoformat(),
            "postedLabel": row[34] if len(row) > 34 and isinstance(row[34], str) else "",
        })
    return articles


def story_title_from_blobs(blobs: list[Any], articles: list[dict[str, Any]]) -> str:
    for blob in blobs:
        try:
            title = blob[2][0][2]
            if isinstance(title, str) and len(title) > 8:
                return title
        except Exception:
            pass
    return articles[0]["title"] if articles else "Story sem título"


def fallback_image_for_story(story_id: str) -> str:
    return FALLBACK_IMAGES[int(hashlib.sha1(story_id.encode()).hexdigest(), 16) % len(FALLBACK_IMAGES)]


def choose_cluster_image(articles: list[dict[str, Any]], story_id: str) -> str:
    for article in articles:
        if article.get("imageUrl") and article.get("bucket") != "unknown":
            return article["imageUrl"]
    for article in articles:
        if article.get("imageUrl"):
            return article["imageUrl"]
    return fallback_image_for_story(story_id)


def article_preview_priority(article: dict[str, Any], index: int) -> tuple[int, int]:
    score = source_score(article.get("source", ""))
    bucket = score_to_bucket(score)
    return (0 if bucket != "unknown" else 1, index)


def enrich_article_preview_images(
    articles: list[dict[str, Any]],
    max_fetches: int,
    timeout: float,
    stats: Counter[str] | None = None,
) -> None:
    if max_fetches <= 0:
        return

    attempts = 0
    prioritized = sorted(enumerate(articles), key=lambda item: article_preview_priority(item[1], item[0]))
    for _, article in prioritized:
        if attempts >= max_fetches:
            break
        if article.get("imageUrl"):
            if stats is not None:
                stats["article_images_existing"] += 1
            continue

        attempts += 1
        if stats is not None:
            stats["preview_fetch_attempts"] += 1
        try:
            image_url = fetch_preview_image(article["url"], timeout)
        except Exception:
            if stats is not None:
                stats["preview_fetch_failed"] += 1
            continue
        if image_url:
            article["imageUrl"] = image_url
            if stats is not None:
                stats["article_images_open_graph"] += 1
        elif stats is not None:
            stats["preview_fetch_missing"] += 1


def extract_topic_keywords(titles: list[str], top_n: int = 6) -> list[str]:
    words = []
    for title in titles:
        for raw in re.findall(r"[A-Za-zÀ-ÿ0-9]{3,}", title.lower()):
            if raw not in STOPWORDS and not raw.isdigit():
                words.append(raw)
    return [w for w, _ in Counter(words).most_common(top_n)]


def score_to_bucket(score: int | None) -> str:
    if score is None:
        return "unknown"
    if score <= 2:
        return "left"
    if score <= 4:
        return "centerLeft"
    if score <= 6:
        return "center"
    if score <= 8:
        return "centerRight"
    return "right"


def canonical_source_name(source: str) -> str:
    source_clean = source.strip()
    if source_clean in SOURCE_ALIASES:
        return SOURCE_ALIASES[source_clean]
    normalized = source_clean.lower()
    for alias, canonical in SOURCE_ALIASES.items():
        if alias.strip().lower() == normalized:
            return canonical
    for name in NEWS_SOURCE_CONFIG:
        if name.strip().lower() == normalized:
            return name
    return source_clean


def source_score(source: str) -> int | None:
    canonical = canonical_source_name(source)
    if canonical in NEWS_POLITICAL_SPECTRUM:
        return NEWS_POLITICAL_SPECTRUM[canonical]
    return None


def article_id(url: str) -> str:
    return "article_" + hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]


def cluster_id(story_id: str) -> str:
    """Create a stable unique cluster id from the full upstream story id.

    Upstream story ids share a long common prefix, so truncating the raw id
    creates duplicate React keys and can make distinct cards render as repeats.
    """
    return "story_" + hashlib.sha1(story_id.encode("utf-8")).hexdigest()[:12]


def cluster_article_urls(cluster: dict[str, Any]) -> set[str]:
    return {article.get("url") for article in cluster.get("articles", []) if article.get("url")}


def cluster_overlap_ratio(first: dict[str, Any], second: dict[str, Any]) -> float:
    first_urls = cluster_article_urls(first)
    second_urls = cluster_article_urls(second)
    if not first_urls or not second_urls:
        return 0.0
    return len(first_urls & second_urls) / min(len(first_urls), len(second_urls))


def cluster_completeness_key(cluster: dict[str, Any]) -> tuple[int, int, int]:
    articles = cluster.get("articles", [])
    return (
        int(cluster.get("articleCount") or len(articles)),
        int(cluster.get("sourceCount") or len({article.get("source") for article in articles if article.get("source")})),
        int((cluster.get("spectrum") or {}).get("knownCount") or 0),
    )


def normalized_cluster_title(cluster: dict[str, Any]) -> str:
    title = str(cluster.get("title") or "").strip().lower()
    return re.sub(r"\s+", " ", title)


def dedupe_clusters(clusters: list[dict[str, Any]], overlap_threshold: float = 0.7) -> list[dict[str, Any]]:
    """Remove near-duplicate story variants.

    The upstream feed sometimes returns multiple /stories ids for the same coverage package.
    When two clusters share most article URLs, keep the more complete one. Some
    duplicate variants also arrive with identical story titles but disjoint URL
    lists, so exact normalized title matches are treated as duplicates too.
    """
    deduped: list[dict[str, Any]] = []
    seen_titles: dict[str, int] = {}
    for cluster in clusters:
        duplicate_index = None
        title_key = normalized_cluster_title(cluster)
        if title_key:
            duplicate_index = seen_titles.get(title_key)
        if duplicate_index is None:
            for idx, existing in enumerate(deduped):
                same_title = title_key and title_key == normalized_cluster_title(existing)
                high_overlap = cluster_overlap_ratio(cluster, existing) >= overlap_threshold
                if high_overlap or (same_title and cluster_overlap_ratio(cluster, existing) >= 0.5):
                    duplicate_index = idx
                    break
        if duplicate_index is None:
            deduped.append(cluster)
            if title_key:
                seen_titles[title_key] = len(deduped) - 1
            continue
        if cluster_completeness_key(cluster) > cluster_completeness_key(deduped[duplicate_index]):
            deduped[duplicate_index] = cluster
            if title_key:
                seen_titles[title_key] = duplicate_index
    return deduped


def build_cluster(
    story_id: str,
    seed_labels: set[str],
    max_articles_per_story: int,
    max_preview_image_fetches: int = 0,
    preview_image_timeout: float = 5.0,
    image_stats: Counter[str] | None = None,
) -> dict[str, Any] | None:
    url = STORY_URL_TEMPLATE.format(story_id)
    try:
        html = fetch(url)
        blobs = extract_json_blobs(html)
        articles_raw = []
        for blob in blobs:
            articles_raw.extend(extract_articles_from_blob(blob))
    except Exception as exc:
        print(f"WARN story failed {story_id}: {exc}", file=sys.stderr)
        return None

    # Dedupe while preserving order.
    deduped = []
    seen = set()
    for item in articles_raw:
        if item["url"] in seen:
            continue
        seen.add(item["url"])
        deduped.append(item)
    articles_raw = deduped[:max_articles_per_story]
    if not articles_raw:
        return None
    enrich_article_preview_images(articles_raw, max_preview_image_fetches, preview_image_timeout, image_stats)

    articles = []
    bucket_counts = {"left": 0, "centerLeft": 0, "center": 0, "centerRight": 0, "right": 0, "unknown": 0}
    scores = []
    for item in articles_raw:
        canonical_source = canonical_source_name(item["source"])
        score = source_score(item["source"])
        bucket = score_to_bucket(score)
        bucket_counts[bucket] += 1
        if score is not None:
            scores.append(score)
        articles.append({
            "id": article_id(item["url"]),
            "title": item["title"],
            "description": item["description"],
            "url": item["url"],
            "source": item["source"],
            "sourceCanonical": canonical_source,
            "sourceDomain": item.get("sourceDomain"),
            "publishedAt": item["publishedAt"],
            "postedLabel": item.get("postedLabel") or "",
            "imageUrl": item.get("imageUrl"),
            "spectrumScore": score,
            "bucket": bucket,
        })

    keywords = extract_topic_keywords([a["title"] for a in articles])
    known = len(scores)
    unknown = len(articles) - known
    represented = sum(1 for k, v in bucket_counts.items() if k != "unknown" and v > 0)
    diversity = round((represented / 5) * 100)
    spread = (max(scores) - min(scores)) if scores else 0
    balance = min(100, round((spread / 9) * 100 + represented * 8)) if scores else 0
    headline_divergence = min(100, round((len(set(keywords)) / max(1, len(keywords))) * 70 + spread * 3))
    flags = []
    if len(articles) >= 10:
        flags.append("Alta cobertura")
    if represented >= 4:
        flags.append("Ampla diversidade editorial")
    if unknown >= max(3, len(articles) // 3):
        flags.append("Muitas fontes não classificadas")
    if headline_divergence >= 65:
        flags.append("Manchetes divergentes")
    if not flags:
        flags.append("Cobertura monitorada")

    title = story_title_from_blobs(blobs, articles)
    summary = articles[0]["description"] or "Cluster extraído da coleta editorial com artigos relacionados e distribuição editorial estimada."
    source_count = len(set(a["source"] for a in articles))
    cluster_image = choose_cluster_image(articles, story_id)
    if image_stats is not None:
        image_stats["cluster_images_real" if any(a.get("imageUrl") == cluster_image for a in articles) else "cluster_images_fallback"] += 1

    return {
        "id": cluster_id(story_id),
        "storyId": story_id,
        "storyUrl": url,
        "seedPages": sorted(seed_labels),
        "title": title,
        "summary": summary,
        "topic": " · ".join(keywords[:2]).title() if keywords else "Manchetes",
        "topicKeywords": keywords,
        "imageUrl": cluster_image,
        "publishedAt": min(a["publishedAt"] for a in articles),
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "sourceCount": source_count,
        "articleCount": len(articles),
        "articles": articles,
        "spectrum": {
            "min": min(scores) if scores else None,
            "max": max(scores) if scores else None,
            "average": round(statistics.mean(scores), 2) if scores else None,
            "knownCount": known,
            "unknownCount": unknown,
            "buckets": bucket_counts,
        },
        "scores": {
            "coverageDiversity": diversity,
            "spectrumBalance": balance,
            "headlineDivergence": headline_divergence,
            "confidence": min(95, round(45 + known * 3 + min(len(articles), 15) * 2)),
        },
        "flags": flags,
    }


def build_sources() -> list[dict[str, Any]]:
    labels = {"left": "Progressista", "centerLeft": "Centro-progressista", "center": "Centro", "centerRight": "Centro-conservador", "right": "Conservador", "unknown": "Não classificado"}
    sources = []
    for name, config in sorted(NEWS_SOURCE_CONFIG.items()):
        score = int(config["spectrum_score"])
        bucket = score_to_bucket(score)
        sources.append({
            "name": name,
            "spectrumScore": score,
            "bucket": bucket,
            "label": config.get("spectrum_label") or labels[bucket],
            "confidence": config.get("confidence", "medium"),
            "region": config.get("country", "BR"),
            "type": config.get("type", "editorial"),
            "scope": config.get("scope"),
            "politicalWeight": config.get("political_weight", 1),
            "reviewStatus": config.get("review_status", "draft"),
            "rationale": config.get("rationale"),
        })
    return sources


def build_source_coverage(clusters: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    coverage: dict[str, dict[str, int]] = {}
    for cluster in clusters:
        seen_in_cluster: set[str] = set()
        for article in cluster.get("articles", []):
            source_key = article.get("sourceCanonical") or article.get("source")
            if not source_key:
                continue
            stats = coverage.setdefault(source_key, {"articles": 0, "clusters": 0})
            stats["articles"] += 1
            seen_in_cluster.add(source_key)
        for source_key in seen_in_cluster:
            coverage[source_key]["clusters"] += 1
    return coverage


def build_cluster_summary(cluster: dict[str, Any], detail_path: str) -> dict[str, Any]:
    unique_sources: list[str] = []
    seen_sources: set[str] = set()
    for article in cluster.get("articles", []):
        source = article.get("source")
        if not source or source in seen_sources:
            continue
        seen_sources.add(source)
        unique_sources.append(source)
        if len(unique_sources) >= 5:
            break

    return {
        "id": cluster["id"],
        "detailPath": detail_path,
        "storyUrl": cluster.get("storyUrl"),
        "title": cluster.get("title"),
        "summary": cluster.get("summary"),
        "topic": cluster.get("topic"),
        "topicKeywords": cluster.get("topicKeywords", []),
        "imageUrl": cluster.get("imageUrl"),
        "publishedAt": cluster.get("publishedAt"),
        "updatedAt": cluster.get("updatedAt"),
        "sourceCount": cluster.get("sourceCount", 0),
        "articleCount": cluster.get("articleCount", 0),
        "topSources": unique_sources,
        "spectrum": cluster.get("spectrum", {}),
        "scores": cluster.get("scores", {}),
        "flags": cluster.get("flags", []),
    }


def with_source_coverage(sources: list[dict[str, Any]], clusters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    coverage = build_source_coverage(clusters)
    with_coverage: list[dict[str, Any]] = []
    for source in sources:
        source_coverage = coverage.get(source["name"], {"articles": 0, "clusters": 0})
        with_coverage.append({
            **source,
            "coverage": {
                "articles": source_coverage["articles"],
                "clusters": source_coverage["clusters"],
            },
        })
    return with_coverage


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    loaded = json.loads(tmp.read_text(encoding="utf-8"))
    if not loaded.get("clusters"):
        raise SystemExit(f"No clusters in {path.name}; refusing to write")
    tmp.replace(path)


def write_latest_partitioned(out: Path, base_payload: dict[str, Any], clusters: list[dict[str, Any]]) -> None:
    cluster_dir = out.parent / "clusters" / "latest"
    temp_cluster_dir = out.parent / "clusters" / ".latest_tmp"
    if temp_cluster_dir.exists():
        shutil.rmtree(temp_cluster_dir)
    temp_cluster_dir.mkdir(parents=True, exist_ok=True)

    summaries = []
    for cluster in clusters:
        detail_file = temp_cluster_dir / f"{cluster['id']}.json"
        detail_file.write_text(json.dumps(cluster, ensure_ascii=False, indent=2), encoding="utf-8")
        detail_path = f"data/clusters/latest/{cluster['id']}.json"
        summaries.append(build_cluster_summary(cluster, detail_path))

    index_payload = {
        **base_payload,
        "clusters": summaries,
    }
    write_json_atomic(out, index_payload)

    if cluster_dir.exists():
        shutil.rmtree(cluster_dir)
    temp_cluster_dir.rename(cluster_dir)

    missing = [c["id"] for c in clusters if not (cluster_dir / f"{c['id']}.json").exists()]
    if missing:
        raise SystemExit(f"Missing latest cluster detail files: {', '.join(missing[:5])}")


def write_archive_partitioned(archive_dir: Path, date_key: str, base_payload: dict[str, Any], clusters: list[dict[str, Any]]) -> None:
    target_day_dir = archive_dir / date_key
    temp_day_dir = archive_dir / f".{date_key}.tmp"

    if temp_day_dir.exists():
        shutil.rmtree(temp_day_dir)
    temp_day_dir.mkdir(parents=True, exist_ok=True)

    summaries = []
    for cluster in clusters:
        detail_file = temp_day_dir / f"{cluster['id']}.json"
        detail_file.write_text(json.dumps(cluster, ensure_ascii=False, indent=2), encoding="utf-8")
        detail_path = f"data/archive/{date_key}/{cluster['id']}.json"
        summaries.append(build_cluster_summary(cluster, detail_path))

    index_payload = {
        **base_payload,
        "clusters": summaries,
    }
    index_file = temp_day_dir / "index.json"
    index_file.write_text(json.dumps(index_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    loaded = json.loads(index_file.read_text(encoding="utf-8"))
    if not loaded.get("clusters"):
        raise SystemExit("No clusters in archive index; refusing to write")

    if target_day_dir.exists():
        shutil.rmtree(target_day_dir)
    temp_day_dir.rename(target_day_dir)

    missing = [c["id"] for c in clusters if not (target_day_dir / f"{c['id']}.json").exists()]
    if missing or not (target_day_dir / "index.json").exists():
        raise SystemExit(f"Archive validation failed for {date_key}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="public/data/latest.json")
    parser.add_argument("--archive-dir", default="public/data/archive")
    parser.add_argument("--max-stories", type=int, default=80)
    parser.add_argument("--max-articles-per-story", type=int, default=20)
    parser.add_argument("--max-preview-image-fetches-per-story", type=int, default=4)
    parser.add_argument("--preview-image-timeout", type=float, default=5.0)
    parser.add_argument("--disable-preview-images", action="store_true")
    parser.add_argument("--sleep", type=float, default=0.15)
    args = parser.parse_args()

    story_sources = discover_story_ids()
    print(f"Discovered {len(story_sources)} unique stories")

    clusters = []
    image_stats: Counter[str] = Counter()
    max_preview_fetches = 0 if args.disable_preview_images else args.max_preview_image_fetches_per_story
    for idx, (sid, labels) in enumerate(story_sources.items()):
        if len(clusters) >= args.max_stories:
            break
        print(f"[{idx+1}/{len(story_sources)}] story {sid[:12]} from {','.join(sorted(labels))}")
        cluster = build_cluster(
            sid,
            labels,
            args.max_articles_per_story,
            max_preview_image_fetches=max_preview_fetches,
            preview_image_timeout=args.preview_image_timeout,
            image_stats=image_stats,
        )
        if cluster:
            clusters.append(cluster)
        time.sleep(args.sleep)

    clusters = dedupe_clusters(clusters)
    clusters.sort(key=lambda c: (c["articleCount"], c["spectrum"]["knownCount"]), reverse=True)
    article_count = sum(len(c["articles"]) for c in clusters)
    known_sources = set()
    unknown_sources = set()
    for c in clusters:
        for a in c["articles"]:
            source_key = a.get("sourceCanonical") or a["source"]
            (known_sources if a.get("spectrumScore") is not None else unknown_sources).add(source_key)

    payload_base = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "version": "0.2.0-editorial-collection",
        "source": "Coleta editorial / stories coletados de manchetes e tópicos",
        "stats": {
            "clusterCount": len(clusters),
            "articleCount": article_count,
            "knownSources": len(known_sources),
            "unknownSources": len(unknown_sources),
            "discoveredStories": len(story_sources),
            "imageFetchAttempts": image_stats["preview_fetch_attempts"],
            "articleImagesFromPreview": image_stats["article_images_open_graph"],
            "clusterImagesFromPreview": image_stats["cluster_images_real"],
            "clusterImagesFromFallback": image_stats["cluster_images_fallback"],
        },
        "sources": with_source_coverage(build_sources(), clusters),
    }

    out = Path(args.output)
    write_latest_partitioned(out, payload_base, clusters)

    archive_dir = Path(args.archive_dir)
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    write_archive_partitioned(archive_dir, archive_date, payload_base, clusters)

    print(f"Wrote partitioned latest index {out}: {len(clusters)} clusters, {article_count} articles")
    print(f"Wrote partitioned archive {archive_dir / archive_date}")
    print(
        "Images: "
        f"{image_stats['article_images_open_graph']} article previews, "
        f"{image_stats['cluster_images_real']} cluster previews, "
        f"{image_stats['cluster_images_fallback']} cluster fallbacks, "
        f"{image_stats['preview_fetch_failed']} failed fetches"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
