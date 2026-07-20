import importlib.util
import sys
import types
import unittest
from pathlib import Path

from core.channel_content_policy import (
    build_quality_gates,
    load_editorial_profile,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_hybrid_module():
    previous_output = sys.modules.get("output")
    output_stub = types.ModuleType("output")
    output_stub.save_output = lambda *args, **kwargs: None
    sys.modules["output"] = output_stub

    try:
        source_path = (
            PROJECT_ROOT
            / "agents"
            / "hybrid_video_assembly"
            / "run.py"
        )
        spec = importlib.util.spec_from_file_location(
            "rise_dossier_visual_quality_target",
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
        if previous_output is None:
            sys.modules.pop("output", None)
        else:
            sys.modules["output"] = previous_output


HYBRID = load_hybrid_module()


class RiseDossierVisualQualityTests(unittest.TestCase):
    @staticmethod
    def context() -> dict:
        profile = load_editorial_profile("rise_dossier")
        return {
            "channel": "rise_dossier",
            "quality_gates": build_quality_gates(profile),
        }

    @staticmethod
    def build_fast_timeline() -> list[dict]:
        entries = []
        sequence = 1

        for cycle in range(2):
            for index in range(26):
                entries.append({
                    "type": "stock",
                    "segment_id": (
                        f"STOCK-{index:03d}-S{cycle + 1}"
                    ),
                    "candidate_id": f"STOCK-{index:03d}",
                    "source_relative_path": (
                        f"stock/clip_{index:03d}.mp4"
                    ),
                    "duration_seconds": 6.6,
                    "sequence": sequence,
                    "cycle": 1,
                })
                sequence += 1

            for index in range(22):
                suffix = "" if cycle == 0 else "_M02"
                entries.append({
                    "type": "ai_insert",
                    "segment_id": f"AI-{index:03d}{suffix}",
                    "insert_id": f"AI-{index:03d}",
                    "source_relative_path": (
                        f"images/image_{index:03d}.png"
                    ),
                    "duration_seconds": 6.6,
                    "sequence": sequence,
                    "cycle": 1,
                })
                sequence += 1

        return entries

    def test_profile_sets_balanced_visual_capacity(self):
        gates = self.context()["quality_gates"]

        self.assertEqual(gates["minimum_ai_insert_count"], 22)
        self.assertEqual(
            gates["minimum_hybrid_stock_clip_count"],
            26,
        )
        self.assertEqual(
            gates["minimum_combined_visual_asset_count"],
            48,
        )
        self.assertEqual(
            gates["minimum_stock_duration_seconds"],
            300.0,
        )
        self.assertEqual(
            gates["maximum_stock_segments_per_clip"],
            2,
        )

    def test_eight_second_ai_cap_has_long_form_capacity(self):
        specs = [
            {
                "segment_id": f"AI-{index:03d}",
                "insert_id": f"AI-{index:03d}",
                "source_relative_path": (
                    f"images/image_{index:03d}.png"
                ),
                "duration_seconds": 5.0,
            }
            for index in range(22)
        ]

        expanded = HYBRID.expand_ai_image_specs_for_target(
            ai_specs=specs,
            target_total_duration=352.0,
            maximum_uses_per_image=2,
            maximum_segment_seconds=8.0,
        )

        self.assertEqual(len(expanded), 44)
        self.assertGreaterEqual(
            sum(
                float(item["duration_seconds"])
                for item in expanded
            ),
            352.0,
        )
        self.assertTrue(
            all(
                float(item["duration_seconds"]) <= 8.0
                for item in expanded
            )
        )

    def test_fast_timeline_passes_pacing_qa(self):
        report = HYBRID.validate_visual_pacing(
            context=self.context(),
            timeline_entries=self.build_fast_timeline(),
            audio_duration=630.0,
        )

        self.assertEqual(report["status"], "approved")
        self.assertLessEqual(
            report["metrics"][
                "average_visual_hold_seconds"
            ],
            6.75,
        )
        self.assertLessEqual(
            report["metrics"]["p95_visual_hold_seconds"],
            8.0,
        )
        self.assertGreaterEqual(
            report["metrics"][
                "minimum_actual_ai_reuse_gap_seconds"
            ],
            90.0,
        )
        self.assertEqual(
            report["metrics"][
                "maximum_actual_ai_image_uses"
            ],
            2,
        )

    def test_slow_timeline_is_blocked_before_render(self):
        slow_entries = [
            {
                "type": "stock",
                "segment_id": f"SLOW-{index:03d}",
                "source_relative_path": (
                    f"stock/slow_{index:03d}.mp4"
                ),
                "duration_seconds": 8.0,
                "sequence": index + 1,
                "cycle": 1,
            }
            for index in range(80)
        ]

        with self.assertRaisesRegex(
            ValueError,
            "Visual pacing QA rejected",
        ):
            HYBRID.validate_visual_pacing(
                context=self.context(),
                timeline_entries=slow_entries,
                audio_duration=630.0,
            )

    def test_hiddenova_without_profile_gate_is_unchanged(self):
        report = HYBRID.validate_visual_pacing(
            context={
                "channel": "hiddenova",
                "quality_gates": {},
            },
            timeline_entries=[
                {
                    "type": "stock",
                    "segment_id": "SLOW",
                    "source_relative_path": "slow.mp4",
                    "duration_seconds": 20.0,
                    "sequence": 1,
                    "cycle": 1,
                }
            ],
            audio_duration=10.0,
        )

        self.assertEqual(report["status"], "not_required")


if __name__ == "__main__":
    unittest.main()
