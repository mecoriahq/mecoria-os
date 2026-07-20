import importlib.util
import sys
import types
import unittest
from collections import Counter
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
            "hybrid_long_form_capacity_target",
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


class HybridLongFormCapacityTests(unittest.TestCase):
    def build_specs(self) -> list[dict]:
        return [
            {
                "segment_id": f"AI-{index:03d}",
                "insert_id": f"AI-{index:03d}",
                "source_path": f"image_{index:03d}.png",
                "source_relative_path": (
                    f"images/image_{index:03d}.png"
                ),
                "duration_seconds": 10.0,
            }
            for index in range(12)
        ]

    def test_theranos_capacity_uses_two_variants_only(self):
        expanded = HYBRID.expand_ai_image_specs_for_target(
            ai_specs=self.build_specs(),
            target_total_duration=298.16,
        )

        self.assertEqual(len(expanded), 24)
        self.assertGreaterEqual(
            round(
                sum(
                    float(item["duration_seconds"])
                    for item in expanded
                ),
                2,
            ),
            298.16,
        )
        self.assertTrue(
            all(
                float(item["duration_seconds"])
                <= HYBRID.MAX_AI_IMAGE_SEGMENT_SECONDS
                for item in expanded
            )
        )
        self.assertEqual(
            {
                int(item["motion_variant"])
                for item in expanded
            },
            {1, 2},
        )

        source_counts = Counter(
            str(item["source_relative_path"])
            for item in expanded
        )
        self.assertEqual(
            set(source_counts.values()),
            {2},
        )

    def test_capacity_limit_still_blocks_oversized_target(self):
        with self.assertRaisesRegex(
            ValueError,
            "cannot satisfy one-cycle timeline coverage",
        ):
            HYBRID.expand_ai_image_specs_for_target(
                ai_specs=self.build_specs(),
                target_total_duration=312.5,
            )

    def test_security_constants_remain_unchanged(self):
        self.assertEqual(
            HYBRID.MAX_ADAPTIVE_STOCK_SEGMENT_SECONDS,
            8,
        )
        self.assertEqual(
            HYBRID.TIMELINE_TAIL_PADDING_SECONDS,
            3.0,
        )
        self.assertEqual(
            HYBRID.MAX_AI_IMAGE_SEGMENT_SECONDS,
            13.0,
        )


if __name__ == "__main__":
    unittest.main()
