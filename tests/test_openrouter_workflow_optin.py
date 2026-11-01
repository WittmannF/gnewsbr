"""Make legacy paid synthesis manual-only and allow explicit pause of homepage briefs."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class OpenRouterWorkflowOptInTests(unittest.TestCase):
    def test_scheduled_synthesis_requires_exact_true(self):
        workflow = (ROOT / ".github/workflows/news-synthesis.yml").read_text(encoding="utf-8")
        self.assertIn(
            "if: github.event_name == 'workflow_dispatch' || vars.ENABLE_GNEWSBR_SYNTHESIS == 'true'",
            workflow,
        )
        self.assertNotIn("vars.ENABLE_GNEWSBR_SYNTHESIS != 'false'", workflow)

    def test_pages_briefs_have_an_explicit_opt_out(self):
        workflow = (ROOT / ".github/workflows/pages.yml").read_text(encoding="utf-8")
        self.assertIn(
            "if: vars.ENABLE_GNEWSBR_SYNTHESIS != 'false'",
            workflow,
        )
        self.assertIn("scripts/summarize_home.py", workflow)
        self.assertNotIn("scripts/generate_news_synthesis.py", workflow)


if __name__ == "__main__":
    unittest.main()
