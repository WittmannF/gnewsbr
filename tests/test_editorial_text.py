"""Internal source IDs belong in structured references, not reader-facing prose."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from enrichment.editorial_text import clean_reader_text, clean_news_payload


class ReaderTextTests(unittest.TestCase):
    def test_multiple_semicolon_separated_article_ids(self):
        text = (
            "A decisão depende de seu mandato atual. "
            "(article_43db944271d3; article_cc787d1fb01f) "
            "Aliados reagiram à declaração."
        )
        self.assertEqual(
            clean_reader_text(text),
            "A decisão depende de seu mandato atual. Aliados reagiram à declaração.",
        )

    def test_single_and_comma_separated_article_ids(self):
        text = (
            "O governador foi criticado (article_8aa29db554bc, article_76dd46422187). "
            "A decisão será coletiva (article_980e1f2d95d3)."
        )
        self.assertEqual(
            clean_reader_text(text),
            "O governador foi criticado. A decisão será coletiva.",
        )

    def test_normal_content_and_publication_dates_are_unchanged(self):
        text = "O PL divulgou notícia em 31/10/2026. Fontes: Folha e O GLOBO."
        self.assertEqual(clean_reader_text(text), text)

    def test_structured_source_ids_and_urls_remain_intact(self):
        payload = {
            "clusterId": "story_abc123",
            "sourceArticles": [{
                "articleId": "article_43db944271d3",
                "url": "https://example.com/noticia",
            }],
            "news": {
                "headline": "Notícia consolidada",
                "subtitle": "Resumo (article_43db944271d3)",
                "sections": [{
                    "heading": "Contexto",
                    "paragraphs": ["A declaração ocorreu (article_43db944271d3)."],
                    "claimIds": ["claim_1"],
                }],
                "claims": [{
                    "claimId": "claim_1",
                    "articleId": "article_43db944271d3",
                    "text": "Relato (article_43db944271d3)",
                }],
                "coverageAngles": [{
                    "articleId": "article_43db944271d3",
                    "focus": "Destaca o encontro (article_43db944271d3)",
                }],
                "openQuestions": ["Qual será a data? (article_43db944271d3)"],
            },
        }
        result = clean_news_payload(payload)
        self.assertEqual(result["news"]["subtitle"], "Resumo")
        self.assertEqual(result["news"]["sections"][0]["paragraphs"][0], "A declaração ocorreu.")
        self.assertEqual(result["news"]["claims"][0]["articleId"], "article_43db944271d3")
        self.assertEqual(result["sourceArticles"][0]["articleId"], "article_43db944271d3")
        self.assertEqual(result["sourceArticles"][0]["url"], "https://example.com/noticia")
        self.assertEqual(result["news"]["sections"][0]["claimIds"], ["claim_1"])


if __name__ == "__main__":
    unittest.main()
