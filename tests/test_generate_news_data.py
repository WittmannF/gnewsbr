import importlib.util
import unittest
from pathlib import Path


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


if __name__ == "__main__":
    unittest.main()
