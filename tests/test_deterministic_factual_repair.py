import copy
import unittest
from unittest.mock import patch

from core.factual_repair import (
    apply_deterministic_factual_repair,
    build_deterministic_factual_repair_plan,
)


STALE_QA_HOOK_STATEMENT = (
    "By March 13, 2019, the Boeing 737 MAX had become more than "
    "an aircraft program under scrutiny; it was also a test of "
    "Boeing and the FAA."
)

CURRENT_SAFE_HOOK = (
    "On March 13, 2019, the FAA issued its U.S. grounding order "
    "for the Boeing 737 MAX. Europe had suspended MAX operations "
    "the day before. Two MAX crashes had killed 346 people, and "
    "the question facing aviation was no longer only whether one "
    "aircraft could return to service. Based on official findings "
    "and actions, the MAX story can be framed not simply as one "
    "software problem, but as a trust collapse involving design, "
    "training, certification, disclosure, and oversight issues "
    "across Boeing and the FAA."
)


def script_fixture():
    return {
        "agent": "script",
        "version": "2.0",
        "channel": "rise_dossier",
        "script": {
            "title": "Boeing 737 MAX",
            "hook": {
                "narration": CURRENT_SAFE_HOOK,
                "claim_ids": ["C06", "C11", "C25"],
            },
            "introduction": {
                "narration": "Introduction.",
                "claim_ids": ["C01"],
            },
            "main_sections": [
                {
                    "title": "One",
                    "narration": "Supported narration.",
                    "claim_ids": ["C01"],
                },
                {
                    "title": "Certification",
                    "narration": (
                        "Boeing announced that the MAX 8 had earned "
                        "FAA certification on March 8, 2017."
                    ),
                    "claim_ids": ["C04"],
                },
                {
                    "title": "Three",
                    "narration": "Supported narration.",
                    "claim_ids": ["C05"],
                },
                {
                    "title": "Four",
                    "narration": "Supported narration.",
                    "claim_ids": ["C06"],
                },
                {
                    "title": "Grounding",
                    "narration": (
                        "Once the aircraft was grounded, the program "
                        "entered a new regulatory phase."
                    ),
                    "claim_ids": ["C09", "C10", "C25"],
                },
            ],
            "conclusion": {
                "narration": "Conclusion.",
                "claim_ids": ["C25"],
            },
            "call_to_action": {
                "narration": "Subscribe for more.",
                "claim_ids": [],
            },
        },
    }


def qa_fixture():
    return {
        "status": "rejected",
        "factual_grounding_score": 94,
        "risk_compliance_score": 96,
        "approved_claim_ids": [
            "C01", "C04", "C05", "C06", "C09", "C10", "C11", "C25"
        ],
        "unsupported_statements": [
            {
                "location": "hook.narration",
                "statement": f"\u201c{STALE_QA_HOOK_STATEMENT}\u201d",
                "reason": "Temporal certainty is unsupported.",
                "suggested_action": (
                    "Remove the date-linked interpretive assertion or "
                    "qualify it so the framing is tied to later findings."
                ),
            },
            {
                "location": "main_sections[1].narration",
                "statement": (
                    "\u201cBoeing announced that the MAX 8 had earned "
                    "FAA certification\u2026\u201d"
                ),
                "reason": "The announcement attribution is unsupported.",
                "suggested_action": (
                    "Remove \u201cBoeing announced that\u201d unless an "
                    "approved claim supports the announcement."
                ),
            },
            {
                "location": "main_sections[4].narration",
                "statement": "\u201cOnce the aircraft was grounded\u2026\u201d",
                "reason": "The grounding claim ID is missing.",
                "suggested_action": (
                    "Attach C11 to this narration block or remove the "
                    "grounding reference."
                ),
            },
        ],
        "risk_issues": [
            {
                "category": "misleading_certainty",
                "severity": "medium",
                "location": "hook.narration",
                "message": "Temporal certainty is too strong.",
                "required_edit": "Tie the framing to later findings.",
            },
            {
                "category": "other",
                "severity": "low",
                "location": "main_sections[4].narration",
                "message": "Grounding claim ID is missing.",
                "required_edit": "Add C11.",
            },
        ],
    }


class DeterministicFactualRepairTests(unittest.TestCase):
    def test_stale_hook_is_excluded_and_real_issues_build_safe_plan(self):
        plan = build_deterministic_factual_repair_plan(
            script_data=script_fixture(),
            qa_data=qa_fixture(),
        )
        self.assertTrue(plan["available"])
        self.assertEqual(plan["action_count"], 2)
        self.assertEqual(
            set(plan["action_types"]),
            {"add_claim_id", "remove_exact_text"},
        )
        self.assertEqual(plan["unresolved_count"], 0)
        self.assertEqual(plan["stale_issue_count"], 2)
        self.assertFalse(any(
            action["location"] == "hook.narration"
            for action in plan["actions"]
        ))

    @patch(
        "core.factual_repair.validate_script_claim_references",
        return_value={"approved": True, "errors": []},
    )
    def test_safe_plan_applies_only_current_exact_changes(self, _validator):
        script = script_fixture()
        original_hook = script["script"]["hook"]["narration"]
        qa = qa_fixture()
        plan = build_deterministic_factual_repair_plan(
            script_data=script,
            qa_data=qa,
        )
        result = apply_deterministic_factual_repair(
            script_data=script,
            ledger_data={"claims": []},
            qa_data=qa,
            plan=plan,
        )
        self.assertTrue(result["applied"])
        repaired = result["repaired_script"]["script"]
        self.assertEqual(repaired["hook"]["narration"], original_hook)
        self.assertEqual(
            repaired["main_sections"][1]["narration"],
            "The MAX 8 had earned FAA certification on March 8, 2017.",
        )
        self.assertIn("C11", repaired["main_sections"][4]["claim_ids"])

    @patch(
        "core.factual_repair.validate_script_claim_references",
        return_value={"approved": True, "errors": []},
    )
    def test_application_is_idempotent(self, _validator):
        script = script_fixture()
        qa = qa_fixture()
        plan = build_deterministic_factual_repair_plan(
            script_data=script,
            qa_data=qa,
        )
        first = apply_deterministic_factual_repair(
            script_data=script,
            ledger_data={"claims": []},
            qa_data=qa,
            plan=plan,
        )
        second = apply_deterministic_factual_repair(
            script_data=first["repaired_script"],
            ledger_data={"claims": []},
            qa_data=qa,
            plan=plan,
        )
        self.assertFalse(second["applied"])
        self.assertEqual(second["status"], "already_satisfied")

    def test_high_risk_issue_blocks_auto_repair(self):
        qa = qa_fixture()
        qa["risk_issues"].append({
            "category": "defamation",
            "severity": "high",
            "location": "hook.narration",
            "message": "High-risk allegation.",
            "required_edit": "Founder review required.",
        })
        plan = build_deterministic_factual_repair_plan(
            script_data=script_fixture(),
            qa_data=qa,
        )
        self.assertFalse(plan["available"])
        self.assertEqual(plan["high_risk_issue_count"], 1)

    def test_unapproved_claim_id_is_blocked(self):
        qa = qa_fixture()
        qa["approved_claim_ids"].remove("C11")
        plan = build_deterministic_factual_repair_plan(
            script_data=script_fixture(),
            qa_data=qa,
        )
        self.assertFalse(plan["available"])
        self.assertTrue(any(
            "claim_id_not_approved:C11" in str(item)
            for item in plan["unresolved"]
        ))


if __name__ == "__main__":
    unittest.main()
