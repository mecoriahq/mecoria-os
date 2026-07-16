import unittest

from core.content_quality import evaluate_duration_seconds
from agents.video_audio_pipeline.run import (
    build_actual_chapters,
    format_chapter_time,
)
from agents.video_publisher.run import (
    build_final_description,
    normalize_actual_chapters,
    strip_estimated_chapters,
)


class DurationGateTests(unittest.TestCase):
    def test_duration_boundaries(self):
        cases = [
            (479.99, False, "too_short"),
            (480, True, "within_range"),
            (720, True, "within_range"),
            (720.01, False, "too_long"),
        ]

        for actual, approved, reason in cases:
            with self.subTest(actual=actual):
                result = evaluate_duration_seconds(actual)
                self.assertEqual(result["approved"], approved)
                self.assertEqual(result["reason"], reason)

    def test_chapter_time_format(self):
        self.assertEqual(format_chapter_time(0), "0:00")
        self.assertEqual(format_chapter_time(65.99), "1:05")
        self.assertEqual(format_chapter_time(3665), "1:01:05")


class ActualChapterTests(unittest.TestCase):
    def test_actual_chapters_use_section_start_times(self):
        sections = [
            {
                "sequence": 1,
                "section_type": "hook",
                "title": "Hook",
                "start_seconds": 0,
            },
            {
                "sequence": 2,
                "section_type": "introduction",
                "title": "Introduction",
                "start_seconds": 20,
            },
            {
                "sequence": 3,
                "section_type": "main_section",
                "title": "Authorization",
                "start_seconds": 75.8,
            },
            {
                "sequence": 4,
                "section_type": "main_section",
                "title": "Risk Checks",
                "start_seconds": 245.2,
            },
            {
                "sequence": 5,
                "section_type": "conclusion",
                "title": "What Happens Next",
                "start_seconds": 540.9,
            },
        ]

        chapters = build_actual_chapters(
            sections=sections,
            total_duration_seconds=600,
        )

        self.assertEqual(
            [(item["time"], item["title"]) for item in chapters],
            [
                ("0:00", "Introduction"),
                ("1:15", "Authorization"),
                ("4:05", "Risk Checks"),
                ("9:00", "What Happens Next"),
            ],
        )

    def test_too_few_actual_chapters_are_blocked(self):
        sections = [
            {
                "sequence": 1,
                "section_type": "main_section",
                "title": "Only Section",
                "start_seconds": 120,
            }
        ]

        with self.assertRaisesRegex(ValueError, "fewer than three"):
            build_actual_chapters(
                sections=sections,
                total_duration_seconds=600,
            )


class PublisherChapterTests(unittest.TestCase):
    def test_estimated_chapters_are_removed(self):
        description = (
            "Payment systems explained.\n\n"
            "Chapters:\n"
            "0:00 Old intro\n"
            "1:30 Old chapter\n\n"
            "Subscribe for more."
        )

        cleaned = strip_estimated_chapters(description)

        self.assertNotIn("0:00 Old intro", cleaned)
        self.assertNotIn("1:30 Old chapter", cleaned)
        self.assertNotIn("Chapters:", cleaned)
        self.assertIn("Payment systems explained.", cleaned)
        self.assertIn("Subscribe for more.", cleaned)

    def test_final_description_uses_actual_chapters(self):
        chapters = [
            {"time": "0:00", "title": "Introduction"},
            {"time": "1:15", "title": "Authorization"},
            {"time": "4:05", "title": "Risk Checks"},
        ]

        normalized = normalize_actual_chapters(chapters)
        description = build_final_description(
            base_description=(
                "Payment systems explained.\n\n"
                "Timestamps:\n"
                "0:00 Estimated intro\n"
                "2:00 Estimated middle"
            ),
            chapters=normalized,
        )

        self.assertIn("0:00 Introduction", description)
        self.assertIn("1:15 Authorization", description)
        self.assertIn("4:05 Risk Checks", description)
        self.assertNotIn("Estimated intro", description)
        self.assertNotIn("Estimated middle", description)
        self.assertEqual(description.count("Chapters:"), 1)

    def test_first_chapter_must_start_at_zero(self):
        with self.assertRaisesRegex(ValueError, "must start at 0:00"):
            normalize_actual_chapters([
                {"time": "0:10", "title": "Late Start"},
                {"time": "1:10", "title": "Section Two"},
                {"time": "2:10", "title": "Section Three"},
            ])


if __name__ == "__main__":
    unittest.main()
