import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from enrichment.schemas import ArticleQuality, NormalizedArticle


def _make_article(archive_id, domain, bucket, word_count=500, rank=1, status="ok"):
    return NormalizedArticle(
        archiveId=archive_id,
        articleId=f"art_{archive_id}",
        clusterId="story_test",
        articleRank=rank,
        source="Test Source",
        sourceDomain=domain,
        bucket=bucket,
        title="Test title",
        url="https://example.com",
        extractionStatus="ok",
        originalWordCount=word_count,
        cleanWordCount=word_count,
        cleanText="x " * word_count,
        contentHash="sha256-test",
        quality=ArticleQuality(status=status),
    )


def test_select_max_per_cluster():
    from select_articles_for_enrichment import _select_articles
    articles = [_make_article(f"a{i}", f"domain{i}.com", "left", rank=i) for i in range(10)]
    selected = _select_articles(articles, max_per_cluster=5)
    assert len(selected) <= 5


def test_select_domain_diversity():
    from select_articles_for_enrichment import _select_articles
    # 3 articles from same domain, 2 from different
    articles = [
        _make_article("a1", "same.com", "left", rank=1),
        _make_article("a2", "same.com", "left", rank=2),
        _make_article("a3", "same.com", "left", rank=3),
        _make_article("a4", "other.com", "right", rank=4),
        _make_article("a5", "third.com", "center", rank=5),
    ]
    selected = _select_articles(articles, max_per_cluster=3)
    domains = [a.sourceDomain for a in selected]
    # Should prefer distinct domains first pass
    assert len(set(d for d in domains)) >= min(3, len(selected))


def test_select_ignores_low_quality():
    from select_articles_for_enrichment import _select_articles
    articles = [
        _make_article("a1", "good.com", "left", word_count=100, status="low_quality_extraction"),
        _make_article("a2", "good2.com", "right", word_count=500),
    ]
    selected = _select_articles(articles, max_per_cluster=5)
    ids = [a.archiveId for a in selected]
    assert "a1" not in ids
    assert "a2" in ids


def test_cluster_score_increases_with_diversity():
    from select_articles_for_enrichment import _cluster_score
    few = [_make_article("a1", "d.com", "left")]
    many_diverse = [
        _make_article("a1", "d1.com", "left"),
        _make_article("a2", "d2.com", "right"),
        _make_article("a3", "d3.com", "center"),
    ]
    assert _cluster_score(many_diverse) > _cluster_score(few)
