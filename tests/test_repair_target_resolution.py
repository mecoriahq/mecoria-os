import unittest

from core.script_candidate_manager import (
    resolve_repair_targets_for_script,
)


def sample_script() -> dict:
    return {
        "script": {
            "hook": {
                "narration": "The promise entered public view.",
                "claim_ids": ["C01"],
            },
            "introduction": {
                "narration": "Theranos announced a Walgreens partnership.",
                "claim_ids": ["C03"],
            },
            "main_sections": [
                {
                    "title": "One",
                    "narration": "The company described small-sample testing.",
                    "claim_ids": ["C04"],
                },
                {
                    "title": "Two",
                    "narration": "The approved record described scrutiny.",
                    "claim_ids": ["C08"],
                },
            ],
            "conclusion": {
                "narration": "The public promise outpaced available evidence.",
                "claim_ids": ["C24"],
            },
            "call_to_action": {
                "narration": "Comment, like, and subscribe.",
                "claim_ids": [],
            },
        }
    }


class RepairTargetResolutionTests(unittest.TestCase):
    def test_out_of_range_target_is_skipped(self):
        result = resolve_repair_targets_for_script(
            script_data=sample_script(),
            repair_targets=[
                {
                    "location": "main_sections[7].narration",
                    "issues": [
                        {
                            "location": "main_sections[7].narration",
                            "statement": "A sentence that is not present.",
                            "reason": "Unsupported.",
                        }
                    ],
                }
            ],
        )

        self.assertEqual(result["targets"], [])
        self.assertEqual(len(result["stale_issues"]), 1)
        self.assertEqual(result["relocated_issues"], [])

    def test_stale_location_is_relocated_by_statement(self):
        result = resolve_repair_targets_for_script(
            script_data=sample_script(),
            repair_targets=[
                {
                    "location": "main_sections[7].narration",
                    "issues": [
                        {
                            "location": "main_sections[7].narration",
                            "statement": (
                                "The public promise outpaced "
                                "available evidence."
                            ),
                            "reason": "Needs cautious wording.",
                        }
                    ],
                }
            ],
        )

        self.assertEqual(
            [
                item["location"]
                for item in result["targets"]
            ],
            ["conclusion.narration"],
        )
        self.assertEqual(len(result["relocated_issues"]), 1)
        self.assertEqual(result["stale_issues"], [])

    def test_valid_and_stale_targets_are_partitioned(self):
        result = resolve_repair_targets_for_script(
            script_data=sample_script(),
            repair_targets=[
                {
                    "location": "hook.narration",
                    "issues": [
                        {
                            "location": "hook.narration",
                            "statement": (
                                "The promise entered public view."
                            ),
                        }
                    ],
                },
                {
                    "location": "main_sections[9].narration",
                    "issues": [
                        {
                            "location": "main_sections[9].narration",
                            "statement": "Missing statement.",
                        }
                    ],
                },
            ],
        )

        self.assertEqual(
            [
                item["location"]
                for item in result["targets"]
            ],
            ["hook.narration"],
        )
        self.assertEqual(len(result["stale_issues"]), 1)


if __name__ == "__main__":
    unittest.main()
