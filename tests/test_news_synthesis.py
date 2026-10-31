"""Unit tests for grounded structured news synthesis. No network or API key."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from enrichment.schemas import NormalizedArticle, ArticleQuality
from generate_news_synthesis import NewsClaim, NewsSection, CoverageAngle, NewsSynthesis, fingerprint, verify_news


def article(article_id: str, domain: str) -> NormalizedArticle:
    return NormalizedArticle(
        archiveId=f"archive-{article_id}", articleId=article_id, clusterId="story_test",
        source=domain, sourceDomain=domain, title="Reportagem de teste",
        url=f"https://{domain}/noticia", extractionStatus="ok",
        originalWordCount=320, cleanWordCount=320,
        cleanText="A fonte confirmou que a reunião será na terça-feira. Outra informação contextual.",
        contentHash=f"hash-{article_id}",
        quality=ArticleQuality(status="ok"),
    )


def sample_news() -> NewsSynthesis:
    return NewsSynthesis(
        headline="Autoridades anunciam reunião na terça-feira",
        subtitle="Duas fontes relatam o anúncio da reunião.",
        sections=[NewsSection(heading="O que aconteceu",
                              paragraphs=["Autoridades anunciaram uma reunião."],
                              claimIds=["c1", "c2"])],
        claims=[
            NewsClaim(claimId="c1", text="Primeira fonte relata reunião", kind="attributed_statement",
                      articleId="a1"),
            NewsClaim(claimId="c2", text="Segunda fonte relata reunião", kind="attributed_statement",
                      articleId="a2"),
        ],
        coverageAngles=[
            CoverageAngle(articleId="a1", focus="Enfatiza anúncio"),
            CoverageAngle(articleId="a2", focus="Enfatiza a data"),
        ],
        openQuestions=["O local será confirmado?"],
        confidence="medium",
    )


class SynthesisTests(unittest.TestCase):
    def setUp(self) -> None:
        self.articles = [article("a1", "one.example"), article("a2", "two.example")]

    def test_valid_two_source_synthesis(self):
        verify_news(sample_news(), self.articles)

    def test_article_link_is_sufficient_for_mvp(self):
        # The model no longer has to copy exact source excerpts.
        news = sample_news()
        verify_news(news, self.articles)
        self.assertNotIn("excerpt", news.claims[0].model_dump())

    def test_rejects_unknown_article_id(self):
        news = sample_news()
        news.claims[0].articleId = "fictional"
        with self.assertRaisesRegex(ValueError, "Unknown article"):
            verify_news(news, self.articles)

    def test_rejects_missing_claim(self):
        news = sample_news()
        news.sections[0].claimIds = ["nonexistent"]
        with self.assertRaisesRegex(ValueError, "Unreferenced"):
            verify_news(news, self.articles)

    def test_rejects_single_source(self):
        news = sample_news()
        news.claims[1].articleId = "a1"
        with self.assertRaisesRegex(ValueError, "at least 2"):
            verify_news(news, self.articles)

    def test_cache_hash_is_independent_of_article_order(self):
        self.assertEqual(fingerprint(self.articles, "glm"), fingerprint(list(reversed(self.articles)), "glm"))
        self.assertNotEqual(fingerprint(self.articles, "glm"), fingerprint(self.articles, "other"))

    def test_no_raw_article_text_in_published_schema(self):
        self.assertNotIn("cleanText", sample_news().model_dump_json())


if __name__ == "__main__":
    unittest.main()
