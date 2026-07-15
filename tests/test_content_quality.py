import unittest

from core.content_quality import (
    count_script_narration_words,
    evaluate_script_word_count,
)


class ContentQualityTests(unittest.TestCase):
    def build_script(
        self,
        word_count: int
    ) -> dict:
        words = " ".join(
            f"word{index}"
            for index in range(word_count)
        )

        return {
            "script": {
                "hook": {
                    "narration": words
                },
                "introduction": {
                    "narration": ""
                },
                "main_sections": [],
                "conclusion": {
                    "narration": ""
                },
                "call_to_action": {
                    "narration": ""
                }
            }
        }

    def test_valid_script_passes(self):
        result = evaluate_script_word_count(
            self.build_script(1000),
            minimum=800,
            maximum=1300
        )

        self.assertTrue(result["approved"])

    def test_long_script_fails(self):
        result = evaluate_script_word_count(
            self.build_script(2266),
            minimum=800,
            maximum=1300
        )

        self.assertFalse(result["approved"])

    def test_short_script_fails(self):
        result = evaluate_script_word_count(
            self.build_script(500),
            minimum=800,
            maximum=1300
        )

        self.assertFalse(result["approved"])

    def test_visual_directions_are_not_counted(self):
        data = self.build_script(900)
        data["script"]["main_sections"] = [
            {
                "title": "Section",
                "narration": "",
                "visual_direction": "visual " * 500
            }
        ]

        self.assertEqual(
            count_script_narration_words(data),
            900
        )


if __name__ == "__main__":
    unittest.main()
