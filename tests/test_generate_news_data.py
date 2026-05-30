import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "generate_news_data.py"
spec = importlib.util.spec_from_file_location("generate_news_data", MODULE_PATH)
generate_news_data = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(generate_news_data)


def make_cluster(story_id, urls, title="Repeated story", article_count=None):
    articles = [
        {
            "id": f"article_{idx}",
            "title": f"Article {idx}",
            "url": url,
            "source": f"Source {idx}",
            "sourceCanonical": f"Source {idx}",
            "spectrumScore": 5,
        }
        for idx, url in enumerate(urls)
    ]
    return {
        "id": "story_" + story_id[:16],
        "storyId": story_id,
        "title": title,
        "summary": "",
        "articleCount": article_count if article_count is not None else len(articles),
        "sourceCount": len({a["source"] for a in articles}),
        "articles": articles,
        "spectrum": {"knownCount": len(articles)},
    }


class GenerateNewsDataTest(unittest.TestCase):
    def test_cluster_id_uses_full_story_id_hash_to_avoid_common_google_prefix_collisions(self):
        first = "CAAqNggKIjBDQklTSGpvSmMzUnZjbmt0TXpZd1NoRUtEd2lPMHFXWEVSSGs5Vkd4X19GSHlTZ0FQAQ"
        second = "CAAqNggKIjBDQklTSGpvSmMzUnZjbmt0TXpZd1NoRUtEd2lPMHFXWEVSSE80N3VSeWdubGFTZ0FQAQ"

        self.assertEqual(first[:16], second[:16])
        self.assertNotEqual(generate_news_data.cluster_id(first), generate_news_data.cluster_id(second))

    def test_dedupe_clusters_removes_google_story_variants_with_high_article_overlap(self):
        base_urls = [f"https://example.com/news/{i}" for i in range(20)]
        duplicate_urls = base_urls[:18] + ["https://example.com/news/extra-a", "https://example.com/news/extra-b"]
        unrelated_urls = [f"https://example.com/other/{i}" for i in range(20)]

        first = make_cluster("CAAqNggKIjBDQklT_first", base_urls, article_count=20)
        duplicate = make_cluster("CAAqNggKIjBDQklT_second", duplicate_urls, article_count=20)
        unrelated = make_cluster("CAAqNggKIjBDQklT_third", unrelated_urls, title="Different story", article_count=20)

        result = generate_news_data.dedupe_clusters([first, duplicate, unrelated])

        self.assertEqual([cluster["storyId"] for cluster in result], [first["storyId"], unrelated["storyId"]])

    def test_dedupe_clusters_keeps_more_complete_duplicate_cluster(self):
        shared = [f"https://example.com/news/{i}" for i in range(18)]
        smaller = make_cluster("CAAqNggKIjBDQklT_small", shared, article_count=18)
        larger = make_cluster("CAAqNggKIjBDQklT_large", shared + ["https://example.com/news/18", "https://example.com/news/19"], article_count=20)

        result = generate_news_data.dedupe_clusters([smaller, larger])

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["storyId"], larger["storyId"])

    def test_dedupe_clusters_removes_google_story_variants_with_identical_titles(self):
        first = make_cluster("CAAqNggKIjBDQklT_first", ["https://example.com/a/1", "https://example.com/a/2"], title="Notícias sobre Trump")
        duplicate = make_cluster("CAAqNggKIjBDQklT_second", ["https://example.com/b/1", "https://example.com/b/2"], title="  notícias   sobre trump  ")
        unrelated = make_cluster("CAAqNggKIjBDQklT_third", ["https://example.com/c/1"], title="Different story")

        result = generate_news_data.dedupe_clusters([first, duplicate, unrelated])

        self.assertEqual([cluster["storyId"] for cluster in result], [first["storyId"], unrelated["storyId"]])

    def test_preview_image_from_html_prefers_secure_open_graph_image(self):
        html = """
        <meta property="og:image" content="https://cdn.example.com/basic.jpg">
        <meta property="og:image:secure_url" content="https://cdn.example.com/secure.jpg">
        """

        result = generate_news_data.preview_image_from_html(html, "https://example.com/news/story")

        self.assertEqual(result, "https://cdn.example.com/secure.jpg")

    def test_preview_image_from_html_resolves_relative_urls(self):
        html = '<meta name="twitter:image" content="/images/story.jpg">'

        result = generate_news_data.preview_image_from_html(html, "https://example.com/news/story")

        self.assertEqual(result, "https://example.com/images/story.jpg")

    def test_preview_image_from_html_ignores_placeholder_images(self):
        html = '<meta property="og:image" content="https://example.com/assets/placeholder.jpg">'

        result = generate_news_data.preview_image_from_html(html, "https://example.com/news/story")

        self.assertIsNone(result)

    def test_choose_cluster_image_prefers_classified_article_image_before_fallback(self):
        articles = [
            {"bucket": "unknown", "imageUrl": "https://cdn.example.com/unknown.jpg"},
            {"bucket": "center", "imageUrl": "https://cdn.example.com/center.jpg"},
        ]

        result = generate_news_data.choose_cluster_image(articles, "story-id")

        self.assertEqual(result, "https://cdn.example.com/center.jpg")

    def test_enrich_article_preview_images_limits_fetches_and_mutates_article_images(self):
        articles = [
            {"url": "https://example.com/unknown", "source": "Unknown Source"},
            {"url": "https://example.com/g1", "source": "G1"},
            {"url": "https://example.com/folha", "source": "Folha de S.Paulo"},
        ]

        def fake_fetch(url, timeout):
            return f"{url}/image.jpg"

        with patch.object(generate_news_data, "fetch_preview_image", side_effect=fake_fetch) as fetch_mock:
            generate_news_data.enrich_article_preview_images(articles, max_fetches=2, timeout=1)

        self.assertEqual(fetch_mock.call_count, 2)
        self.assertEqual(articles[1]["imageUrl"], "https://example.com/g1/image.jpg")
        self.assertEqual(articles[2]["imageUrl"], "https://example.com/folha/image.jpg")
        self.assertNotIn("imageUrl", articles[0])


if __name__ == "__main__":
    unittest.main()
