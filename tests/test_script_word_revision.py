import json
import unittest
from pathlib import Path

from core.script_revision import (
    build_word_count_revision_feedback,
)


class ScriptWordRevisionTests(unittest.TestCase):
    def test_short_script_targets_middle_of_range(self):
        feedback = build_word_count_revision_feedback(
            attempt=1,
            word_gate={
                "word_count": 1266,
                "minimum": 1325,
                "maximum": 1550,
                "approved": False,
            },
            previous_script={
                "title": "Theranos",
                "hook": {"narration": "Short hook."},
                "introduction": {
                    "narration": "Short introduction."
                },
                "main_sections": [
                    {
                        "title": "Section",
                        "narration": "Short section.",
                    }
                ],
                "conclusion": {
                    "narration": "Short conclusion."
                },
                "call_to_action": {
                    "narration": "Comment, like, subscribe."
                },
            },
            prior_revision_feedback=None,
            approved_claim_ids=["C01", "C02"],
        )

        self.assertEqual(feedback["direction"], "expand")
        self.assertEqual(feedback["target_word_count"], 1438)
        self.assertEqual(feedback["target_net_change"], 172)
        self.assertEqual(
            feedback["approved_claim_ids"],
            ["C01", "C02"],
        )
        self.assertEqual(
            len(
                feedback["section_word_targets"][
                    "targets"
                ]["main_sections"]
            ),
            1,
        )
        self.assertTrue(
            feedback[
                "must_preserve_editorial_corrections"
            ]
        )

    def test_long_script_targets_middle_of_range(self):
        feedback = build_word_count_revision_feedback(
            attempt=2,
            word_gate={
                "word_count": 1600,
                "minimum": 1325,
                "maximum": 1550,
                "approved": False,
            },
            previous_script={"title": "Theranos"},
            prior_revision_feedback={"attempt": 1},
        )

        self.assertEqual(feedback["direction"], "compress")
        self.assertEqual(feedback["target_word_count"], 1438)
        self.assertEqual(feedback["target_net_change"], 162)
        self.assertEqual(
            feedback["prior_editorial_revision_brief"],
            {"attempt": 1},
        )

    def test_prior_qa_issues_become_hard_constraints(self):
        feedback = build_word_count_revision_feedback(
            attempt=1,
            word_gate={
                "word_count": 1199,
                "minimum": 1325,
                "maximum": 1550,
                "approved": False,
            },
            previous_script={"title": "Theranos"},
            prior_revision_feedback={
                "issues": [
                    {
                        "statement": (
                            "a blood-testing company stepped "
                            "out of secrecy"
                        ),
                        "suggested_action": (
                            "Remove the unsupported secrecy claim."
                        ),
                    },
                    {
                        "message": (
                            "Do not make a negative legal "
                            "conclusion."
                        ),
                        "required_edit": (
                            "Remove the legal conclusion."
                        ),
                    },
                ]
            },
        )

        constraints = feedback["editorial_constraints"]
        self.assertEqual(constraints["issue_count"], 2)
        self.assertIn(
            "a blood-testing company stepped out of secrecy",
            constraints["flagged_statements"],
        )
        self.assertIn(
            "Remove the legal conclusion.",
            constraints["required_edits"],
        )

    def test_passing_gate_cannot_create_revision(self):
        with self.assertRaises(ValueError):
            build_word_count_revision_feedback(
                attempt=1,
                word_gate={
                    "word_count": 1400,
                    "minimum": 1325,
                    "maximum": 1550,
                    "approved": True,
                },
                previous_script={"title": "Theranos"},
                prior_revision_feedback=None,
            )

    def test_script_agent_has_grounded_auto_revision(self):
        root = Path(__file__).resolve().parents[1]
        source = (
            root / "agents" / "script" / "run.py"
        ).read_text(encoding="utf-8-sig")
        prompt = (
            root / "agents" / "script" / "prompt.py"
        ).read_text(encoding="utf-8-sig")
        profile = json.loads(
            (
                root
                / "config"
                / "editorial_profiles"
                / "rise_dossier.json"
            ).read_text(encoding="utf-8-sig")
        )

        self.assertIn(
            "evaluate_script_word_count",
            source,
        )
        self.assertIn(
            "approved_claim_ids=[",
            source,
        )
        self.assertIn(
            "SCRIPT_WORD_COUNT_REVISION_TARGET",
            source,
        )
        self.assertIn(
            "MANDATORY COMBINED FACT/RISK + WORD COUNT",
            prompt,
        )
        self.assertIn(
            "FLAGGED OR UNSUPPORTED LANGUAGE",
            prompt,
        )
        self.assertEqual(
            profile["script"]["word_count_revision_attempts"],
            2,
        )


if __name__ == "__main__":
    unittest.main()
