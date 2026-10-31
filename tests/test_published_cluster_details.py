"""Regression test for the broken-homepage HTTP 404 incident."""
import json
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from check_published_cluster_details import missing_details


class PublishedDetailsTest(unittest.TestCase):
    def test_detects_missing_cluster_json(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            index = root / "data/latest.json"
            index.parent.mkdir(parents=True)
            index.write_text(json.dumps({"clusters": [
                {"id": "story_1", "detailPath": "data/clusters/latest/story_1.json"}
            ]}))
            self.assertEqual(
                missing_details(root),
                ["data/clusters/latest/story_1.json"],
            )
            detail = root / "data/clusters/latest/story_1.json"
            detail.parent.mkdir(parents=True)
            detail.write_text('{"id":"story_1","articles":[]}')
            self.assertEqual(missing_details(root), [])


if __name__ == "__main__":
    unittest.main()
