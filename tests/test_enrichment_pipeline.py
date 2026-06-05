import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "enrichment" / "generate_daily_enrichment.py"
spec = importlib.util.spec_from_file_location("generate_daily_enrichment", MODULE_PATH)
generate_daily_enrichment = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(generate_daily_enrichment)


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


class EnrichmentPipelineTest(unittest.TestCase):
    def make_article_content_fixture(self, root: Path) -> None:
        public_data = root / "public" / "data"
        date = "2026-06-05"
        cluster_id = "story_abc"
        articles = []
        for idx, (bucket, source, status) in enumerate(
            [
                ("center", "G1", "ok"),
                ("left", "CartaCapital", "ok"),
                ("centerRight", "Estadão", "error"),
            ],
            start=1,
        ):
            archive_id = f"article_{idx}"
            rel_path = f"data/article-content/{date}/articles/{archive_id}/content.json"
            articles.append(
                {
                    "archiveId": archive_id,
                    "title": f"Título {idx} sobre economia",
                    "source": source,
                    "sourceDomain": f"fonte{idx}.example.com",
                    "bucket": bucket,
                    "url": f"https://fonte{idx}.example.com/noticia",
                    "publishedAt": "2026-06-05T08:00:00+00:00",
                    "status": status,
                    "method": "light-html",
                    "path": rel_path,
                    "wordCount": 120 if status == "ok" else 0,
                }
            )
            write_json(
                public_data / rel_path.removeprefix("data/"),
                {
                    "archiveId": archive_id,
                    "article": articles[-1],
                    "extraction": {"status": status, "method": "light-html", "wordCount": 120 if status == "ok" else 0},
                    "content": {"text": f"Texto limpo da matéria {idx}. Fato relevante e contexto público." if status == "ok" else ""},
                },
            )

        write_json(
            public_data / f"article-content/{date}/index.json",
            {
                "date": date,
                "generatedAt": "2026-06-05T09:00:00+00:00",
                "clusters": [
                    {
                        "id": cluster_id,
                        "rank": 1,
                        "title": "Cluster de economia",
                        "selectedArticleCount": len(articles),
                        "okArticleCount": 2,
                        "scores": {"confidence": 90, "headlineDivergence": 40},
                        "articles": articles,
                    }
                ],
            },
        )

    def test_generate_enrichment_fallback_writes_public_json_markdown_and_cluster_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_article_content_fixture(root)

            result = generate_daily_enrichment.run_enrichment(
                date_key="2026-06-05",
                root_dir=root,
                max_clusters=20,
                provider="none",
                model="llama3.2:3b",
                now="2026-06-05T10:00:00+00:00",
            )

            self.assertEqual(result["selectedClusterCount"], 1)
            newsletter_path = root / "public" / "data" / "enrichment" / "newsletters" / "2026-06-05.json"
            markdown_path = root / "public" / "data" / "enrichment" / "newsletters" / "2026-06-05.md"
            latest_path = root / "public" / "data" / "enrichment" / "latest.json"
            cluster_path = root / "public" / "data" / "enrichment" / "clusters" / "story_abc.json"

            self.assertTrue(newsletter_path.exists())
            self.assertTrue(markdown_path.exists())
            self.assertTrue(latest_path.exists())
            self.assertTrue(cluster_path.exists())

            newsletter = json.loads(newsletter_path.read_text(encoding="utf-8"))
            self.assertEqual(newsletter["date"], "2026-06-05")
            self.assertEqual(newsletter["provider"], "none")
            self.assertEqual(newsletter["model"], "llama3.2:3b")
            self.assertTrue(newsletter["fallbackMetadataUsed"])
            self.assertEqual(newsletter["stats"]["clustersEnriched"], 1)
            self.assertEqual(newsletter["stats"]["articlesOk"], 2)
            self.assertEqual(newsletter["stats"]["articlesFailed"], 1)
            self.assertIn("inputDigests", newsletter)
            self.assertIn("promptVersion", newsletter)
            self.assertEqual(newsletter["items"][0]["clusterId"], "story_abc")
            self.assertTrue(newsletter["items"][0]["fallbackMetadataUsed"])
            self.assertGreaterEqual(len(newsletter["items"][0]["angles"]), 2)
            self.assertIn("Cluster de economia", markdown_path.read_text(encoding="utf-8"))

    def test_validate_newsletter_rejects_missing_required_fields(self):
        invalid = {"date": "2026-06-05", "items": []}

        with self.assertRaises(ValueError):
            generate_daily_enrichment.validate_newsletter(invalid)


if __name__ == "__main__":
    unittest.main()
