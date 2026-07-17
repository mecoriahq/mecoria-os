import unittest

from core.thumbnail_standard import (
    assert_thumbnail_text,
    build_thumbnail_lines,
    build_thumbnail_overlay_spec,
    build_thumbnail_prompt,
    build_thumbnail_qa_checklist,
    load_thumbnail_standard,
    normalize_thumbnail_text,
    resolve_gold_reference_path,
    validate_thumbnail_text,
)


class ThumbnailStandardTests(unittest.TestCase):
    def test_standard_loads_v2(self):
        standard = load_thumbnail_standard()
        self.assertEqual(
            standard["standard_name"],
            "hiddenova_cinematic_v2"
        )
        self.assertEqual(
            standard["layout"]["text_position"],
            "left"
        )
        self.assertEqual(
            standard["layout"]["subject_position"],
            "right"
        )

    def test_gold_reference_exists(self):
        standard = load_thumbnail_standard()
        path = resolve_gold_reference_path(standard)
        self.assertTrue(path.exists())
        self.assertEqual(
            standard["gold_reference"]["sha256"],
            "c60f1b99c6b58b7c6dde5a7e22323c90a29cc40b2f633da35d09cd0d7f05fd8d"
        )

    def test_valid_thumbnail_text_passes(self):
        result = assert_thumbnail_text("WHEN CABLES SNAP")
        self.assertTrue(result["approved"])
        self.assertEqual(result["word_count"], 3)

    def test_one_word_thumbnail_fails(self):
        result = validate_thumbnail_text("SNAP")
        self.assertFalse(result["approved"])

    def test_lowercase_thumbnail_text_fails(self):
        result = validate_thumbnail_text("When Cables Snap")
        self.assertFalse(result["approved"])
        self.assertFalse(result["uppercase_valid"])

    def test_long_thumbnail_text_fails(self):
        result = validate_thumbnail_text(
            "WHAT HAPPENS WHEN THE CABLE BREAKS"
        )
        self.assertFalse(result["approved"])
        self.assertFalse(result["word_count_valid"])

    def test_normalization(self):
        self.assertEqual(
            normalize_thumbnail_text("two second verdict!"),
            "TWO SECOND VERDICT"
        )

    def test_three_word_line_contract(self):
        lines = build_thumbnail_lines("TWO SECOND VERDICT")
        self.assertEqual(
            [item["text"] for item in lines],
            ["TWO", "SECOND", "VERDICT"]
        )
        self.assertEqual(
            lines[-1]["color_role"],
            "highlight_yellow"
        )

    def test_four_word_line_contract(self):
        lines = build_thumbnail_lines("WHO REALLY MAKES MONEY")
        self.assertEqual(
            [item["text"] for item in lines],
            ["WHO REALLY", "MAKES", "MONEY"]
        )

    def test_overlay_spec_is_locked(self):
        spec = build_thumbnail_overlay_spec()
        self.assertEqual(spec["text_position"], "left")
        self.assertEqual(spec["subject_position"], "right")
        self.assertEqual(
            spec["layout_signature"],
            "oversized_headline_left__dominant_subject_right"
        )
        self.assertGreaterEqual(spec["stroke_width_px"], 14)

    def test_prompt_contains_gold_series_contract(self):
        prompt = build_thumbnail_prompt(
            video_topic="How card payments are approved",
            main_subject="payment terminal with approval glow",
            thumbnail_text="TWO SECOND VERDICT",
            text_position="left"
        )
        self.assertIn("hiddenova_cinematic_v2", prompt)
        self.assertIn("TWO SECOND VERDICT", prompt)
        self.assertIn("oversized stacked ALL CAPS", prompt)
        self.assertIn("subject on the right", prompt)

    def test_qa_checklist(self):
        result = build_thumbnail_qa_checklist(
            "WHEN CABLES SNAP"
        )
        self.assertTrue(result["automatic_text_checks_passed"])
        self.assertTrue(
            result["automatic_checks"]["gold_reference_traceable"]
        )
        self.assertTrue(
            result["automatic_checks"]["text_position_locked_left"]
        )


if __name__ == "__main__":
    unittest.main()
