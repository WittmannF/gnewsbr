#!/usr/bin/env python3
"""Generate GNewsBR static JSON from Google News Brasil stories.

This intentionally starts from the reference script Fernando provided:
- discover /stories/<id> links from Google News pages;
- open each story page;
- parse AF_initDataCallback JSON;
- extract article-like arrays with title/description/time/url/source;
- enrich sources with the manual 1-10 editorial spectrum map;
- export a frontend-friendly camelCase JSON payload.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import statistics
import sys
import time
from collections import Counter, OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import requests

GOOGLE_NEWS_BASE = "https://news.google.com"
COMMON_PARAMS = "hl=pt-BR&gl=BR&ceid=BR:pt-419"
STORY_URL_TEMPLATE = GOOGLE_NEWS_BASE + "/stories/{}?ceid=BR:pt-419&oc=3&hl=pt-BR&gl=BR"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.6",
}

# Reference manual map. Kept as numeric internal signal; UI labels are deliberately softer.
NEWS_POLITICAL_SPECTRUM = {
    "98 FM Natal": 5, "ANSA Brasil": 5, "Agora no Vale": 5, "Agência Brasil": 4,
    "Aratu ON": 5, "BBC News Brasil": 3, "BNews": 5, "Bahia.Ba": 4,
    "Blog do Esmael": 2, "Brasil 247": 1, "Brasil de Fato": 2, "CNN Brasil": 5,
    "Canal Rural": 6, "CartaCapital": 2, "ClicRDC": 5, "Clube FM 100.5": 5,
    "ContilNet Notícias": 5, "Correio Braziliense": 4, "Correio do Povo": 5,
    "D'Ponta News": 5, "DW (Brasil)": 3, "Diario de Pernambuco": 4,
    "Diário da Capital": 5, "Diário de Goiás": 5, "Diário do Centro do Mundo": 2,
    "Diário do Nordeste": 4, "Diário do Poder": 8, "Estado de Minas": 5, "Estadão": 6,
    "Exame Notícias": 5, "Expresso": 5, "Extra": 5, "Folha Vitória": 5,
    "Folha de Boa Vista": 5, "Folha de Pernambuco": 4, "Forças Terrestres": 7,
    "G1": 5, "GOV.BR": 5, "GZH": 5, "Gazeta do Povo": 8,
    "Hora Certa Notícias": 5, "Hora do Povo": 2, "ISTOÉ": 7, "InfoMoney": 5,
    "Inteligência Financeira": 5, "Investing.com Brasil": 5, "Istoé Dinheiro": 6,
    "Itatiaia": 5, "Jornal Correio": 5, "Jornal O Sul": 5, "Jornal Opção": 5,
    "Jornal de Brasília": 5, "Jornal de Notícias": 5, "Jornal do Comércio": 5,
    "Jovem Pan": 9, "MSN": 5, "Mais Brasília": 5, "Metrópoles": 5,
    "Money Times": 5, "NSC Total": 5, "Nexo Jornal": 3, "Notícia Hoje": 5,
    "Notícias Agrícolas": 7, "O Antagonista": 8, "O Bairrista": 5, "O Bastidor": 5,
    "O Cafezinho": 2, "O Dia": 5, "O Globo": 6, "O POVO": 4, "O Popular": 5,
    "O Tempo": 5, "OLiberal.com": 5, "Petronotícias": 5, "Pleno.News": 9,
    "Poder360": 6, "Ponta Porã Informa": 5, "Portal Salvador FM": 5,
    "Portal do Estado do Rio Grande do Sul": 5, "Portal iG": 5, "Público": 3,
    "R7": 7, "RDCTV": 5, "RFI Português": 3, "Revista Oeste": 10,
    "Robsonpiresxerife": 5, "SBT": 7, "SIC Notícias": 5, "Senado Federal": 5,
    "Seu Dinheiro": 5, "Stars Insider": 5, "Sul21": 2, "TSF Online": 5,
    "Terra": 5, "Tribuna do Norte": 5, "Tribuna do Sertão": 5, "UOL Confere": 4,
    "UOL Notícias": 5, "VEJA": 8, "Vermelho": 1, "cancaonova.com": 6, "epbr": 5,
    "montesclaros.com": 5, "sampi.net.br": 5, "Área VIP": 5,
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


def fetch(url: str, timeout: int = 25) -> str:
    resp = requests.get(url, headers=HEADERS, timeout=timeout)
    resp.raise_for_status()
    return resp.text


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
        # Some Google markup puts escaped URLs in data blobs. This catches those too.
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
    # Observed Google News structure: row[10][2] = source name; row[36][1][0][0] = "Acessar Fonte".
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


def source_score(source: str) -> int | None:
    if source in NEWS_POLITICAL_SPECTRUM:
        return NEWS_POLITICAL_SPECTRUM[source]
    normalized = source.strip().lower()
    for key, value in NEWS_POLITICAL_SPECTRUM.items():
        if key.strip().lower() == normalized:
            return value
    return None


def article_id(url: str) -> str:
    return "article_" + hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]


def build_cluster(story_id: str, seed_labels: set[str], max_articles_per_story: int) -> dict[str, Any] | None:
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

    articles = []
    bucket_counts = {"left": 0, "centerLeft": 0, "center": 0, "centerRight": 0, "right": 0, "unknown": 0}
    scores = []
    for item in articles_raw:
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
            "sourceDomain": item.get("sourceDomain"),
            "publishedAt": item["publishedAt"],
            "postedLabel": item.get("postedLabel") or "",
            "imageUrl": None,
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
    summary = articles[0]["description"] or "Cluster extraído do Google News Brasil com artigos relacionados e distribuição editorial estimada."
    source_count = len(set(a["source"] for a in articles))
    fallback_image = FALLBACK_IMAGES[int(hashlib.sha1(story_id.encode()).hexdigest(), 16) % len(FALLBACK_IMAGES)]

    return {
        "id": "story_" + story_id[:16],
        "storyId": story_id,
        "storyUrl": url,
        "seedPages": sorted(seed_labels),
        "title": title,
        "summary": summary,
        "topic": " · ".join(keywords[:2]).title() if keywords else "Manchetes",
        "topicKeywords": keywords,
        "imageUrl": fallback_image,
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
    return [
        {
            "name": name,
            "spectrumScore": score,
            "bucket": score_to_bucket(score),
            "label": labels[score_to_bucket(score)],
            "confidence": "manual",
            "region": "Brasil",
            "type": "veículo",
        }
        for name, score in sorted(NEWS_POLITICAL_SPECTRUM.items())
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="public/data/latest.json")
    parser.add_argument("--archive-dir", default="public/data/archive")
    parser.add_argument("--max-stories", type=int, default=80)
    parser.add_argument("--max-articles-per-story", type=int, default=20)
    parser.add_argument("--sleep", type=float, default=0.15)
    args = parser.parse_args()

    story_sources = discover_story_ids()
    print(f"Discovered {len(story_sources)} unique stories")

    clusters = []
    for idx, (sid, labels) in enumerate(story_sources.items()):
        if len(clusters) >= args.max_stories:
            break
        print(f"[{idx+1}/{len(story_sources)}] story {sid[:12]} from {','.join(sorted(labels))}")
        cluster = build_cluster(sid, labels, args.max_articles_per_story)
        if cluster:
            clusters.append(cluster)
        time.sleep(args.sleep)

    clusters.sort(key=lambda c: (c["articleCount"], c["spectrum"]["knownCount"]), reverse=True)
    article_count = sum(len(c["articles"]) for c in clusters)
    known_sources = set()
    unknown_sources = set()
    for c in clusters:
        for a in c["articles"]:
            (known_sources if a.get("spectrumScore") is not None else unknown_sources).add(a["source"])

    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "version": "0.2.0-google-news-real",
        "source": "Google News Brasil /stories coletados de Manchetes e tópicos",
        "stats": {
            "clusterCount": len(clusters),
            "articleCount": article_count,
            "knownSources": len(known_sources),
            "unknownSources": len(unknown_sources),
            "discoveredStories": len(story_sources),
        },
        "clusters": clusters,
        "sources": build_sources(),
    }

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp.json")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    # Validate by loading back and checking minimally.
    loaded = json.loads(tmp.read_text(encoding="utf-8"))
    if not loaded["clusters"]:
        raise SystemExit("No clusters generated; refusing to overwrite latest.json")
    tmp.replace(out)

    archive_dir = Path(args.archive_dir)
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive = archive_dir / (datetime.now(timezone.utc).strftime("%Y-%m-%d") + ".json")
    archive.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Wrote {out}: {len(clusters)} clusters, {article_count} articles")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
