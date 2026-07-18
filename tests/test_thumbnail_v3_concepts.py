import unittest

from core.thumbnail_standard import (
    combine_thumbnail_scores,
    load_thumbnail_standard,
    normalize_thumbnail_vision_qa,
    score_thumbnail_concept,
    validate_thumbnail_concepts,
)


def build_concept(
    concept_id: str,
    concept_type: str,
    overlay_text: str,
    dominant_subject: str,
    visual_hook: str,
) -> dict:
    return {
        "concept_id": concept_id,
        "concept_type": concept_type,
        "overlay_text": overlay_text,
        "dominant_subject": dominant_subject,
        "conflict": (
            "The city waste system reaches a visible breaking point"
        ),
        "emotional_trigger": "urgency",
        "visual_hook": visual_hook,
        "differentiation": (
            "This candidate uses a distinct subject and consequence"
        ),
        "topic_keywords": [
            "city waste",
            "garbage",
            "trash collection",
        ],
        "background_prompt": (
            "Premium realistic cinematic city waste scene, one dominant "
            "subject on the right or center-right, clean dark negative "
            "space on the left, no text, dramatic high contrast lighting, "
            "strong rim lighting, focal glow, realistic materials, deep "
            "perspective, urgent visual tension, mobile-first composition."
        ),
    }


class ThumbnailV3ConceptTests(unittest.TestCase):
    def setUp(self):
        self.standard = load_thumbnail_standard()
        self.topic = (
            "How Cities Quietly Remove Millions of Tons of Waste"
        )
        self.concepts = [
            build_concept(
                "THUMB-01",
                "scale_and_consequence",
                "CITY DROWNS IN TRASH",
                "massive garbage truck beside a mountain of city waste",
                "A clean skyline is overwhelmed by a rising wall of trash",
            ),
            build_concept(
                "THUMB-02",
                "failure_or_risk",
                "WHEN COLLECTION STOPS",
                "jammed garbage truck blocked by overflowing bins",
                "One stopped truck causes an entire street to overflow",
            ),
            build_concept(
                "THUMB-03",
                "hidden_mechanism",
                "WHO MOVES THE WASTE",
                "waste control room linked to collection trucks",
                "A hidden routing decision controls the city waste flow",
            ),
        ]

    def test_standard_uses_three_concept_contract(self):
        system = self.standard["concept_system"]
        self.assertEqual(system["candidate_count"], 3)
        self.assertEqual(system["finalist_count"], 2)
        self.assertEqual(
            set(system["required_concept_types"]),
            {
                "scale_and_consequence",
                "failure_or_risk",
                "hidden_mechanism",
            },
        )

    def test_three_distinct_strong_concepts_pass(self):
        result = validate_thumbnail_concepts(
            concepts=self.concepts,
            video_topic=self.topic,
            standard=self.standard,
        )
        self.assertEqual(len(result), 3)
        self.assertTrue(
            all(item["preflight_approved"] for item in result)
        )
        self.assertTrue(
            all(item["preflight_score"] >= 85 for item in result)
        )

    def test_duplicate_headline_is_rejected(self):
        concepts = [dict(item) for item in self.concepts]
        concepts[1]["overlay_text"] = concepts[0]["overlay_text"]

        with self.assertRaises(ValueError):
            validate_thumbnail_concepts(
                concepts=concepts,
                video_topic=self.topic,
                standard=self.standard,
            )

    def test_duplicate_subject_is_rejected(self):
        concepts = [dict(item) for item in self.concepts]
        concepts[2]["dominant_subject"] = (
            concepts[0]["dominant_subject"]
        )

        with self.assertRaises(ValueError):
            validate_thumbnail_concepts(
                concepts=concepts,
                video_topic=self.topic,
                standard=self.standard,
            )

    def test_generic_weak_concept_fails_score(self):
        weak = {
            "concept_id": "THUMB-01",
            "concept_type": "scale_and_consequence",
            "overlay_text": "HIDDEN SYSTEM",
            "dominant_subject": "a system",
            "conflict": "something happens",
            "emotional_trigger": "",
            "visual_hook": "generic scene",
            "differentiation": "different",
            "topic_keywords": [],
            "background_prompt": "dark cinematic background",
        }
        result = score_thumbnail_concept(
            concept=weak,
            video_topic=self.topic,
            standard=self.standard,
        )
        self.assertFalse(result["approved"])
        self.assertLess(result["score"], 85)

    def test_vision_qa_rejects_average_candidate(self):
        result = normalize_thumbnail_vision_qa(
            {
                "scores": {
                    "topic_match": 90,
                    "dominant_subject": 70,
                    "visual_tension": 78,
                    "mobile_readability": 88,
                    "clean_composition": 82,
                    "cinematic_quality": 80,
                    "ctr_strength": 70,
                },
                "verdict": "approved",
                "issues": ["Weak subject and CTR tension"],
                "summary": "Average candidate",
            },
            self.standard,
        )
        self.assertFalse(result["approved"])

    def test_vision_qa_approves_strong_candidate(self):
        result = normalize_thumbnail_vision_qa(
            {
                "scores": {
                    "topic_match": 92,
                    "dominant_subject": 91,
                    "visual_tension": 88,
                    "mobile_readability": 94,
                    "clean_composition": 90,
                    "cinematic_quality": 91,
                    "ctr_strength": 89,
                },
                "verdict": "approved",
                "issues": [],
                "summary": "Strong production candidate",
            },
            self.standard,
        )
        self.assertTrue(result["approved"])
        self.assertGreaterEqual(result["average_score"], 82)

    def test_final_score_is_vision_weighted(self):
        result = combine_thumbnail_scores(
            preflight_score=90,
            vision_score=88,
            standard=self.standard,
        )
        self.assertEqual(result["weights"]["preflight"], 0.30)
        self.assertEqual(result["weights"]["vision"], 0.70)
        self.assertTrue(result["approved"])


if __name__ == "__main__":
    unittest.main()
