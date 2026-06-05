import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import pytest
from pydantic import ValidationError

from enrichment.schemas import (
    ArticleQuality,
    ArticleSummary,
    ClusterSummary,
    Confidence,
    HeadlineDivergence,
    NormalizedArticle,
    RawArticleContent,
)

_RAW_FIXTURE = {
    "archiveId": "article_48bddf561985174f",
    "article": {
        "bucket": "centerLeft",
        "description": "Pai de Henry.",
        "id": "article_d4619f49ad0e",
        "publishedAt": "2026-06-04T07:30:00+00:00",
        "source": "Folha de S.Paulo",
        "sourceCanonical": "Folha de S.Paulo",
        "sourceDomain": "www1.folha.uol.com.br",
        "title": "'Mataram o meu filho pela terceira vez'",
        "url": "https://www1.folha.uol.com.br/test",
    },
    "articleRank": 3,
    "clusterId": "story_22ba073c31d0",
    "content": {"text": "Texto do artigo.", "wordCount": 100},
    "extraction": {
        "contentType": "text/html",
        "fetchedAt": "2026-06-05T04:19:21.873851+00:00",
        "method": "light-html",
        "resolvedUrl": "https://www1.folha.uol.com.br/test",
        "status": "ok",
        "title": "Test title",
        "wordCount": 100,
    },
}


def test_raw_article_content_loads():
    data = RawArticleContent.model_validate(_RAW_FIXTURE)
    assert data.archiveId == "article_48bddf561985174f"
    assert data.extraction.status == "ok"
    assert data.article.bucket == "centerLeft"


def test_normalized_article_requires_clean_text():
    with pytest.raises(ValidationError):
        NormalizedArticle(
            archiveId="x",
            articleId="y",
            clusterId="z",
            source="S",
            url="https://x.com",
            extractionStatus="ok",
            originalWordCount=100,
            cleanWordCount=0,
            # missing cleanText
            contentHash="sha256-x",
            quality=ArticleQuality(status="ok"),
        )


def test_article_summary_requires_confidence():
    with pytest.raises(ValidationError):
        ArticleSummary(
            archiveId="x",
            articleId="y",
            clusterId="z",
            source="S",
            title="T",
            url="https://x.com",
            model="m",
            promptVersion="v",
            contentHash="h",
            generatedAt="2026-01-01T00:00:00Z",
            summary="s",
            whatHappened="w",
            confidence="invalid_value",  # type: ignore
        )


def test_cluster_summary_confidence_enum():
    cs = ClusterSummary(
        clusterId="story_x",
        model="m",
        promptVersion="v",
        generatedAt="2026-01-01T00:00:00Z",
        neutralHeadline="H",
        neutralSummary="S",
        whatHappened="W",
        whyItMatters="M",
        headlineDivergence=HeadlineDivergence(level="low", explanation="ok"),
        newsletterBlurb="B",
        confidence="high",
    )
    assert cs.confidence == Confidence.high


def test_confidence_invalid_raises():
    with pytest.raises(ValidationError):
        ClusterSummary(
            clusterId="story_x",
            model="m",
            promptVersion="v",
            generatedAt="2026-01-01T00:00:00Z",
            neutralHeadline="H",
            neutralSummary="S",
            whatHappened="W",
            whyItMatters="M",
            headlineDivergence=HeadlineDivergence(level="low", explanation="ok"),
            newsletterBlurb="B",
            confidence="super-high",  # type: ignore
        )
