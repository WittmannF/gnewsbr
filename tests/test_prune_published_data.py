import importlib.util
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "prune_published_data.py"
spec = importlib.util.spec_from_file_location("prune_published_data", MODULE_PATH)
prune_published_data = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(prune_published_data)


class PrunePublishedDataTest(unittest.TestCase):
    def test_prunes_only_old_date_partitioned_data_from_dist(self):
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp) / "dist"
            for relative in [
                "data/archive/2026-06-05/story_old.json",
                "data/archive/2026-06-06/story_keep.json",
                "data/archive/2026-07-05/story_new.json",
                "data/article-content/2026-06-05/articles/article_old.json",
                "data/article-content/2026-06-06/articles/article_keep.json",
                "data/article-content/2026-07-05/articles/article_new.json",
                "data/enrichment/newsletters/2026-06-05.json",
                "data/enrichment/newsletters/2026-06-06.md",
                "data/latest.json",
                "data/source-spectrum.json",
            ]:
                path = dist / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("{}")

            result = prune_published_data.prune_published_data(dist, days=30)

            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["newest_date"], "2026-07-05")
            self.assertEqual(result["cutoff_date"], "2026-06-06")
            self.assertFalse((dist / "data/archive/2026-06-05").exists())
            self.assertTrue((dist / "data/archive/2026-06-06").exists())
            self.assertTrue((dist / "data/archive/2026-07-05").exists())
            self.assertFalse((dist / "data/article-content/2026-06-05").exists())
            self.assertTrue((dist / "data/article-content/2026-06-06").exists())
            self.assertTrue((dist / "data/article-content/2026-07-05").exists())
            self.assertFalse((dist / "data/enrichment/newsletters/2026-06-05.json").exists())
            self.assertTrue((dist / "data/enrichment/newsletters/2026-06-06.md").exists())
            self.assertTrue((dist / "data/latest.json").exists())
            self.assertTrue((dist / "data/source-spectrum.json").exists())

    def test_skips_when_dist_has_no_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = prune_published_data.prune_published_data(Path(tmp) / "dist", days=30)

        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["removed"], 0)


if __name__ == "__main__":
    unittest.main()
