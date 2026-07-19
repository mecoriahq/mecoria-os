import json
import tempfile
import unittest
from pathlib import Path

from core.script_candidate_manager import (
    archive_fact_risk_candidate,
    candidate_is_better,
    extract_repair_targets,
    get_script_block,
    merge_script_repairs,
    qa_metrics,
    restore_best_candidate_script,
)


class ScriptCandidateManagerTests(unittest.TestCase):
    def setUp(self):
        self.script_data = {
            "agent": "script",
            "script": {
                "hook": {
                    "narration": "Supported hook.",
                    "claim_ids": ["C01"],
                },
                "introduction": {
                    "narration": "Unsupported introduction.",
                    "claim_ids": ["C01"],
                },
                "main_sections": [
                    {
                        "title": "One",
                        "narration": "Unsupported section one.",
                        "visual_direction": "Visual one.",
                        "claim_ids": ["C02"],
                    },
                    {
                        "title": "Two",
                        "narration": "Supported section two.",
                        "visual_direction": "Visual two.",
                        "claim_ids": ["C03"],
                    },
                ],
                "conclusion": {
                    "narration": "Unsupported conclusion.",
                    "claim_ids": ["C04"],
                },
                "call_to_action": {
                    "narration": "Comment, like, subscribe.",
                    "claim_ids": [],
                },
            },
        }

    def test_better_candidate_uses_issue_counts_before_scores(self):
        better = qa_metrics({
            "status": "rejected",
            "factual_grounding_score": 88,
            "risk_compliance_score": 90,
            "unsupported_statements": [{}, {}, {}, {}, {}],
            "risk_issues": [
                {"severity": "medium"},
                {"severity": "low"},
                {"severity": "low"},
            ],
        })
        worse = qa_metrics({
            "status": "rejected",
            "factual_grounding_score": 95,
            "risk_compliance_score": 95,
            "unsupported_statements": [{} for _ in range(16)],
            "risk_issues": [
                {"severity": "medium"}
                for _ in range(6)
            ],
        })

        self.assertTrue(
            candidate_is_better(better, worse)
        )
        self.assertFalse(
            candidate_is_better(worse, better)
        )

    def test_extract_targets_deduplicates_locations(self):
        qa = {
            "unsupported_statements": [
                {
                    "location": (
                        "main_sections[0].narration / One"
                    )
                },
                {
                    "location": "main_sections[0].narration"
                },
                {
                    "location": "conclusion.narration"
                },
            ],
            "risk_issues": [
                {
                    "location": "conclusion.narration"
                },
                {
                    "location": "multiple locations"
                },
            ],
        }

        targets = extract_repair_targets(qa)

        self.assertEqual(
            [item["location"] for item in targets],
            [
                "main_sections[0].narration",
                "conclusion.narration",
            ],
        )
        self.assertEqual(
            len(targets[0]["issues"]),
            2,
        )

    def test_merge_changes_only_requested_blocks(self):
        original_hook = get_script_block(
            self.script_data,
            "hook.narration",
        )
        merged = merge_script_repairs(
            script_data=self.script_data,
            repairs=[
                {
                    "location": (
                        "introduction.narration"
                    ),
                    "narration": (
                        "Repaired introduction."
                    ),
                    "claim_ids": ["C01", "C02"],
                    "change_summary": "Removed issue.",
                },
                {
                    "location": (
                        "main_sections[0].narration"
                    ),
                    "narration": "Repaired section.",
                    "claim_ids": ["C02"],
                    "change_summary": "Removed issue.",
                },
            ],
            required_locations=[
                "introduction.narration",
                "main_sections[0].narration",
            ],
        )

        self.assertEqual(
            merged["script"]["hook"],
            original_hook,
        )
        self.assertEqual(
            merged["script"]["introduction"][
                "narration"
            ],
            "Repaired introduction.",
        )
        self.assertEqual(
            merged["script"]["main_sections"][1][
                "narration"
            ],
            "Supported section two.",
        )

    def test_worse_candidate_does_not_replace_best(self):
        with tempfile.TemporaryDirectory() as temp:
            project_root = Path(temp)
            canonical = project_root / "script.json"
            canonical.parent.mkdir(
                parents=True,
                exist_ok=True,
            )
            canonical.write_text(
                json.dumps(self.script_data),
                encoding="utf-8",
            )
            context = {
                "channel": "rise_dossier",
                "video_id": "video_001",
                "quality_gates": {},
            }
            better_qa = {
                "status": "rejected",
                "factual_grounding_score": 88,
                "risk_compliance_score": 90,
                "unsupported_statements": [
                    {} for _ in range(5)
                ],
                "risk_issues": [],
            }
            worse_script = json.loads(
                json.dumps(self.script_data)
            )
            worse_script["script"]["hook"][
                "narration"
            ] = "Worse hook."
            worse_qa = {
                "status": "rejected",
                "factual_grounding_score": 78,
                "risk_compliance_score": 86,
                "unsupported_statements": [
                    {} for _ in range(16)
                ],
                "risk_issues": [
                    {"severity": "medium"}
                    for _ in range(6)
                ],
            }

            first = archive_fact_risk_candidate(
                project_root=project_root,
                context=context,
                script_data=self.script_data,
                qa_data=better_qa,
            )
            second = archive_fact_risk_candidate(
                project_root=project_root,
                context=context,
                script_data=worse_script,
                qa_data=worse_qa,
            )

            self.assertTrue(
                first["accepted_as_best"]
            )
            self.assertFalse(
                second["accepted_as_best"]
            )

            restore_best_candidate_script(
                project_root=project_root,
                context=context,
                canonical_script_path=canonical,
            )
            restored = json.loads(
                canonical.read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(
                restored["script"]["hook"][
                    "narration"
                ],
                "Supported hook.",
            )


if __name__ == "__main__":
    unittest.main()
