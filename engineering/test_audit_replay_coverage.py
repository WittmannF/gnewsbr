"""Offline tests for replay manifest coverage auditing."""
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit_replay_coverage import summarize


class AuditTests(unittest.TestCase):
    def test_counts_and_provenance(self):
        data = {
            "total_requested": 3,
            "recovered": [
                {"cluster_id": "a", "historical_outcome": "failed",
                 "snapshot_provenance": "primary_pre_inference", "sources": [{}]},
                {"cluster_id": "b", "historical_outcome": "succeeded",
                 "snapshot_provenance": "adjacent_pre_reservation", "sources": [{}, {}]},
            ],
            "missing": [{"cluster_id": "c", "reason": "absent_from_bounded_pre_reservation_history"}],
        }
        result = summarize(data)
        self.assertEqual(result["recovered"], 2)
        self.assertEqual(result["recovered_outcomes"], {"failed": 1, "succeeded": 1})
        self.assertEqual(result["article_count_max"], 2)
        self.assertEqual(result["replay_equivalence"], "not_proven")
        self.assertNotIn("sources", result)

    def test_canonical_manifest_rejects_wrong_id_and_outcome(self):
        manifest = {"clusters": [{"cluster_id": "a", "outcome": "failed"}]}
        valid = {"total_requested": 1, "recovered": [
            {"cluster_id": "a", "historical_outcome": "failed",
             "snapshot_provenance": "primary_pre_inference", "sources": [{}]}
        ], "missing": []}
        self.assertEqual(summarize(valid, manifest)["recovered"], 1)
        for field, value in (("cluster_id", "different"), ("historical_outcome", "succeeded")):
            with self.subTest(field=field):
                import copy
                tampered = copy.deepcopy(valid)
                tampered["recovered"][0][field] = value
                with self.assertRaises(ValueError):
                    summarize(tampered, manifest)

    def test_missing_outcome_stratification(self):
        manifest = {"clusters": [
            {"cluster_id": "a", "outcome": "failed"},
            {"cluster_id": "b", "outcome": "succeeded"},
            {"cluster_id": "c", "outcome": "failed"},
        ]}
        data = {"total_requested": 3, "recovered": [
            {"cluster_id": "b", "historical_outcome": "succeeded",
             "snapshot_provenance": "primary_pre_inference", "sources": [{}, {}]}
        ], "missing": [
            {"cluster_id": "a", "reason": "insufficient_distinct_sources"},
            {"cluster_id": "c", "reason": "absent_from_bounded_pre_reservation_history"},
        ]}
        result = summarize(data, manifest)
        self.assertEqual(result["missing_outcomes"], {"failed": 2})
        self.assertEqual(result["recovered_outcomes"], {"succeeded": 1})
        self.assertNotIn("title", result)

    def test_missing_or_duplicate_id_is_rejected(self):
        for missing in ([], [{"cluster_id": "a", "reason": "absent"}]):
            with self.subTest(missing=missing):
                data = {"total_requested": 2,
                        "recovered": [{"cluster_id": "a", "snapshot_provenance": "primary_pre_inference",
                                       "sources": [{}]}], "missing": missing}
                with self.assertRaises(ValueError):
                    summarize(data)

    def test_unknown_provenance_is_rejected(self):
        with self.assertRaises(ValueError):
            summarize({"total_requested": 1, "recovered": [
                {"cluster_id": "a", "snapshot_provenance": "present_day", "sources": [{}]}
            ], "missing": []})

    def test_empty_recovered_source_is_rejected(self):
        with self.assertRaises(ValueError):
            summarize({"total_requested": 1, "recovered": [
                {"cluster_id": "a", "snapshot_provenance": "primary_pre_inference", "sources": []}
            ], "missing": []})


if __name__ == "__main__":
    unittest.main()
