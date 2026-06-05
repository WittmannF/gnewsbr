import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "archive_article_content.py"
spec = importlib.util.spec_from_file_location("archive_article_content", MODULE_PATH)
archive_article_content = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(archive_article_content)


def make_cluster(cluster_id, seed_pages, confidence, article_total=7, source_prefix="Fonte"):
    articles = []
    for idx in range(article_total):
        bucket = ["left", "center", "right", "unknown"][idx % 4]
        articles.append(
            {
                "id": f"{cluster_id}_a{idx}",
                "title": f"Matéria {idx} do {cluster_id}",
                "description": f"Descrição {idx}",
                "url": f"https://site{idx % 3}.example.com/{cluster_id}/{idx}",
                "source": f"{source_prefix} {idx % 4}",
                "sourceDomain": f"site{idx % 3}.example.com",
                "bucket": bucket,
                "publishedAt": "2026-06-05T10:00:00+00:00",
            }
        )
    return {
        "id": cluster_id,
        "title": f"Cluster {cluster_id}",
        "summary": "Resumo",
        "seedPages": seed_pages,
        "scores": {"confidence": confidence, "coverageDiversity": confidence - 10, "headlineDivergence": 30},
        "articles": articles,
        "articleCount": len(articles),
    }


class ArchiveArticleContentTest(unittest.TestCase):
    def test_select_clusters_prefers_home_and_topstories_then_internal_scores_with_limit(self):
        clusters = [
            make_cluster("topic-high", ["topic-1"], 95),
            make_cluster("home-low", ["home"], 50),
            make_cluster("top-high", ["topstories"], 80),
            make_cluster("home-high", ["home", "topic-2"], 90),
        ]

        selected = archive_article_content.select_clusters_for_archive(clusters, max_clusters=3)

        self.assertEqual([cluster["id"] for cluster in selected], ["home-high", "top-high", "home-low"])

    def test_select_articles_keeps_at_least_five_when_available_and_diversifies_domains(self):
        cluster = make_cluster("story_1", ["home"], 90, article_total=9)

        selected = archive_article_content.select_articles_for_cluster(cluster, min_articles=5, max_articles=6)

        self.assertGreaterEqual(len(selected), 5)
        self.assertLessEqual(len(selected), 6)
        self.assertGreaterEqual(len({article["sourceDomain"] for article in selected}), 3)
        self.assertEqual(len({article["url"] for article in selected}), len(selected))

    def test_extract_article_text_strips_scripts_styles_and_reports_light_extractor(self):
        html = """
        <html><head><title>Título da página</title><style>.x{}</style><script>alert(1)</script></head>
        <body><article><h1>Manchete</h1><p>Primeiro parágrafo relevante.</p><p>Segundo parágrafo relevante.</p></article></body></html>
        """

        with patch.object(archive_article_content.requests, "get") as get_mock:
            get_mock.return_value.status_code = 200
            get_mock.return_value.url = "https://example.com/final"
            get_mock.return_value.text = html
            get_mock.return_value.headers = {"content-type": "text/html; charset=utf-8"}
            get_mock.return_value.raise_for_status.return_value = None

            extracted = archive_article_content.extract_article("https://example.com/noticia", timeout=1, enable_crawl4ai=False)

        self.assertEqual(extracted["status"], "ok")
        self.assertEqual(extracted["method"], "light-html")
        self.assertEqual(extracted["resolvedUrl"], "https://example.com/final")
        self.assertIn("Primeiro parágrafo relevante", extracted["text"])
        self.assertNotIn("alert(1)", extracted["text"])
        self.assertNotIn(".x{}", extracted["text"])

    def test_write_archive_outputs_index_cluster_and_article_files_without_raw_html(self):
        cluster = make_cluster("story_1", ["home"], 90, article_total=1)
        article = cluster["articles"][0]
        extracted_by_url = {
            article["url"]: {
                "status": "ok",
                "method": "light-html",
                "resolvedUrl": article["url"],
                "text": "Texto limpo da matéria",
                "wordCount": 4,
                "fetchedAt": "2026-06-05T12:00:00+00:00",
            }
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            out_dir = Path(temp_dir) / "public" / "data" / "article-content"
            archive_article_content.write_article_archive(
                out_dir=out_dir,
                date_key="2026-06-05",
                selected_clusters=[cluster],
                selected_articles_by_cluster={"story_1": [article]},
                extracted_by_url=extracted_by_url,
                generated_at="2026-06-05T12:00:00+00:00",
            )

            day_dir = out_dir / "2026-06-05"
            index_payload = json.loads((day_dir / "index.json").read_text(encoding="utf-8"))
            cluster_payload = json.loads((day_dir / "clusters" / "story_1.json").read_text(encoding="utf-8"))
            article_path = day_dir / "articles" / index_payload["clusters"][0]["articles"][0]["archiveId"] / "content.json"
            article_payload = json.loads(article_path.read_text(encoding="utf-8"))

        self.assertEqual(index_payload["stats"]["clusterCount"], 1)
        self.assertEqual(cluster_payload["articles"][0]["status"], "ok")
        self.assertEqual(article_payload["content"]["text"], "Texto limpo da matéria")
        self.assertNotIn("rawHtml", article_payload)
        self.assertNotIn("rawHtml", article_payload["content"])


if __name__ == "__main__":
    unittest.main()
