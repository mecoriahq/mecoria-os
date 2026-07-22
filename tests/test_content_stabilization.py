import copy
import json
import tempfile
import unittest
from pathlib import Path

from core.channel_content_policy import (
    load_editorial_profile,
)
from core.content_stabilization import (
    ContentStabilizationBudgetExceeded,
    ContentStabilizationLoopDetected,
    apply_safe_word_budget_recovery,
    automatic_checkpoint_recovery_available,
    enter_stabilization_step,
    record_stabilization_action,
    word_budget_report,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ContentStabilizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profile = load_editorial_profile(
            "rise_dossier"
        )
        cls.context = json.loads(
            (
                PROJECT_ROOT
                / "records"
                / "run_contexts"
                / "rise_dossier"
                / "video_002.json"
            ).read_text(encoding="utf-8-sig")
        )
        script_ref = cls.context["outputs"]["script"]
        cls.script = json.loads(
            (PROJECT_ROOT / script_ref).read_text(
                encoding="utf-8-sig"
            )
        )

    def test_current_boeing_word_gap_is_auto_recoverable(self):
        report = word_budget_report(
            script_data=self.script,
            profile=self.profile,
        )
        self.assertEqual(
            report["current_word_count"],
            1319,
        )
        self.assertEqual(
            report["missing_word_count"],
            6,
        )
        self.assertTrue(report["recoverable"])

        revised, recovery = (
            apply_safe_word_budget_recovery(
                script_data=self.script,
                profile=self.profile,
            )
        )
        self.assertTrue(recovery["applied"])
        self.assertGreaterEqual(
            recovery["revised_word_count"],
            1325,
        )
        self.assertIn(
            "automatic_word_budget_recovery",
            revised["quality"],
        )

    def test_word_recovery_is_idempotent(self):
        revised, first = (
            apply_safe_word_budget_recovery(
                script_data=self.script,
                profile=self.profile,
            )
        )
        second_script, second = (
            apply_safe_word_budget_recovery(
                script_data=revised,
                profile=self.profile,
            )
        )
        self.assertTrue(first["applied"])
        self.assertFalse(second["applied"])
        self.assertEqual(
            second["reason"],
            "word_budget_already_satisfied",
        )
        self.assertEqual(
            revised["script"]["call_to_action"]["narration"],
            second_script["script"]["call_to_action"]["narration"],
        )

    def test_large_gap_is_not_silently_filled(self):
        short = copy.deepcopy(self.script)
        short["script"]["main_sections"] = []
        report = word_budget_report(
            script_data=short,
            profile=self.profile,
        )
        self.assertGreater(
            report["missing_word_count"],
            report["max_safe_word_top_up"],
        )
        revised, recovery = (
            apply_safe_word_budget_recovery(
                script_data=short,
                profile=self.profile,
            )
        )
        self.assertFalse(recovery["applied"])
        self.assertEqual(short, revised)

    def test_same_signature_loop_is_bounded(self):
        context = {
            "quality_gates": {},
        }
        profile = copy.deepcopy(self.profile)
        profile["reliability"][
            "max_same_signature_attempts"
        ] = 2

        for _ in range(2):
            record_stabilization_action(
                context=context,
                profile=profile,
                phase="factual",
                action="repair",
                payload={"script": "same"},
            )

        with self.assertRaises(
            ContentStabilizationLoopDetected
        ):
            record_stabilization_action(
                context=context,
                profile=profile,
                phase="factual",
                action="repair",
                payload={"script": "same"},
            )

    def test_total_step_budget_is_finite(self):
        context = {
            "quality_gates": {},
        }
        profile = copy.deepcopy(self.profile)
        profile["reliability"][
            "max_content_stabilization_steps"
        ] = 2

        enter_stabilization_step(
            context=context,
            profile=profile,
            phase="content",
        )
        enter_stabilization_step(
            context=context,
            profile=profile,
            phase="content",
        )

        with self.assertRaises(
            ContentStabilizationBudgetExceeded
        ):
            enter_stabilization_step(
                context=context,
                profile=profile,
                phase="content",
            )

    def test_current_checkpoint_can_resume_automatically(self):
        result = automatic_checkpoint_recovery_available(
            project_root=PROJECT_ROOT,
            context=self.context,
            profile=self.profile,
        )
        self.assertTrue(result["available"])
        self.assertEqual(
            result["reason"],
            "safe_word_budget_recovery",
        )


if __name__ == "__main__":
    unittest.main()
