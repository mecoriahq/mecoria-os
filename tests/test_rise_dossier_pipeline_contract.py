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
        cls.selector = (
            cls.root / "agents" / "content_idea_selector" / "run.py"
        ).read_text(encoding="utf-8-sig")
        cls.hybrid = (
            cls.root / "agents" / "hybrid_video_assembly" / "run.py"
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
        self.assertIn(
            "Distribute the inserts across every named script section",
            self.visual,
        )

    def test_visual_quality_profile_is_authoritative(self):
        self.assertIn(
            "quality_gates.update(\n"
            "        build_quality_gates(editorial_profile)",
            self.selector,
        )
        self.assertIn(
            "build_visual_quality_gates",
            self.orchestrator,
        )
        self.assertIn(
            "validate_visual_pacing",
            self.hybrid,
        )
        self.assertIn(
            "maximum_ai_image_segment_seconds",
            self.hybrid,
        )

    def test_production_is_enabled_but_manual_start_only(self):
        self.assertEqual(self.config["status"], "active")
        self.assertTrue(self.config["production_enabled"])
        self.assertFalse(
            self.config["pipeline"]["auto_create_next_video"]
        )
        self.assertFalse(
            self.config["pipeline"]["automatic_public_release"]
        )
        self.assertEqual(self.config["blockers"], [])
        self.assertEqual(
            self.config["analytics"]["next_action"],
            "first_topic_selection",
        )


if __name__ == "__main__":
    unittest.main()
