"""Offline cost safety tests for the opt-in comparison runner."""
import unittest
from unittest.mock import patch
from engineering.compare_brief_configs import run

def sample():
    def item(outcome, ident):
        return {"cluster_id": ident, "historical_outcome": outcome, "title": "Example",
                "sources": [{"source": "A", "title": "A", "description": "A"},
                            {"source": "B", "title": "B", "description": "B"}]}
    return {"recovered": [item("failed", "f"), item("succeeded", "s")]}

class BudgetGateTests(unittest.TestCase):
    def test_dry_run_never_calls_provider(self):
        with patch("engineering.compare_brief_configs.requests.post") as post:
            result = run(sample(), live=False, key="")
            self.assertEqual(result["planned_calls"], 6)
            post.assert_not_called()

    def test_live_requires_provider_side_cap(self):
        with patch("engineering.compare_brief_configs.requests.post") as post:
            with self.assertRaisesRegex(ValueError, "provider-side"):
                run(sample(), live=True, key="dummy")
            post.assert_not_called()

    def test_unknown_cost_stops_after_one_request(self):
        response = type("Response", (), {
            "status_code": 200,
            "raise_for_status": lambda self: None,
            "json": lambda self: {"choices": [{"message": {"content": '{"summary":"' + 'A'*120 + '"}'}, "finish_reason": "stop"}], "usage": {}},
        })()
        with patch("engineering.compare_brief_configs.requests.post", return_value=response) as post:
            result = run(sample(), live=True, key="dummy", provider_cap_verified=True)
            self.assertEqual(result["attempted"], 1)
            self.assertEqual(result["results"][0]["cost_accounting_status"], "UNKNOWN_STOPPED")
            self.assertEqual(post.call_count, 1)

    def test_nonfinite_cost_stops_after_one_request(self):
        response = type("Response", (), {
            "status_code": 200,
            "raise_for_status": lambda self: None,
            "json": lambda self: {"choices": [{"message": {"content": '{"summary":"' + 'A'*120 + '"}'}, "finish_reason": "stop"}], "usage": {"cost": float("nan")}},
        })()
        with patch("engineering.compare_brief_configs.requests.post", return_value=response) as post:
            result = run(sample(), live=True, key="dummy", provider_cap_verified=True)
            self.assertEqual(result["attempted"], 1)
            self.assertEqual(result["results"][0]["cost_accounting_status"], "UNKNOWN_STOPPED")
            self.assertEqual(post.call_count, 1)

    def test_cumulative_cost_stops_at_budget(self):
        response = type("Response", (), {
            "status_code": 200,
            "raise_for_status": lambda self: None,
            "json": lambda self: {"choices": [{"message": {"content": '{"summary":"' + 'A'*120 + '"}'}, "finish_reason": "stop"}], "usage": {"cost": 5.0}},
        })()
        with patch("engineering.compare_brief_configs.requests.post", return_value=response) as post:
            result = run(sample(), live=True, key="dummy", provider_cap_verified=True)
            self.assertEqual(result["attempted"], 1)
            self.assertEqual(result["results"][0]["cost_accounting_status"], "BUDGET_EXHAUSTED_STOPPED")
            self.assertEqual(post.call_count, 1)

if __name__ == "__main__":
    unittest.main()
