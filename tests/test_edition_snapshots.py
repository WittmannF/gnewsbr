"""Ensure published editions survive changes to the hourly live feed."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from enrichment.edition_snapshots import index_story_entry, snapshot_for_story


class EditionSnapshotsTest(unittest.TestCase):
    def test_uses_recorded_article_archive_when_live_cluster_is_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dest = root / "public/data/article-content/2026-10-31/index.json"
            dest.parent.mkdir(parents=True)
            dest.write_text(json.dumps({"clusters": [{
                "id": "story_removed",
                "storyUrl": "https://news.google.com/example",
                "title": "Reportagem original",
                "scores": {"confidence": 95, "coverageDiversity": 80,
                           "spectrumBalance": 85, "headlineDivergence": 50},
                "articles": [
                    {"archiveId": "a1", "title": "Fonte um", "url": "https://a.example/article",
                     "source": "Fonte A", "bucket": "center", "publishedAt": "2026-10-31T12:00:00Z"},
                    {"archiveId": "a2", "title": "Fonte dois", "url": "https://b.example/article",
                     "source": "Fonte B", "bucket": "centerRight", "publishedAt": "2026-10-31T13:00:00Z"},
                ],
            }]}), encoding="utf-8")
            snapshot = snapshot_for_story(
                "story_removed", {"headline": "Nova manchete", "subtitle": "Resumo",
                                  "generatedAt": "2026-10-31T14:00:00Z"}, "2026-10-31", root
            )
            self.assertEqual(len(snapshot["articles"]), 2)
            self.assertEqual(snapshot["spectrum"]["knownCount"], 2)
            self.assertEqual(snapshot["scores"]["confidence"], 95)
            self.assertEqual(snapshot["imageUrl"], "")
            self.assertEqual(snapshot["articles"][0]["url"], "https://a.example/article")
            self.assertNotIn("cleanText", json.dumps(snapshot))

    def test_prefers_actual_historical_editorial_cluster_and_photo(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archived = root / "public/data/archive/2026-10-31/story_abc.json"
            archived.parent.mkdir(parents=True)
            archived.write_text(json.dumps({
                "id": "story_abc", "imageUrl": "https://news.example/photo.jpg",
                "topic": "Ciência", "title": "História", "summary": "Resumo",
                "articles": [{"id": "a", "source": "Fonte", "url": "https://news.example"}],
                "spectrum": {"knownCount": 1, "unknownCount": 0, "buckets": {"center": 1}},
                "scores": {"confidence": 93}, "flags": [],
            }), encoding="utf-8")
            snapshot = snapshot_for_story("story_abc", {"headline": "IA", "subtitle": "IA"}, "2026-10-31", root)
            self.assertEqual(snapshot["imageUrl"], "https://news.example/photo.jpg")
            self.assertEqual(snapshot["topic"], "Ciência")

    def test_keeps_snapshot_and_sources_on_index_rebuild_without_archive(self):
        payload = {
            "clusterId": "story_removed",
            "generatedAt": "2026-10-31T15:00:00Z",
            "archiveDate": "2026-10-31",
            "news": {"headline": "Título", "subtitle": "Subtítulo"},
            "sourceArticles": [
                {"articleId": "article_1", "source": "G1", "url": "https://g1.globo.com/example"},
                {"articleId": "article_2", "source": "CNN", "url": "https://cnn.example/news"},
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            old = {"clusterSnapshot": {"id": "story_removed", "articles": [{"url": "https://a.example"}]}}
            indexed = index_story_entry(payload, existing=old, root=Path(directory))
            self.assertEqual(indexed["clusterSnapshot"], old["clusterSnapshot"])
            self.assertEqual(len(indexed["sources"]), 2)
            self.assertEqual(indexed["sources"][0]["url"], "https://g1.globo.com/example")
            self.assertEqual(indexed["sourceCount"], 2)

    def test_no_invented_cluster_when_both_archives_are_absent(self):
        with tempfile.TemporaryDirectory() as directory:
            item = index_story_entry({
                "clusterId": "story_missing", "generatedAt": "2026-10-31T15:00:00Z",
                "news": {"headline": "Notícia", "subtitle": "Resumo"},
                "sourceArticles": [{"source": "Fonte", "url": "https://example.com",
                                    "articleId": "article_1"}],
            }, root=Path(directory))
            self.assertNotIn("clusterSnapshot", item)
            self.assertEqual(item["sources"][0]["source"], "Fonte")


if __name__ == "__main__":
    unittest.main()
