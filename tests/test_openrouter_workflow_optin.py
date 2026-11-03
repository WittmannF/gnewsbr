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

    def test_briefs_have_dedicated_schedule_and_explicit_opt_out(self):
        pages = (ROOT / ".github/workflows/pages.yml").read_text(encoding="utf-8")
        briefs = (ROOT / ".github/workflows/top-15-summaries.yml").read_text(encoding="utf-8")
        self.assertIn("cron: '7 * * * *'", pages)
        self.assertNotIn("scripts/summarize_home.py", pages)
        self.assertIn("cron: '20 11,17,23 * * *'", briefs)
        self.assertIn("vars.ENABLE_GNEWSBR_SYNTHESIS != 'false'", briefs)
        self.assertIn("scripts/summarize_home.py --max-new 15", briefs)
        self.assertNotIn("scripts/generate_news_synthesis.py", briefs)


if __name__ == "__main__":
    unittest.main()
