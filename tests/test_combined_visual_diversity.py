import importlib.util
import sys
import types
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_module(
    module_name: str,
    source_path: Path,
    stub_output: bool = False,
):
    previous_output = sys.modules.get("output")

    if stub_output:
        output_stub = types.ModuleType("output")
        output_stub.save_output = lambda *args, **kwargs: None
        sys.modules["output"] = output_stub

    try:
        spec = importlib.util.spec_from_file_location(
            module_name,
            source_path,
        )
        if spec is None or spec.loader is None:
            raise RuntimeError(
                f"Could not load module: {source_path}"
            )

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if stub_output:
            if previous_output is None:
                sys.modules.pop("output", None)
            else:
                sys.modules["output"] = previous_output


HYBRID_MODULE = load_module(
    "hybrid_video_assembly_test_target",
    PROJECT_ROOT
    / "agents"
    / "hybrid_video_assembly"
    / "run.py",
    stub_output=True,
)
STOCK_MODULE = load_module(
    "video_stock_pipeline_test_target",
    PROJECT_ROOT
    / "agents"
    / "video_stock_pipeline"
    / "run.py",
)

expand_ai_image_specs_for_target = (
    HYBRID_MODULE.expand_ai_image_specs_for_target
)
maximum_stock_spec_duration = (
    HYBRID_MODULE.maximum_stock_spec_duration
)
build_stock_qa = STOCK_MODULE.build_stock_qa
resolve_stock_qa_thresholds = (
    STOCK_MODULE.resolve_stock_qa_thresholds
)


class CombinedVisualDiversityTests(unittest.TestCase):
    def test_hybrid_threshold_uses_ai_visual_count(self):
        context = {
            "quality_gates": {
                "minimum_stock_clip_count": 30,
                "minimum_ai_insert_count": 12,
                "require_ai_visuals": True,
                "maximum_single_stock_clip_share": 0.08,
            }
        }
        thresholds = resolve_stock_qa_thresholds(context)
        self.assertEqual(
            thresholds["minimum_stock_clip_count"],
            18,
        )
        self.assertEqual(
            thresholds["minimum_combined_visual_asset_count"],
            30,
        )
        self.assertEqual(
            thresholds["maximum_stock_source_clip_share"],
            0.15,
        )

    def test_stock_qa_accepts_eighteen_plus_twelve_ai(self):
        items = []
        for index in range(18):
            items.append({
                "candidate_id": f"C{index:03d}",
                "relative_path": f"clip_{index:03d}.mp4",
                "duration_seconds": 15.0,
                "role": f"role_{index % 6}",
                "storyblocks_id": f"SBV-{index:06d}",
                "classification_confidence": "medium",
                "license_status": "public_use_confirmed",
            })

        manifest = {
            "items": items,
            "total_duration_seconds": 270.0,
        }
        context = {
            "channel": "hiddenova",
            "video_id": "video_005",
            "run_id": "hiddenova_video_005_v1",
            "quality_gates": {
                "minimum_stock_clip_count": 30,
                "minimum_ai_insert_count": 12,
                "require_ai_visuals": True,
                "maximum_single_stock_clip_share": 0.08,
                "minimum_stock_duration_seconds": 180,
                "minimum_distinct_stock_roles": 5,
            },
        }

        qa = build_stock_qa(manifest, context)
        self.assertEqual(qa["status"], "approved")
        self.assertEqual(
            qa["summary"]["diversity_mode"],
            "hybrid_visual_diversity",
        )
        self.assertEqual(
            qa["summary"]["expected_combined_visual_count"],
            30,
        )

    def test_ai_images_expand_with_two_motion_variants(self):
        specs = []
        for index in range(12):
            specs.append({
                "segment_id": f"AI-{index:03d}",
                "duration_seconds": 5.0,
                "source_path": f"image_{index:03d}.png",
            })

        expanded = expand_ai_image_specs_for_target(
            ai_specs=specs,
            target_total_duration=220.0,
        )
        self.assertEqual(len(expanded), 24)
        self.assertGreaterEqual(
            sum(item["duration_seconds"] for item in expanded),
            220.0,
        )
        self.assertEqual(
            len({item["segment_id"] for item in expanded}),
            24,
        )
        self.assertTrue(
            all(item["duration_seconds"] <= 12.0 for item in expanded)
        )

    def test_hybrid_repetition_gate_uses_combined_thresholds(self):
        stock_clips = [
            {
                "candidate_id": f"C{index:03d}",
                "duration_seconds": 15.0,
            }
            for index in range(18)
        ]
        stock_specs = [
            {
                "candidate_id": item["candidate_id"],
                "duration_seconds": 8.0,
            }
            for item in stock_clips
        ]
        ai_specs = [
            {
                "segment_id": f"AI-{index:03d}",
                "source_relative_path": f"image_{index:03d}.png",
                "duration_seconds": 30.0,
            }
            for index in range(12)
        ]
        context = {
            "quality_gates": {
                "minimum_stock_clip_count": 30,
                "minimum_ai_insert_count": 12,
                "require_ai_visuals": True,
                "maximum_single_stock_clip_share": 0.08,
                "minimum_timeline_cycle_coverage": 1.0,
                "maximum_timeline_cycles": 1,
            }
        }

        result = HYBRID_MODULE.validate_stock_repetition(
            context=context,
            stock_clips=stock_clips,
            stock_specs=stock_specs,
            ai_specs=ai_specs,
            audio_duration=495.0,
        )

        self.assertEqual(
            result["effective_minimum_stock_clip_count"],
            18,
        )
        self.assertEqual(
            result["effective_maximum_stock_source_share"],
            0.15,
        )
        self.assertEqual(
            result["combined_unique_visual_count"],
            30,
        )
        self.assertEqual(
            result["diversity_mode"],
            "hybrid_visual_diversity",
        )


    def test_stock_capacity_respects_non_overlapping_limits(self):
        clips = [
            {"candidate_id": "C001", "duration_seconds": 20.0}
        ]
        specs = [
            {
                "candidate_id": "C001",
                "start_seconds": 0.0,
                "duration_seconds": 5.0,
            },
            {
                "candidate_id": "C001",
                "start_seconds": 10.0,
                "duration_seconds": 5.0,
            },
        ]
        self.assertEqual(
            maximum_stock_spec_duration(clips, specs),
            16.0,
        )


if __name__ == "__main__":
    unittest.main()
