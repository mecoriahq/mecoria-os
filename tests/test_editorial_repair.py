import unittest

from core.editorial_repair import (
    build_editorial_repair_targets,
)


def sample_script() -> dict:
    return {
        "script": {
            "hook": {
                "narration": (
                    "Theranos announced a promise. The public promise "
                    "would later face scrutiny."
                ),
                "claim_ids": ["C03", "C24"],
            },
            "introduction": {
                "narration": (
                    "Theranos announced a promise. The public promise "
                    "would later face scrutiny."
                ),
                "claim_ids": ["C03", "C24"],
            },
            "main_sections": [
                {
                    "title": "Walgreens",
                    "narration": (
                        "In 2013 Walgreens announced its partnership "
                        "with Theranos."
                    ),
                    "claim_ids": ["C03"],
                },
                {
                    "title": "Evidence",
                    "narration": (
                        "The public promise would later face scrutiny "
                        "as evidence remained limited."
                    ),
                    "claim_ids": ["C24"],
                },
                {
                    "title": "Outcome",
                    "narration": (
                        "The public promise would later face scrutiny "
                        "as evidence remained limited."
                    ),
                    "claim_ids": ["C24"],
                },
            ],
            "conclusion": {
                "narration": (
                    "The approved record shows the public promise "
                    "outpaced available evidence."
                ),
                "claim_ids": ["C24"],
            },
            "call_to_action": {
                "narration": "Comment, like, and subscribe.",
                "claim_ids": [],
            },
        }
    }


class EditorialRepairTests(unittest.TestCase):
    def test_failed_checks_create_section_scoped_targets(self):
        qa = {
            "overall_score": 78,
            "checks": {
                "hook_strength": {"score": 74},
                "hook_intro_distinctness": {"score": 64},
                "narrative_spine": {"score": 86},
                "specificity": {"score": 83},
                "repetition_risk": {"score": 50},
            },
            "issues": [],
        }
        gate = {
            "approved": False,
            "failures": [
                {"check": "hook_strength", "score": 74, "minimum": 88},
                {
                    "check": "hook_intro_distinctness",
                    "score": 64,
                    "minimum": 82,
                },
                {"check": "narrative_spine", "score": 86, "minimum": 88},
                {"check": "specificity", "score": 83, "minimum": 85},
                {"check": "repetition_risk", "score": 50, "minimum": 82},
            ],
        }

        targets = build_editorial_repair_targets(
            script_data=sample_script(),
            qa_data=qa,
            gate_result=gate,
            maximum_targets=6,
        )
        locations = [item["location"] for item in targets]

        self.assertIn("hook.narration", locations)
        self.assertIn("introduction.narration", locations)
        self.assertLessEqual(len(locations), 6)
        self.assertTrue(
            all(
                location != "main_sections[7].narration"
                for location in locations
            )
        )

    def test_no_failed_checks_produces_no_repairs(self):
        targets = build_editorial_repair_targets(
            script_data=sample_script(),
            qa_data={"checks": {}, "issues": []},
            gate_result={"approved": True, "failures": []},
        )
        self.assertEqual(targets, [])


if __name__ == "__main__":
    unittest.main()
