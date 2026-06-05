#!/usr/bin/env python3
"""Ingest content.json files into normalized articles for LLM enrichment."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR / "scripts"))

from enrichment.hashing import content_hash
from enrichment.paths import article_content_dir, normalized_articles_dir
from enrichment.schemas import ArticleQuality, NormalizedArticle, RawArticleContent
from enrichment.text_cleaning import clean_boilerplate
from enrichment.text_encoding import repair_mojibake

MIN_WORD_COUNT = 250


def ingest(date: str, source_dir: Path, output_dir: Path) -> list[NormalizedArticle]:
    output_dir.mkdir(parents=True, exist_ok=True)
    content_files = list(source_dir.glob("*/content.json"))
    print(f"Found {len(content_files)} content.json files in {source_dir}")

    results: list[NormalizedArticle] = []
    skipped = 0

    for path in content_files:
        raw = json.loads(path.read_text(encoding="utf-8"))
        try:
            data = RawArticleContent.model_validate(raw)
        except Exception as e:
            print(f"  SKIP {path.parent.name}: schema error — {e}", file=sys.stderr)
            skipped += 1
            continue

        if data.extraction.status != "ok":
            skipped += 1
            continue

        original_text = data.content.text.strip()
        if not original_text or data.content.wordCount < MIN_WORD_COUNT:
            skipped += 1
            continue

        # Encoding repair
        repaired_text, repair_applied = repair_mojibake(original_text)

        # Boilerplate cleaning
        clean_text, removed_ratio = clean_boilerplate(repaired_text)
        clean_word_count = len(clean_text.split())

        warnings: list[str] = []
        status = "ok"
        if clean_word_count < MIN_WORD_COUNT:
            status = "low_quality_extraction"
            warnings.append(f"cleanWordCount={clean_word_count} below threshold")

        article = NormalizedArticle(
            archiveId=data.archiveId,
            articleId=data.article.id,
            clusterId=data.clusterId,
            articleRank=data.articleRank,
            source=data.article.source,
            sourceCanonical=data.article.sourceCanonical,
            sourceDomain=data.article.sourceDomain,
            bucket=data.article.bucket,
            title=data.article.title,
            description=data.article.description,
            url=data.article.url,
            resolvedUrl=data.extraction.resolvedUrl,
            publishedAt=data.article.publishedAt,
            fetchedAt=data.extraction.fetchedAt,
            extractionMethod=data.extraction.method,
            extractionStatus=data.extraction.status,
            originalWordCount=data.content.wordCount,
            cleanWordCount=clean_word_count,
            cleanText=clean_text,
            contentHash=content_hash(clean_text),
            quality=ArticleQuality(
                status=status,
                encodingRepairApplied=repair_applied,
                removedBoilerplateRatio=round(removed_ratio, 3),
                warnings=warnings,
            ),
        )

        out_path = output_dir / f"{data.archiveId}.json"
        out_path.write_text(
            article.model_dump_json(indent=2),
            encoding="utf-8",
        )
        results.append(article)

    print(f"Normalized {len(results)} articles, skipped {skipped}")
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest article content.json files")
    parser.add_argument("--date", default=None, help="Date key YYYY-MM-DD (default: today UTC)")
    parser.add_argument("--article-content-dir", default=None)
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args()

    from datetime import datetime, timezone
    date = args.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    source = Path(args.article_content_dir) if args.article_content_dir else article_content_dir(date)
    output = Path(args.output_dir) if args.output_dir else normalized_articles_dir(date)

    if not source.exists():
        print(f"Source dir not found: {source}", file=sys.stderr)
        sys.exit(1)

    ingest(date, source, output)


if __name__ == "__main__":
    main()
