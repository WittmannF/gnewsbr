#!/usr/bin/env python3
"""Generate structured LLM summaries for selected articles."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR / "scripts"))

from enrichment.llm_client import LLMClient, make_client
from enrichment.paths import article_summaries_dir, normalized_articles_dir
from enrichment.prompts import ARTICLE_SUMMARY_SYSTEM, build_article_user_prompt
from enrichment.schemas import ArticleSummary, Confidence, NormalizedArticle


def _summary_cache_key(model: str, prompt_version: str, content_hash: str) -> str:
    return f"{model}::{prompt_version}::{content_hash}"


def summarize_articles(
    date: str,
    selected_path: Path,
    norm_dir: Path,
    output_dir: Path,
    client: LLMClient,
    model: str,
    prompt_version: str,
) -> tuple[list[ArticleSummary], list[dict]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    selection = json.loads(selected_path.read_text(encoding="utf-8"))

    # Build set of selected archiveIds
    selected_ids: set[str] = set()
    for cluster in selection.get("clusters", []):
        selected_ids.update(cluster.get("selectedArticles", []))

    # Build cache of existing summaries keyed by cache_key
    cache: dict[str, ArticleSummary] = {}
    for path in output_dir.glob("*.json"):
        try:
            s = ArticleSummary.model_validate_json(path.read_text(encoding="utf-8"))
            key = _summary_cache_key(s.model, s.promptVersion, s.contentHash)
            cache[key] = s
        except Exception:
            pass

    results: list[ArticleSummary] = []
    errors: list[dict] = []

    for archive_id in selected_ids:
        norm_path = norm_dir / f"{archive_id}.json"
        if not norm_path.exists():
            errors.append({"archiveId": archive_id, "stage": "summarize_article", "error": "normalized_not_found"})
            continue

        try:
            article = NormalizedArticle.model_validate_json(norm_path.read_text(encoding="utf-8"))
        except Exception as e:
            errors.append({"archiveId": archive_id, "stage": "summarize_article", "error": str(e)})
            continue

        if article.quality.status != "ok":
            continue

        cache_key = _summary_cache_key(model, prompt_version, article.contentHash)
        if cache_key in cache:
            results.append(cache[cache_key])
            continue

        try:
            raw = client.generate_json(
                ARTICLE_SUMMARY_SYSTEM,
                build_article_user_prompt(article.model_dump()),
                schema_name="article_summary",
            )
        except Exception as e:
            errors.append({"archiveId": archive_id, "stage": "summarize_article", "error": str(e)})
            continue

        try:
            summary = ArticleSummary(
                archiveId=article.archiveId,
                articleId=article.articleId,
                clusterId=article.clusterId,
                source=article.source,
                sourceDomain=article.sourceDomain,
                bucket=article.bucket,
                title=article.title,
                url=article.url,
                publishedAt=article.publishedAt,
                model=model,
                promptVersion=prompt_version,
                contentHash=article.contentHash,
                generatedAt=datetime.now(timezone.utc).isoformat(),
                summary=raw.get("summary", ""),
                whatHappened=raw.get("whatHappened", ""),
                mainClaims=raw.get("mainClaims", []),
                keyEntities=raw.get("keyEntities", []),
                datesAndNumbers=raw.get("datesAndNumbers", []),
                articleType=raw.get("articleType", "news"),
                tone=raw.get("tone", "neutral"),
                notableFraming=raw.get("notableFraming", ""),
                limitations=raw.get("limitations", []),
                confidence=raw.get("confidence", "medium"),
            )
        except Exception as e:
            errors.append({"archiveId": archive_id, "stage": "summarize_article", "error": f"schema_validation: {e}"})
            continue

        out_path = output_dir / f"{archive_id}.json"
        out_path.write_text(summary.model_dump_json(indent=2), encoding="utf-8")
        results.append(summary)

    print(f"Article summaries: {len(results)} generated, {len(errors)} errors")
    return results, errors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None)
    parser.add_argument("--selected-articles", default=None)
    parser.add_argument("--normalized-articles-dir", default=None)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--prompt-version", default="article-summary-v1")
    parser.add_argument("--mock", action="store_true")
    args = parser.parse_args()

    from datetime import datetime, timezone
    date = args.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    from enrichment.paths import ENRICHMENT_DATA
    selected = Path(args.selected_articles) if args.selected_articles else ENRICHMENT_DATA / "selected-articles" / f"{date}.json"
    norm_dir = Path(args.normalized_articles_dir) if args.normalized_articles_dir else normalized_articles_dir(date)
    out_dir = Path(args.output_dir) if args.output_dir else article_summaries_dir(date)
    model = args.model or "llama3.2:3b"

    client = make_client(model=model, mock=args.mock)
    summarize_articles(date, selected, norm_dir, out_dir, client, model, args.prompt_version)


if __name__ == "__main__":
    main()
