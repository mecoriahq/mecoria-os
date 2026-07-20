import importlib.util
import sys
import types
import unittest
from pathlib import Path


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
            "hybrid_stock_capacity_precision_target",
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


class HybridStockCapacityPrecisionTests(unittest.TestCase):
    def build_stock_clips(self) -> list[dict]:
        return [
            {
                "candidate_id": f"VIDEO-C{index:03d}",
                "asset_id": f"ASSET-{index:03d}",
                "role": "precision_test",
                "path": (
                    PROJECT_ROOT
                    / "tests"
                    / "fixtures"
                    / f"stock_{index:03d}.mp4"
                ),
                "duration_seconds": 6.01,
            }
            for index in range(1, 5)
        ]

    def test_stock_expansion_consumes_centisecond_capacity(self):
        clips = self.build_stock_clips()
        specs = HYBRID.build_stock_segment_specs(
            stock_clips=clips,
            max_segments_per_clip=1,
        )
        maximum = HYBRID.maximum_stock_spec_duration(
            stock_clips=clips,
            stock_specs=specs,
        )

        self.assertEqual(maximum, 24.04)

        expanded = HYBRID.expand_stock_specs_for_target(
            stock_clips=clips,
            stock_specs=specs,
            target_total_duration=maximum,
        )

        self.assertEqual(
            round(
                sum(
                    float(item["duration_seconds"])
                    for item in expanded
                ),
                2,
            ),
            maximum,
        )
        self.assertEqual(
            {
                float(item["duration_seconds"])
                for item in expanded
            },
            {6.01},
        )

    def test_stock_expansion_still_blocks_true_overflow(self):
        clips = self.build_stock_clips()
        specs = HYBRID.build_stock_segment_specs(
            stock_clips=clips,
            max_segments_per_clip=1,
        )

        with self.assertRaisesRegex(
            ValueError,
            "cannot satisfy one-cycle timeline coverage",
        ):
            HYBRID.expand_stock_specs_for_target(
                stock_clips=clips,
                stock_specs=specs,
                target_total_duration=24.05,
            )

    def test_ai_expansion_consumes_centisecond_capacity(self):
        specs = [
            {
                "segment_id": f"AI-{index:03d}",
                "insert_id": f"AI-{index:03d}",
                "source_path": f"image_{index:03d}.png",
                "source_relative_path": (
                    f"images/image_{index:03d}.png"
                ),
                "duration_seconds": 5.0,
            }
            for index in range(1, 3)
        ]

        expanded = HYBRID.expand_ai_image_specs_for_target(
            ai_specs=specs,
            target_total_duration=10.02,
            maximum_uses_per_image=1,
            maximum_segment_seconds=5.01,
        )

        self.assertEqual(
            round(
                sum(
                    float(item["duration_seconds"])
                    for item in expanded
                ),
                2,
            ),
            10.02,
        )
        self.assertEqual(
            {
                float(item["duration_seconds"])
                for item in expanded
            },
            {5.01},
        )

    def test_duration_epsilon_is_sub_centisecond(self):
        self.assertLess(
            HYBRID.DURATION_EPSILON_SECONDS,
            0.01,
        )
        self.assertGreater(
            HYBRID.DURATION_EPSILON_SECONDS,
            0.0,
        )


if __name__ == "__main__":
    unittest.main()
