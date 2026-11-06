"""Deterministic tests for immutable historical replay recovery. No network/LLM."""
import unittest
from unittest.mock import patch
from datetime import datetime, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import recover_historical_inputs as recovery


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.entry = {
            "cluster_id": "story_test",
            "batch_utc": "2026-11-05T11",
            "first_reserved_at": "2026-11-05T11:39:25+00:00",
            "outcome": "failed",
        }
        self.primary = recovery.PRE_INFERENCE_REFS["2026-11-05T11"]

    def index(self, cid="story_test", detail="data/clusters/latest/story_test.json"):
        return {"clusters": [{"id": cid, "title": "A title", "detailPath": detail}]}

    def detail(self):
        return {"articles": [
            {"source": "Example", "title": "News", "description": "Description", "url": "https://example.com/a"},
            {"source": "Other", "title": "Other news", "description": "Other description", "url": "https://other.org/b"},
        ]}

    def test_primary_snapshot_is_exactly_labeled(self):
        with patch.object(recovery, "git_json", side_effect=[self.index(), self.detail()]), patch.object(recovery, "candidate_refs") as candidates:
            out = recovery.recover({"clusters": [self.entry]})
        self.assertEqual(len(out["recovered"]), 1)
        self.assertEqual(out["recovered"][0]["snapshot_sha"], self.primary)
        self.assertEqual(out["recovered"][0]["snapshot_provenance"], "primary_pre_inference")
        self.assertEqual(out["recovered"][0]["historical_outcome"], "failed")
        self.assertEqual(len(out["recovered"][0]["sources"]), 2)
        self.assertEqual(out["recovered"][0]["sources"][0]["url"], "https://example.com/a")
        candidates.assert_not_called()

    def test_adjacent_snapshot_is_not_mislabeled_as_exact(self):
        def read(ref, path):
            if path == "public/data/latest.json":
                return self.index("other") if ref == self.primary else self.index()
            return self.detail()
        with patch.object(recovery, "git_json", side_effect=read), patch.object(recovery, "candidate_refs", return_value=["adjacent_sha"]):
            out = recovery.recover({"clusters": [self.entry]})
        self.assertEqual(out["recovered"][0]["snapshot_provenance"], "adjacent_pre_reservation")
        self.assertEqual(out["recovered"][0]["snapshot_sha"], "adjacent_sha")

    def test_missing_is_explicit_not_silently_replaced(self):
        with patch.object(recovery, "git_json", return_value={"clusters": []}), patch.object(recovery, "candidate_refs", return_value=[]):
            out = recovery.recover({"clusters": [self.entry]})
        self.assertEqual(out["recovered"], [])
        self.assertEqual(out["missing"][0]["reason"], "absent_from_bounded_pre_reservation_history")

    def test_invalid_detail_path_is_rejected(self):
        with patch.object(recovery, "git_json", return_value=self.index(detail="../private.json")):
            out = recovery.recover({"clusters": [self.entry]})
        self.assertEqual(out["missing"][0]["reason"], "invalid_detail_path")

    def test_single_publisher_is_not_replayed_as_eligible(self):
        detail = {"articles": [
            {"source": "A", "title": "News", "url": "https://example.com/a"},
            {"source": "A", "title": "News 2", "url": "https://example.com/b"},
        ]}
        with patch.object(recovery, "git_json", side_effect=[self.index(), detail]):
            out = recovery.recover({"clusters": [self.entry]})
        self.assertEqual(out["recovered"], [])
        self.assertEqual(out["missing"][0]["reason"], "insufficient_distinct_sources")

    def test_candidate_history_is_time_bounded(self):
        class Result:
            stdout = "sha1\nsha2\n"
        with patch.object(recovery.subprocess, "run", return_value=Result()) as run:
            refs = recovery.candidate_refs(self.entry["first_reserved_at"])
        self.assertEqual(refs, ["sha1", "sha2"])
        cmd = run.call_args.args[0]
        self.assertIn("--max-count=80", cmd)
        self.assertTrue(any(str(x).startswith("--before=") for x in cmd))
        self.assertTrue(any(str(x).startswith("--after=") for x in cmd))
        self.assertIn("public/data/latest.json", cmd)

    def test_no_untrusted_git_paths(self):
        for path in ("../secret", "public/data/../../private", "data/latest.json"):
            with self.subTest(path=path):
                with self.assertRaises(ValueError):
                    recovery.git_json("some_sha", path)


if __name__ == "__main__":
    unittest.main()
