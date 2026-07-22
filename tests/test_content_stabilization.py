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


def words(count: int, label: str) -> str:
    return " ".join(
        f"{label}{index}"
        for index in range(count)
    )


def recoverable_script() -> dict:
    return {
        "script": {
            "hook": {"narration": words(100, "hook")},
            "introduction": {
                "narration": words(100, "intro")
            },
            "main_sections": [{
                "title": "Section",
                "narration": words(1069, "main"),
            }],
            "conclusion": {
                "narration": words(25, "conclusion")
            },
            "call_to_action": {
                "narration": words(25, "cta")
            },
        },
        "quality": {},
    }


def approved_fact() -> dict:
    return {
        "status": "approved",
        "factual_grounding_score": 100,
        "risk_compliance_score": 100,
        "unsupported_statements": [],
        "risk_issues": [],
        "approved_claim_ids": [],
    }


def factual_repair_script() -> dict:
    return {
        "script": {
            "hook": {
                "narration": "An approved statement.",
                "claim_ids": ["C01"],
            },
            "introduction": {
                "narration": "Introduction.",
                "claim_ids": [],
            },
            "main_sections": [{
                "title": "Grounding",
                "narration": (
                    "Once the aircraft was grounded, the story "
                    "changed."
                ),
                "claim_ids": ["C09"],
            }],
            "conclusion": {
                "narration": "Conclusion.",
                "claim_ids": [],
            },
            "call_to_action": {
                "narration": "Comment, like, and subscribe.",
                "claim_ids": [],
            },
        }
    }


def factual_repair_qa() -> dict:
    return {
        "status": "rejected",
        "factual_grounding_score": 98,
        "risk_compliance_score": 100,
        "unsupported_statements": [{
            "location": "main_sections[0].narration",
            "statement": "Once the aircraft was grounded...",
            "reason": "C11 is missing from this block.",
            "suggested_action": "Attach C11 to this narration block.",
        }],
        "risk_issues": [{
            "category": "other",
            "severity": "low",
            "location": "main_sections[0].narration",
            "message": "Claim ID missing.",
            "required_edit": "Add C11.",
        }],
        "approved_claim_ids": ["C01", "C09", "C11"],
    }


class ContentStabilizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profile = load_editorial_profile(
            "rise_dossier"
        )
        cls.script = recoverable_script()

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
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "script.json").write_text(
                json.dumps(self.script),
                encoding="utf-8",
            )
            (root / "fact.json").write_text(
                json.dumps(approved_fact()),
                encoding="utf-8",
            )
            context = {
                "status": "founder_editorial_review_required",
                "outputs": {
                    "script": "script.json",
                    "fact_risk_qa": "fact.json",
                },
                "quality_gates": {},
            }
            result = automatic_checkpoint_recovery_available(
                project_root=root,
                context=context,
                profile=self.profile,
            )
        self.assertTrue(result["available"])
        self.assertEqual(
            result["reason"],
            "safe_word_budget_recovery",
        )

    def test_factual_checkpoint_can_resume_deterministically(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "script.json").write_text(
                json.dumps(factual_repair_script()),
                encoding="utf-8",
            )
            (root / "fact.json").write_text(
                json.dumps(factual_repair_qa()),
                encoding="utf-8",
            )
            context = {
                "status": "founder_factual_review_required",
                "outputs": {
                    "script": "script.json",
                    "fact_risk_qa": "fact.json",
                },
                "quality_gates": {},
            }
            result = automatic_checkpoint_recovery_available(
                project_root=root,
                context=context,
                profile=self.profile,
            )
        self.assertTrue(result["available"])
        self.assertEqual(
            result["reason"],
            "deterministic_factual_repair",
        )
        self.assertEqual(
            result["factual_repair"]["action_count"],
            1,
        )


if __name__ == "__main__":
    unittest.main()
