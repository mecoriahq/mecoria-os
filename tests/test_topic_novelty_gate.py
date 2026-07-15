import unittest

from core.topic_novelty import (
    resolve_selected_index,
    validate_novelty_analysis,
)


class TopicNoveltyGateTests(unittest.TestCase):
    def build_analysis(self) -> dict:
        return {
            "evaluations": [
                {
                    "index": 0,
                    "duplicate": False,
                    "closest_video_id": None,
                    "novelty_score": 92,
                    "content_score": 88,
                    "reason": "New topic."
                },
                {
                    "index": 1,
                    "duplicate": True,
                    "closest_video_id": "video_002",
                    "novelty_score": 5,
                    "content_score": 85,
                    "reason": "Same airport baggage system."
                }
            ],
            "selected_index": 0,
            "score": 90,
            "reason": "Best unique topic."
        }

    def test_duplicate_manual_selection_is_blocked(self):
        analysis = validate_novelty_analysis(
            self.build_analysis(),
            idea_count=2
        )

        with self.assertRaises(ValueError):
            resolve_selected_index(
                analysis=analysis,
                requested_index=1,
                idea_count=2
            )

    def test_unique_manual_selection_is_allowed(self):
        analysis = validate_novelty_analysis(
            self.build_analysis(),
            idea_count=2
        )

        self.assertEqual(
            resolve_selected_index(
                analysis=analysis,
                requested_index=0,
                idea_count=2
            ),
            0
        )

    def test_duplicate_recommendation_is_blocked(self):
        data = self.build_analysis()
        data["selected_index"] = 1

        with self.assertRaises(ValueError):
            validate_novelty_analysis(
                data,
                idea_count=2
            )

    def test_missing_evaluation_is_blocked(self):
        data = self.build_analysis()
        data["evaluations"] = data["evaluations"][:1]

        with self.assertRaises(ValueError):
            validate_novelty_analysis(
                data,
                idea_count=2
            )


if __name__ == "__main__":
    unittest.main()
