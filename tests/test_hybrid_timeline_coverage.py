import sys
import unittest
from pathlib import Path

AGENT_DIR = Path("agents/hybrid_video_assembly").resolve()
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

from agents.hybrid_video_assembly.run import (
    PROJECT_ROOT,
    TIMELINE_TAIL_PADDING_SECONDS,
    build_stock_segment_specs,
    validate_stock_repetition,
)


class HybridTimelineCoverageTests(unittest.TestCase):
    def build_stock_clips(self):
        durations = [
            10.0, 20.39, 21.12, 10.03, 8.17,
            18.12, 18.07, 29.03, 20.32, 10.28,
            8.64, 16.97, 23.72, 8.84, 12.88,
            16.48, 7.16, 10.24, 6.64, 20.09,
            15.8, 17.13, 24.12, 11.58, 26.73,
            11.01, 16.27, 10.84, 36.25, 9.88,
        ]
        clips = []

        for index, duration in enumerate(durations, start=1):
            clips.append({
                "asset_id": f"STOCK-{index:03d}",
                "candidate_id": f"VIDEO_005-C{index:03d}",
                "role": f"role_{(index - 1) % 6}",
                "path": (
                    PROJECT_ROOT
                    / "assets"
                    / "stock"
                    / "tests"
                    / f"clip_{index:03d}.mp4"
                ),
                "duration_seconds": duration,
                "risk_level": "low",
            })

        return clips

    @staticmethod
    def context():
        return {
            "quality_gates": {
                "minimum_stock_clip_count": 30,
                "maximum_single_stock_clip_share": 0.08,
                "minimum_timeline_cycle_coverage": 1.0,
                "maximum_timeline_cycles": 1,
            }
        }

    def test_legacy_fixed_segments_fail_one_cycle_gate(self):
        stock_clips = self.build_stock_clips()
        stock_specs = build_stock_segment_specs(
            stock_clips=stock_clips,
            max_segments_per_clip=3,
        )
        ai_specs = [
            {"duration_seconds": 5.0}
            for _ in range(12)
        ]

        with self.assertRaises(ValueError):
            validate_stock_repetition(
                context=self.context(),
                stock_clips=stock_clips,
                stock_specs=stock_specs,
                ai_specs=ai_specs,
                audio_duration=495.38,
            )

    def test_adaptive_segments_cover_audio_without_reuse(self):
        stock_clips = self.build_stock_clips()
        ai_specs = [
            {"duration_seconds": 5.0}
            for _ in range(12)
        ]
        target_stock_duration = (
            495.38
            + TIMELINE_TAIL_PADDING_SECONDS
            - sum(item["duration_seconds"] for item in ai_specs)
        )
        stock_specs = build_stock_segment_specs(
            stock_clips=stock_clips,
            max_segments_per_clip=3,
            target_total_duration=target_stock_duration,
        )
        report = validate_stock_repetition(
            context=self.context(),
            stock_clips=stock_clips,
            stock_specs=stock_specs,
            ai_specs=ai_specs,
            audio_duration=495.38,
        )

        self.assertEqual(report["stock_timeline_cycles"], 1)
        self.assertGreaterEqual(
            report["stock_cycle_coverage_ratio"],
            1.0,
        )
        self.assertEqual(
            report["timeline_target_duration_seconds"],
            498.38,
        )

        grouped = {}
        for spec in stock_specs:
            grouped.setdefault(
                spec["candidate_id"],
                [],
            ).append(spec)
            self.assertLessEqual(
                spec["duration_seconds"],
                8.0,
            )

        for specs in grouped.values():
            self.assertLessEqual(len(specs), 3)
            specs.sort(key=lambda item: item["start_seconds"])
            for current, following in zip(specs, specs[1:]):
                self.assertLessEqual(
                    current["start_seconds"]
                    + current["duration_seconds"],
                    following["start_seconds"] + 0.01,
                )


if __name__ == "__main__":
    unittest.main()
