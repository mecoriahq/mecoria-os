import json
import unittest
from pathlib import Path

from core.script_revision import (
    build_word_count_revision_feedback,
)


class ScriptWordRevisionTests(unittest.TestCase):
    def test_short_script_requests_safe_expansion(self):
        feedback = build_word_count_revision_feedback(
            attempt=1,
            word_gate={
                "word_count": 1266,
                "minimum": 1325,
                "maximum": 1550,
                "approved": False,
            },
            previous_script={"title": "Theranos"},
            prior_revision_feedback=None,
        )

        self.assertEqual(feedback["direction"], "expand")
        self.assertEqual(feedback["target_net_change"], 109)
        self.assertEqual(
            feedback["previous_script"]["title"],
            "Theranos",
        )
        self.assertTrue(
            any(
                "Do not introduce new facts" in item
                for item in feedback["instructions"]
            )
        )

    def test_long_script_requests_compression(self):
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
        self.assertEqual(feedback["target_net_change"], 85)
        self.assertEqual(
            feedback["prior_editorial_revision_brief"],
            {"attempt": 1},
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

    def test_script_agent_has_bounded_auto_revision(self):
        root = Path(__file__).resolve().parents[1]
        source = (
            root / "agents" / "script" / "run.py"
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
            "build_word_count_revision_feedback",
            source,
        )
        self.assertIn(
            "SCRIPT_WORD_COUNT_REVISION_REQUIRED",
            source,
        )
        self.assertEqual(
            profile["script"]["word_count_revision_attempts"],
            2,
        )


if __name__ == "__main__":
    unittest.main()
