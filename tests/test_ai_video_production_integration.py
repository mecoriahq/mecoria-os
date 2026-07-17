import unittest
from pathlib import Path

from core.ai_video_integration import (
    ai_video_context_enabled,
    assert_live_generation_allowed,
    environment_confirmation_matches,
    interleave_ai_specs,
    load_ai_video_production_config,
    mark_ai_video_context_ready,
)


class AIVideoProductionIntegrationTests(unittest.TestCase):
    def enabled_config(self):
        config = load_ai_video_production_config()
        config["orchestrator_enabled"] = True
        config["live_generation_enabled"] = True
        return config

    def test_default_config_is_safe(self):
        config = load_ai_video_production_config()
        self.assertFalse(config["orchestrator_enabled"])
        self.assertFalse(config["live_generation_enabled"])
        self.assertEqual(config["insert_count"], 4)

    def test_default_config_blocks_live_generation(self):
        config = load_ai_video_production_config()

        with self.assertRaises(ValueError):
            assert_live_generation_allowed(
                config=config,
                confirmed=True,
                environ={"MECORIA_AI_VIDEO_LIVE_ENABLED": "true"}
            )

    def test_live_generation_requires_cost_confirmation(self):
        config = self.enabled_config()

        with self.assertRaises(ValueError):
            assert_live_generation_allowed(
                config=config,
                confirmed=False,
                environ={"MECORIA_AI_VIDEO_LIVE_ENABLED": "true"}
            )

    def test_live_generation_requires_environment_confirmation(self):
        config = self.enabled_config()

        with self.assertRaises(ValueError):
            assert_live_generation_allowed(
                config=config,
                confirmed=True,
                environ={}
            )

    def test_live_generation_all_guards_can_pass(self):
        config = self.enabled_config()
        assert_live_generation_allowed(
            config=config,
            confirmed=True,
            environ={"MECORIA_AI_VIDEO_LIVE_ENABLED": "true"}
        )

    def test_environment_confirmation_is_case_insensitive(self):
        config = self.enabled_config()
        self.assertTrue(
            environment_confirmation_matches(
                config=config,
                environ={"MECORIA_AI_VIDEO_LIVE_ENABLED": "TRUE"}
            )
        )

    def test_context_enablement_is_explicit(self):
        context = {"quality_gates": {}}
        self.assertFalse(ai_video_context_enabled(context))
        context["quality_gates"]["ai_video_inserts_enabled"] = True
        self.assertTrue(ai_video_context_enabled(context))

    def test_mark_ready_applies_visual_diversity_gates(self):
        config = self.enabled_config()
        context = {"quality_gates": {}}
        result = mark_ai_video_context_ready(context, config)
        gates = result["quality_gates"]
        self.assertTrue(gates["ai_video_inserts_enabled"])
        self.assertEqual(gates["minimum_ai_insert_count"], 12)
        self.assertEqual(gates["minimum_stock_clip_count"], 30)
        self.assertEqual(gates["maximum_timeline_cycles"], 1)

    def test_ai_specs_are_interleaved_deterministically(self):
        images = [{"segment_id": "AI-001"}, {"segment_id": "AI-002"}]
        videos = [{"segment_id": "AIV-001"}, {"segment_id": "AIV-002"}]
        combined = interleave_ai_specs(images, videos)
        self.assertEqual(
            [item["segment_id"] for item in combined],
            ["AI-001", "AIV-001", "AI-002", "AIV-002"]
        )

    def test_orchestrator_uses_feature_gated_pipeline_runner(self):
        source = Path(
            "agents/media_video_orchestrator/run.py"
        ).read_text(encoding="utf-8")
        self.assertIn("run_ai_video_phase", source)
        self.assertIn("AI_VIDEO_ORCHESTRATOR_ENABLED: false", source)
        self.assertIn("agents/ai_video_pipeline/run.py", source)

    def test_hybrid_assembly_supports_live_ai_video_segments(self):
        source = Path(
            "agents/hybrid_video_assembly/run.py"
        ).read_text(encoding="utf-8")
        self.assertIn('"type": "ai_video"', source)
        self.assertIn("render_ai_video_segment", source)
        self.assertIn(
            "Only live AI video generation can enter assembly.",
            source
        )

    def test_visual_pipeline_uses_context_driven_image_count(self):
        source = Path(
            "agents/video_visual_pipeline/run.py"
        ).read_text(encoding="utf-8")
        self.assertIn("effective_image_count", source)
        self.assertIn("minimum_ai_insert_count", source)
        self.assertIn("default=None", source)


if __name__ == "__main__":
    unittest.main()
