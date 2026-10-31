"""News synthesis must retain source links when third-party full text is blocked."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from ingest_article_content import ingest
from select_articles_for_enrichment import is_usable


class MetadataFallbackTest(unittest.TestCase):
    def test_headline_snippet_is_marked_limited_not_full_article(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            src = root / "raw" / "article_test"
            src.mkdir(parents=True)
            raw = {
                "archiveId": "article_test",
                "clusterId": "story_test",
                "article": {
                    "id": "article_test", "title": "Brasil anuncia uma reunião internacional",
                    "description": "O encontro foi anunciado nesta sexta-feira, segundo informações publicadas pela fonte original.",
                    "source": "Veículo Teste", "sourceDomain": "source.example",
                    "url": "https://source.example/meeting",
                },
                "content": {"text": "", "wordCount": 0},
                "extraction": {"status": "error", "fetchedAt": "2026-10-31T10:00:00+00:00"},
            }
            (src / "content.json").write_text(json.dumps(raw), encoding="utf-8")
            normalized = ingest("2026-10-31", root / "raw", root / "normalized")
            self.assertEqual(len(normalized), 1)
            self.assertEqual(normalized[0].quality.status, "summary_only")
            self.assertTrue(is_usable(normalized[0]))
            self.assertIn("Brasil anuncia", normalized[0].cleanText)
            self.assertEqual(normalized[0].url, "https://source.example/meeting")


if __name__ == "__main__":
    unittest.main()
