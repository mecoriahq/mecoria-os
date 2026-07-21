import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from core.script_candidate_manager import (
    evaluate_founder_manual_candidate_policy,
    find_recoverable_founder_manual_candidate,
)


class FounderManualRevisionRecoveryTests(unittest.TestCase):
    def build_script(self, narration: str) -> dict:
        return {
            "script": {
                "hook": {
                    "narration": narration,
                    "claim_ids": ["C01"],
                },
                "introduction": {
                    "narration": "Documented introduction.",
                    "claim_ids": ["C02"],
                },
                "main_sections": [],
                "conclusion": {
                    "narration": "Documented conclusion.",
                    "claim_ids": ["C03"],
                },
                "call_to_action": {
                    "narration": "Subscribe.",
                    "claim_ids": [],
                },
            }
        }

    def write_json(self, path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )

    def sha256(self, path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def build_context(
        self,
        root: Path,
        script_hash: str,
        *,
        chain_active: bool = False,
    ) -> dict:
        record_path = (
            root
            / "records"
            / "run_contexts"
            / "rise_dossier"
            / "video_002"
            / "inputs"
            / "founder_manual_editorial_revision_03.json"
        )
        self.write_json(record_path, {
            "channel": "rise_dossier",
            "video_id": "video_002",
            "run_id": "rise_dossier_video_002_v1",
            "revised_script_sha256": script_hash,
        })
        return {
            "channel": "rise_dossier",
            "video_id": "video_002",
            "run_id": "rise_dossier_video_002_v1",
            "sources": {
                "founder_manual_editorial_revision": str(
                    record_path.relative_to(root)
                ).replace("\\", "/"),
            },
            "quality_gates": {
                "founder_manual_editorial_revision": {
                    "pending_fact_risk_qa": True,
                    "fact_risk_repair_chain_active": chain_active,
                }
            },
        }

    def build_candidate(
        self,
        root: Path,
        *,
        index: int,
        script: dict,
        qa: dict,
    ) -> tuple[dict, Path]:
        candidate_dir = (
            root
            / "records"
            / "run_contexts"
            / "rise_dossier"
            / "video_002"
            / "candidates"
            / f"candidate_{index:02d}"
        )
        script_path = candidate_dir / "script.json"
        qa_path = candidate_dir / "fact_risk_qa.json"
        metadata_path = candidate_dir / "metadata.json"
        self.write_json(script_path, script)
        self.write_json(qa_path, qa)
        record = {
            "candidate_index": index,
            "script_reference": str(
                script_path.relative_to(root)
            ).replace("\\", "/"),
            "qa_reference": str(
                qa_path.relative_to(root)
            ).replace("\\", "/"),
            "metrics": {},
        }
        self.write_json(metadata_path, record)
        return record, script_path

    def rejected_qa(
        self,
        *,
        severity: str = "medium",
        location: str = "hook.narration",
    ) -> dict:
        return {
            "status": "rejected",
            "factual_grounding_score": 96,
            "risk_compliance_score": 99,
            "unsupported_statements": [{
                "location": location,
                "statement": "Unsupported phrase.",
            }],
            "risk_issues": [{
                "location": location,
                "statement": "Unsupported phrase.",
                "severity": severity,
            }],
        }

    def approved_qa(self) -> dict:
        return {
            "status": "approved",
            "factual_grounding_score": 100,
            "risk_compliance_score": 100,
            "unsupported_statements": [],
            "risk_issues": [],
        }

    def test_exact_manual_candidate_is_preserved_for_repair(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            script = self.build_script(
                "Unsupported phrase. Supported context."
            )
            qa = self.rejected_qa()
            record, script_path = self.build_candidate(
                root,
                index=17,
                script=script,
                qa=qa,
            )
            context = self.build_context(
                root,
                self.sha256(script_path),
            )
            result = evaluate_founder_manual_candidate_policy(
                project_root=root,
                context=context,
                candidate_record=record,
                script_data=script,
                qa_data=qa,
            )
            self.assertEqual(
                result["action"],
                "preserve_for_section_repair",
            )
            self.assertEqual(
                result["repair_locations"],
                ["hook.narration"],
            )

    def test_high_risk_manual_candidate_falls_back(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            script = self.build_script("Unsupported phrase.")
            qa = self.rejected_qa(severity="high")
            record, script_path = self.build_candidate(
                root,
                index=17,
                script=script,
                qa=qa,
            )
            context = self.build_context(
                root,
                self.sha256(script_path),
            )
            result = evaluate_founder_manual_candidate_policy(
                project_root=root,
                context=context,
                candidate_record=record,
                script_data=script,
                qa_data=qa,
            )
            self.assertEqual(result["action"], "fallback_to_best")
            self.assertEqual(
                result["reason"],
                "manual_revision_has_high_risk_issue",
            )

    def test_repair_chain_preserves_repaired_descendant(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            original = self.build_script("Original manual script.")
            _, original_path = self.build_candidate(
                root,
                index=17,
                script=original,
                qa=self.rejected_qa(),
            )
            context = self.build_context(
                root,
                self.sha256(original_path),
                chain_active=True,
            )
            repaired = self.build_script(
                "Unsupported phrase. Repaired descendant."
            )
            qa = self.rejected_qa()
            record, _ = self.build_candidate(
                root,
                index=19,
                script=repaired,
                qa=qa,
            )
            result = evaluate_founder_manual_candidate_policy(
                project_root=root,
                context=context,
                candidate_record=record,
                script_data=repaired,
                qa_data=qa,
            )
            self.assertEqual(
                result["action"],
                "preserve_for_section_repair",
            )

    def test_approved_repair_chain_reaches_editorial(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            original = self.build_script("Original manual script.")
            _, original_path = self.build_candidate(
                root,
                index=17,
                script=original,
                qa=self.rejected_qa(),
            )
            context = self.build_context(
                root,
                self.sha256(original_path),
                chain_active=True,
            )
            repaired = self.build_script(
                "Fully supported repaired descendant."
            )
            qa = self.approved_qa()
            record, _ = self.build_candidate(
                root,
                index=20,
                script=repaired,
                qa=qa,
            )
            result = evaluate_founder_manual_candidate_policy(
                project_root=root,
                context=context,
                candidate_record=record,
                script_data=repaired,
                qa_data=qa,
            )
            self.assertEqual(
                result["action"],
                "allow_editorial_evaluation",
            )

    def test_unrelated_candidate_uses_standard_ranking(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manual = self.build_script("Manual revision.")
            _, manual_path = self.build_candidate(
                root,
                index=17,
                script=manual,
                qa=self.rejected_qa(),
            )
            context = self.build_context(
                root,
                self.sha256(manual_path),
            )
            unrelated = self.build_script("Unrelated candidate.")
            qa = self.rejected_qa()
            record, _ = self.build_candidate(
                root,
                index=18,
                script=unrelated,
                qa=qa,
            )
            result = evaluate_founder_manual_candidate_policy(
                project_root=root,
                context=context,
                candidate_record=record,
                script_data=unrelated,
                qa_data=qa,
            )
            self.assertEqual(
                result["action"],
                "standard_ranking",
            )

    def test_recovery_finds_archived_manual_candidate(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manual = self.build_script(
                "Unsupported phrase. Manual revision."
            )
            qa = self.rejected_qa()
            _, manual_path = self.build_candidate(
                root,
                index=17,
                script=manual,
                qa=qa,
            )
            self.build_candidate(
                root,
                index=18,
                script=self.build_script("Safe fallback."),
                qa=self.approved_qa(),
            )
            context = self.build_context(
                root,
                self.sha256(manual_path),
            )
            result = find_recoverable_founder_manual_candidate(
                project_root=root,
                context=context,
            )
            self.assertIsNotNone(result)
            self.assertEqual(
                result["record"]["candidate_index"],
                17,
            )


if __name__ == "__main__":
    unittest.main()
