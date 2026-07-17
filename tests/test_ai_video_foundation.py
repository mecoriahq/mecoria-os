import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agents.ai_video_insert_plan.run import get_output_path
from core.ai_video_standard import (
    DEFAULT_MODEL,
    approved_image_items,
    build_motion_prompt,
    build_plan,
    evenly_spaced_indexes,
    validate_insert_count,
    validate_plan_identity,
)


class AIVideoFoundationTests(unittest.TestCase):
    def build_context(self):
        return {
            "channel": "hiddenova",
            "video_id": "video_005",
            "run_id": "hiddenova_video_005_v1",
            "topic_title": "Test Topic",
            "outputs": {
                "ai_visual_generation": (
                    "agents/video_visual_pipeline/output/"
                    "hiddenova/video_005/run/ai_visual_generation.json"
                ),
                "ai_visual_qa": (
                    "agents/video_visual_pipeline/output/"
                    "hiddenova/video_005/run/ai_visual_qa.json"
                ),
            },
        }

    def build_generation(self):
        return {
            "channel": "hiddenova",
            "video_id": "video_005",
            "run_id": "hiddenova_video_005_v1",
            "status": "images_ready",
            "generated_images": [
                {
                    "insert_id": f"AI-{index:03d}",
                    "sequence": index,
                    "section_hint": f"Section {index}",
                    "visual_role": "documentary",
                    "relative_path": f"images/ai-{index:03d}.png",
                    "prompt": f"Prompt {index}",
                }
                for index in range(1, 9)
            ],
        }

    def build_qa(self):
        return {
            "channel": "hiddenova",
            "video_id": "video_005",
            "run_id": "hiddenova_video_005_v1",
            "status": "approved",
            "image_checks": [
                {
                    "insert_id": f"AI-{index:03d}",
                    "approved": True,
                }
                for index in range(1, 9)
            ],
        }

    def test_default_model_is_current_omni_preview(self):
        self.assertEqual(
            DEFAULT_MODEL,
            "gemini-omni-flash-preview",
        )

    def test_insert_count_gate(self):
        self.assertEqual(validate_insert_count(4), 4)
        self.assertEqual(validate_insert_count(6), 6)

        with self.assertRaises(ValueError):
            validate_insert_count(3)

        with self.assertRaises(ValueError):
            validate_insert_count(7)

    def test_even_selection_covers_full_story(self):
        self.assertEqual(
            evenly_spaced_indexes(8, 4),
            [0, 2, 5, 7],
        )

    def test_only_approved_images_are_available(self):
        generation = self.build_generation()
        qa = self.build_qa()
        qa["image_checks"][2]["approved"] = False

        items = approved_image_items(generation, qa)

        self.assertEqual(len(items), 7)
        self.assertNotIn(
            "AI-003",
            {item["insert_id"] for item in items},
        )

    def test_motion_prompt_blocks_text_and_audio(self):
        prompt = build_motion_prompt(
            self.build_context(),
            self.build_generation()["generated_images"][0],
        )

        self.assertIn("Do not add text", prompt)
        self.assertIn("dialogue", prompt)
        self.assertIn("music", prompt)
        self.assertIn("sound effects", prompt)

    def test_plan_is_video_specific(self):
        context = self.build_context()
        plan = build_plan(
            context=context,
            generation_data=self.build_generation(),
            qa_data=self.build_qa(),
            count=4,
        )

        validate_plan_identity(plan, context)

        self.assertEqual(plan["video_id"], "video_005")
        self.assertEqual(plan["run_id"], "hiddenova_video_005_v1")
        self.assertEqual(len(plan["items"]), 4)
        self.assertFalse(
            plan["summary"]["production_api_called"]
        )

    def test_plan_rejects_wrong_video(self):
        context = self.build_context()
        generation = self.build_generation()
        generation["video_id"] = "video_004"

        with self.assertRaises(ValueError):
            build_plan(
                context=context,
                generation_data=generation,
                qa_data=self.build_qa(),
                count=4,
            )


    def test_explicit_plan_output_path_is_safe(self):
        context = self.build_context()
        path = get_output_path(
            context=context,
            explicit_path=(
                "records/sandbox/ai_video/"
                "video_005/ai_video_insert_plan.json"
            ),
        )

        self.assertTrue(path.is_absolute())
        self.assertTrue(
            str(path).replace("\\", "/").endswith(
                "records/sandbox/ai_video/"
                "video_005/ai_video_insert_plan.json"
            )
        )

    def test_plan_context_attach_is_opt_in(self):
        source = Path(
            "agents/ai_video_insert_plan/run.py"
        ).read_text(encoding="utf-8")

        self.assertIn(
            '"--attach-context"',
            source,
        )
        self.assertIn(
            "if args.attach_context:",
            source,
        )
        self.assertIn(
            "CONTEXT_CHANGED:",
            source,
        )

    def test_mock_mode_cannot_attach_context(self):
        source = Path(
            "agents/ai_video_generation/run.py"
        ).read_text(encoding="utf-8")

        self.assertIn(
            'if args.mode != "live" and args.attach_context',
            source,
        )
        self.assertIn(
            "Only live generation may be attached",
            source,
        )

    def test_visual_pipeline_records_thumbnail_v2(self):
        source = Path(
            "agents/video_visual_pipeline/run.py"
        ).read_text(encoding="utf-8")

        self.assertIn(
            '"thumbnail_style": "hiddenova_cinematic_v2"',
            source,
        )
        self.assertNotIn(
            '"thumbnail_style": "hiddenova_cinematic_v1"',
            source,
        )


if __name__ == "__main__":
    unittest.main()
