#!/usr/bin/env python3
"""Generate daily GNewsBR enrichment artifacts from archived article content.

This script is intentionally additive: it consumes public/data/article-content/{date}
created by scripts/archive_article_content.py and publishes structured enrichment data
for newsletters/UI without changing the existing Google News collection pipeline.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import request, error

ROOT_DIR = Path(__file__).resolve().parents[2]
PUBLIC_DATA_DIR = ROOT_DIR / "public" / "data"
PROMPT_VERSION = "gnewsbr-enrichment-v1"
DEFAULT_MODEL = "llama3.2:3b"
MAX_TEXT_CHARS_PER_ARTICLE = 4000


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def resolve_public_data_path(root_dir: Path, stored_path: str) -> Path:
    normalized = stored_path.lstrip("/")
    if normalized.startswith("public/data/"):
        return root_dir / normalized
    if normalized.startswith("data/"):
        return root_dir / "public" / normalized
    return root_dir / "public" / "data" / normalized


def load_article_content_archive(root_dir: Path, date_key: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    index_path = root_dir / "public" / "data" / "article-content" / date_key / "index.json"
    if not index_path.exists():
        raise FileNotFoundError(f"Article content index not found: {index_path}")
    index = read_json(index_path)
    clusters: list[dict[str, Any]] = []
    for cluster in index.get("clusters", []):
        hydrated = dict(cluster)
        hydrated_articles = []
        for article in cluster.get("articles", []):
            item = dict(article)
            content_path = resolve_public_data_path(root_dir, str(article.get("path", "")))
            content_doc: dict[str, Any] = {}
            if content_path.exists():
                content_doc = read_json(content_path)
            item["contentPath"] = str(content_path.relative_to(root_dir)) if content_path.exists() else str(content_path)
            item["contentText"] = str(content_doc.get("content", {}).get("text") or "")
            item["contentDigest"] = stable_digest(item["contentText"]) if item["contentText"] else None
            item["extraction"] = content_doc.get("extraction", {})
            hydrated_articles.append(item)
        hydrated["articles"] = hydrated_articles
        clusters.append(hydrated)
    return index, clusters


def compact_text(text: str, limit: int = MAX_TEXT_CHARS_PER_ARTICLE) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def article_summary_fallback(article: dict[str, Any], provider: str, model: str) -> dict[str, Any]:
    text = compact_text(article.get("contentText", ""), 600)
    source = article.get("source") or article.get("sourceDomain") or "Fonte"
    title = str(article.get("title") or "Matéria sem título")
    status = str(article.get("status") or article.get("extraction", {}).get("status") or "unknown")
    warnings: list[str] = []
    if status != "ok":
        warnings.append(f"fetch_status:{status}")
    if not text:
        warnings.append("empty_extracted_text")
    return {
        "archiveId": article.get("archiveId"),
        "title": title,
        "source": source,
        "sourceDomain": article.get("sourceDomain"),
        "bucket": article.get("bucket", "unknown"),
        "url": article.get("url"),
        "publishedAt": article.get("publishedAt"),
        "fetchStatus": status,
        "wordCount": article.get("wordCount") or article.get("extraction", {}).get("wordCount") or 0,
        "contentDigest": article.get("contentDigest"),
        "provider": provider,
        "model": model,
        "promptVersion": PROMPT_VERSION,
        "fallbackMetadataUsed": True,
        "summary": {
            "headline": title,
            "sourceNote": f"{source} publicou: {title}",
            "evidencePreview": text,
        },
        "qualityWarnings": warnings,
    }


def ollama_json(prompt: str, model: str, endpoint: str, timeout: int = 120) -> dict[str, Any]:
    payload = json.dumps({"model": model, "prompt": prompt, "format": "json", "stream": False}).encode("utf-8")
    req = request.Request(
        endpoint.rstrip("/") + "/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Ollama request failed: {exc}") from exc
    raw = data.get("response", "{}")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Ollama returned invalid JSON: {raw[:200]}") from exc


def maybe_llm_article_summary(article: dict[str, Any], provider: str, model: str) -> dict[str, Any]:
    if provider != "ollama":
        return article_summary_fallback(article, provider, model)
    prompt = (
        "Resuma a matéria abaixo para o GNewsBR. Responda apenas JSON válido com as chaves "
        "headline, keyFacts, uncertainties, qualityWarnings. Não invente fatos ausentes.\n\n"
        f"Fonte: {article.get('source')}\nTítulo: {article.get('title')}\nTexto: {compact_text(article.get('contentText', ''))}"
    )
    try:
        llm = ollama_json(prompt, model, os.environ.get("LOCAL_LLM_ENDPOINT", "http://127.0.0.1:11434"))
    except RuntimeError as exc:
        fallback = article_summary_fallback(article, provider, model)
        fallback["qualityWarnings"].append(f"llm_error:{exc}")
        return fallback
    fallback = article_summary_fallback(article, provider, model)
    fallback["fallbackMetadataUsed"] = False
    fallback["summary"].update(llm)
    fallback["qualityWarnings"].extend(llm.get("qualityWarnings", []))
    return fallback


def section_for_cluster(cluster: dict[str, Any]) -> str:
    text = " ".join([str(cluster.get("title", ""))] + [str(a.get("title", "")) for a in cluster.get("articles", [])]).lower()
    sections = [
        ("Economia e negócios", ["economia", "mercado", "banco", "juros", "empresa", "dólar", "tarifa"]),
        ("Justiça e segurança", ["justiça", "stf", "prisão", "crime", "polícia", "julgamento", "condena"]),
        ("Mundo", ["eua", "trump", "cuba", "guerra", "china", "rússia", "internacional"]),
        ("Saúde, ciência e clima", ["saúde", "clima", "vacina", "ciência", "hospital"]),
        ("Tecnologia e sociedade", ["tecnologia", "ia", "internet", "aplicativo", "rede social"]),
        ("Brasil político", ["lula", "governo", "congresso", "senado", "câmara", "ministro", "política"]),
    ]
    for label, keywords in sections:
        if any(keyword in text for keyword in keywords):
            return label
    return "Radar rápido"


def cluster_summary(cluster: dict[str, Any], article_summaries: list[dict[str, Any]], provider: str, model: str) -> dict[str, Any]:
    ok_articles = [a for a in article_summaries if a.get("fetchStatus") == "ok"]
    failed_articles = [a for a in article_summaries if a.get("fetchStatus") != "ok"]
    angles_by_bucket: dict[str, list[str]] = defaultdict(list)
    for article in article_summaries:
        bucket = str(article.get("bucket") or "unknown")
        source = str(article.get("source") or article.get("sourceDomain") or "Fonte")
        headline = str(article.get("title") or "")
        if source and headline:
            angles_by_bucket[bucket].append(f"{source}: {headline}")
    angles = [
        {"label": bucket, "summary": "; ".join(items[:3]), "sources": [item.split(":", 1)[0] for item in items[:3]]}
        for bucket, items in sorted(angles_by_bucket.items())
    ]
    titles = [str(a.get("title")) for a in ok_articles[:3] if a.get("title")]
    what_happened = " ".join(titles) if titles else str(cluster.get("title") or "Sem resumo factual disponível.")
    quality_warnings: list[str] = []
    if len(ok_articles) < 2:
        quality_warnings.append("low_read_article_count")
    if failed_articles:
        quality_warnings.append(f"article_failures:{len(failed_articles)}")
    return {
        "clusterId": cluster.get("id"),
        "rank": cluster.get("rank"),
        "title": cluster.get("title"),
        "section": section_for_cluster(cluster),
        "dek": f"Síntese baseada em {len(ok_articles)} matéria(s) lida(s) e {len(article_summaries)} selecionada(s).",
        "whatHappened": what_happened,
        "whyItMatters": "O item foi selecionado por relevância/cobertura no GNewsBR e deve ser revisado editorialmente antes de publicação final.",
        "angles": angles,
        "uncertainties": ["Há fontes com falha de extração; a síntese pode estar parcial."] if failed_articles else [],
        "readArticles": article_summaries,
        "fallbackMetadataUsed": provider != "ollama" or any(a.get("fallbackMetadataUsed") for a in article_summaries),
        "qualityScore": round(len(ok_articles) / max(1, len(article_summaries)), 2),
        "qualityWarnings": quality_warnings,
        "provider": provider,
        "model": model,
        "promptVersion": PROMPT_VERSION,
        "inputDigests": [a.get("contentDigest") for a in article_summaries if a.get("contentDigest")],
    }


def render_markdown(newsletter: dict[str, Any]) -> str:
    date_key = newsletter["date"]
    items = newsletter.get("items", [])
    lines = [
        f"# GNewsBR Daily — {date_key}",
        "",
        f"Últimas 24h · {len(items)} histórias enriquecidas",
        "",
        f"Provider: `{newsletter.get('provider')}` · Modelo: `{newsletter.get('model')}` · Prompt: `{newsletter.get('promptVersion')}`",
        "",
    ]
    for idx, item in enumerate(items, start=1):
        lines.extend(
            [
                f"## {idx}. {item.get('title')}",
                "",
                f"**Seção:** {item.get('section')}",
                "",
                f"**O que aconteceu:** {item.get('whatHappened')}",
                "",
                f"**Por que importa:** {item.get('whyItMatters')}",
                "",
            ]
        )
        if item.get("angles"):
            lines.append("**Ângulos:**")
            for angle in item["angles"]:
                lines.append(f"- {angle.get('label')}: {angle.get('summary')}")
            lines.append("")
        sources = ", ".join(dict.fromkeys(str(a.get("source")) for a in item.get("readArticles", []) if a.get("source")))
        if sources:
            lines.extend([f"**Fontes lidas:** {sources}", ""])
        if item.get("qualityWarnings"):
            lines.extend([f"**Avisos de qualidade:** {', '.join(item['qualityWarnings'])}", ""])
    return "\n".join(lines).strip() + "\n"


def validate_newsletter(newsletter: dict[str, Any]) -> None:
    required = ["date", "generatedAt", "provider", "model", "promptVersion", "fallbackMetadataUsed", "inputDigests", "stats", "items"]
    missing = [field for field in required if field not in newsletter]
    if missing:
        raise ValueError(f"Newsletter missing required fields: {', '.join(missing)}")
    if not isinstance(newsletter.get("items"), list):
        raise ValueError("Newsletter items must be a list")
    for idx, item in enumerate(newsletter["items"]):
        for field in ["clusterId", "title", "whatHappened", "whyItMatters", "angles", "readArticles", "fallbackMetadataUsed"]:
            if field not in item:
                raise ValueError(f"Newsletter item {idx} missing required field: {field}")


def run_enrichment(
    date_key: str,
    root_dir: Path = ROOT_DIR,
    max_clusters: int = 20,
    provider: str = "none",
    model: str = DEFAULT_MODEL,
    now: str | None = None,
) -> dict[str, Any]:
    root_dir = Path(root_dir)
    index, clusters = load_article_content_archive(root_dir, date_key)
    selected_clusters = clusters[:max_clusters]
    cluster_outputs = []
    article_ok = 0
    article_failed = 0
    all_digests: list[str] = []
    output_root = root_dir / "public" / "data" / "enrichment"
    for cluster in selected_clusters:
        article_outputs = [maybe_llm_article_summary(article, provider, model) for article in cluster.get("articles", [])]
        article_ok += sum(1 for article in article_outputs if article.get("fetchStatus") == "ok")
        article_failed += sum(1 for article in article_outputs if article.get("fetchStatus") != "ok")
        cluster_doc = cluster_summary(cluster, article_outputs, provider, model)
        all_digests.extend(cluster_doc.get("inputDigests", []))
        cluster_outputs.append(cluster_doc)
        write_json(output_root / "clusters" / f"{cluster_doc['clusterId']}.json", cluster_doc)
    generated_at = now or now_iso()
    newsletter = {
        "date": date_key,
        "generatedAt": generated_at,
        "sourceArticleContent": f"public/data/article-content/{date_key}/index.json",
        "provider": provider,
        "model": model,
        "promptVersion": PROMPT_VERSION,
        "fallbackMetadataUsed": provider != "ollama" or any(item.get("fallbackMetadataUsed") for item in cluster_outputs),
        "inputDigests": sorted(set(all_digests)),
        "stats": {
            "clustersAvailable": len(clusters),
            "clustersEnriched": len(cluster_outputs),
            "articlesSelected": article_ok + article_failed,
            "articlesOk": article_ok,
            "articlesFailed": article_failed,
        },
        "items": cluster_outputs,
        "qualityWarnings": sorted({warning for item in cluster_outputs for warning in item.get("qualityWarnings", [])}),
        "sourceIndexGeneratedAt": index.get("generatedAt"),
    }
    validate_newsletter(newsletter)
    newsletter_json_path = output_root / "newsletters" / f"{date_key}.json"
    write_json(newsletter_json_path, newsletter)
    (output_root / "newsletters").mkdir(parents=True, exist_ok=True)
    (output_root / "newsletters" / f"{date_key}.md").write_text(render_markdown(newsletter), encoding="utf-8")
    write_json(output_root / "latest.json", newsletter)
    latest_md = output_root / "latest.md"
    shutil.copyfile(output_root / "newsletters" / f"{date_key}.md", latest_md)
    return {
        "date": date_key,
        "selectedClusterCount": len(cluster_outputs),
        "selectedArticleCount": article_ok + article_failed,
        "outputDir": str(output_root),
        "provider": provider,
        "model": model,
    }


def default_date_key() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate GNewsBR enrichment/newsletter artifacts from archived article content")
    parser.add_argument("--date", default=default_date_key())
    parser.add_argument("--root-dir", type=Path, default=ROOT_DIR)
    parser.add_argument("--max-clusters", type=int, default=20)
    parser.add_argument("--llm-provider", choices=["none", "ollama"], default=os.environ.get("NEWSLETTER_LLM_PROVIDER", "none"))
    parser.add_argument("--model", default=os.environ.get("LOCAL_LLM_MODEL") or os.environ.get("NEWSLETTER_LLM_MODEL") or DEFAULT_MODEL)
    parser.add_argument("--now", default=None, help="Deterministic generatedAt timestamp for tests")
    args = parser.parse_args()
    result = run_enrichment(
        date_key=args.date,
        root_dir=args.root_dir,
        max_clusters=args.max_clusters,
        provider=args.llm_provider,
        model=args.model,
        now=args.now,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
