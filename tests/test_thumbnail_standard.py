import unittest

from core.thumbnail_standard import (
    assert_thumbnail_text,
    build_thumbnail_prompt,
    build_thumbnail_qa_checklist,
    load_thumbnail_standard,
    normalize_thumbnail_text,
    validate_thumbnail_text,
)


class ThumbnailStandardTests(unittest.TestCase):
    def test_standard_loads(self):
        standard = load_thumbnail_standard()

        self.assertEqual(
            standard["standard_name"],
            "hiddenova_cinematic_v1"
        )

    def test_valid_thumbnail_text_passes(self):
        result = assert_thumbnail_text(
            "WHEN CABLES SNAP"
        )

        self.assertTrue(result["approved"])
        self.assertEqual(result["word_count"], 3)

    def test_lowercase_thumbnail_text_fails(self):
        result = validate_thumbnail_text(
            "When Cables Snap"
        )

        self.assertFalse(result["approved"])
        self.assertFalse(
            result["uppercase_valid"]
        )

    def test_long_thumbnail_text_fails(self):
        result = validate_thumbnail_text(
            "WHAT HAPPENS WHEN THE CABLE BREAKS"
        )

        self.assertFalse(result["approved"])
        self.assertFalse(
            result["word_count_valid"]
        )

    def test_normalization(self):
        self.assertEqual(
            normalize_thumbnail_text(
                "when cables snap!"
            ),
            "WHEN CABLES SNAP"
        )

    def test_prompt_contains_standard(self):
        prompt = build_thumbnail_prompt(
            video_topic=(
                "How the Internet Survives "
                "a Broken Cable Under the Ocean"
            ),
            main_subject=(
                "snapped undersea fiber optic cable"
            ),
            thumbnail_text="WHEN CABLES SNAP",
            text_position="left"
        )

        self.assertIn(
            "hiddenova_cinematic_v1",
            prompt
        )
        self.assertIn(
            "WHEN CABLES SNAP",
            prompt
        )
        self.assertIn(
            "one dominant main subject",
            prompt
        )

    def test_qa_checklist(self):
        result = build_thumbnail_qa_checklist(
            "WHEN CABLES SNAP"
        )

        self.assertTrue(
            result[
                "automatic_text_checks_passed"
            ]
        )


if __name__ == "__main__":
    unittest.main()
