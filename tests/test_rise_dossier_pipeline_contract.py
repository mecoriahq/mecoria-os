import json
import unittest
from pathlib import Path


class RiseDossierPipelineContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[1]
        cls.orchestrator = (
            cls.root / "agents" / "media_video_orchestrator" / "run.py"
        ).read_text(encoding="utf-8-sig")
        cls.visual = (
            cls.root / "agents" / "video_visual_pipeline" / "run.py"
        ).read_text(encoding="utf-8-sig")
        cls.research = (
            cls.root / "agents" / "factual_research" / "run.py"
        ).read_text(encoding="utf-8-sig")
        cls.seo_prompt = (
            cls.root / "agents" / "seo" / "prompt.py"
        ).read_text(encoding="utf-8-sig")
        cls.seo_run = (
            cls.root / "agents" / "seo" / "run.py"
        ).read_text(encoding="utf-8-sig")
        cls.config = json.loads(
            (cls.root / "config" / "channels" / "rise_dossier.json")
            .read_text(encoding="utf-8-sig")
        )

    def test_factual_agents_are_in_orchestrator(self):
        for value in (
            "agents/factual_research/run.py",
            "agents/claims_ledger/run.py",
            "agents/fact_risk_qa/run.py",
        ):
            self.assertIn(value, self.orchestrator)
        self.assertIn(
            "invalidate_factual_research_outputs",
            self.orchestrator,
        )
        self.assertIn(
            "max_factual_research_revision_attempts",
            self.orchestrator,
        )

    def test_research_uses_web_search_and_structured_output(self):
        self.assertIn('"type": "web_search"', self.research)
        self.assertIn('"type": "json_schema"', self.research)
        self.assertIn("response_used_web_search", self.research)
        self.assertIn(
            '"web_search_call.action.sources"',
            self.research,
        )

    def test_seo_uses_channel_editorial_profile(self):
        self.assertIn(
            "load_editorial_profile",
            self.seo_run,
        )
        self.assertIn(
            "Thumbnail Standard: {thumbnail_standard}",
            self.seo_prompt,
        )
        self.assertIn(
            "Never fabricate evidence",
            self.seo_prompt,
        )

    def test_visual_pipeline_loads_channel_standard(self):
        self.assertIn(
            'load_thumbnail_standard(\n        channel=context["channel"]',
            self.visual,
        )
        self.assertIn("require_channel_thumbnail_standard", self.visual)
        self.assertIn("no fabricated evidence", self.visual.lower())

    def test_production_remains_disabled_until_dry_run(self):
        self.assertFalse(self.config["production_enabled"])
        self.assertEqual(
            self.config["blockers"],
            ["first_dry_run_required"],
        )
        self.assertEqual(
            self.config["analytics"]["next_action"],
            "first_full_dry_run",
        )


if __name__ == "__main__":
    unittest.main()
