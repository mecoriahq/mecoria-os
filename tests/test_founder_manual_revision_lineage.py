import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from core.script_candidate_manager import (
    evaluate_founder_manual_candidate_policy,
    load_founder_manual_revision_state,
)


class FounderManualRevisionLineageTests(unittest.TestCase):
    def write_json(self, path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )

    def build_script(self, narration: str) -> dict:
        return {
            "script": {
                "hook": {
                    "narration": narration,
                    "claim_ids": ["C01"],
                },
                "introduction": {
                    "narration": "Supported introduction.",
                    "claim_ids": ["C02"],
                },
                "main_sections": [{
                    "title": "Section",
                    "narration": "Supported section.",
                    "claim_ids": ["C03"],
                }],
                "conclusion": {
                    "narration": "Supported conclusion.",
                    "claim_ids": ["C04"],
                },
                "call_to_action": {
                    "narration": "Subscribe.",
                    "claim_ids": [],
                },
            }
        }

    def rejected_qa(
        self,
        *,
        high_risk: bool = False,
    ) -> dict:
        return {
            "status": "rejected",
            "factual_grounding_score": 98,
            "risk_compliance_score": 100,
            "unsupported_statements": [{
                "location": "hook.narration",
                "statement": "Unsupported phrase.",
            }],
            "risk_issues": ([{
                "location": "hook.narration",
                "statement": "Unsupported phrase.",
                "severity": "high",
            }] if high_risk else []),
        }

    def approved_qa(self) -> dict:
        return {
            "status": "approved",
            "factual_grounding_score": 100,
            "risk_compliance_score": 100,
            "unsupported_statements": [],
            "risk_issues": [],
        }

    def build_context(
        self,
        root: Path,
        recovered_reference: str,
        *,
        pending: bool = False,
        chain_active: bool = False,
        lineage_active: bool = False,
        validation_status: str = "fallback_to_best",
    ) -> dict:
        return {
            "channel": "rise_dossier",
            "video_id": "video_002",
            "run_id": "rise_dossier_video_002_v1",
            "sources": {},
            "quality_gates": {
                "founder_manual_editorial_revision": {
                    "pending_fact_risk_qa": pending,
                    "fact_risk_repair_chain_active": chain_active,
                    "manual_revision_lineage_active": lineage_active,
                    "factual_validation_status": validation_status,
                    "recovered_candidate_script_reference": (
                        recovered_reference
                    ),
                }
            },
        }

    def build_candidate(
        self,
        root: Path,
        index: int,
        script: dict,
    ) -> tuple[dict, Path]:
        directory = (
            root
            / "records"
            / "run_contexts"
            / "rise_dossier"
            / "video_002"
            / "candidates"
            / f"candidate_{index:02d}"
        )
        script_path = directory / "script.json"
        qa_path = directory / "fact_risk_qa.json"
        self.write_json(script_path, script)
        self.write_json(qa_path, self.rejected_qa())
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
        self.write_json(directory / "metadata.json", record)
        return record, script_path

    def test_fallback_state_recovers_without_source_reference(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manual = self.build_script("Manual founder revision.")
            _, manual_path = self.build_candidate(
                root,
                17,
                manual,
            )
            reference = str(
                manual_path.relative_to(root)
            ).replace("\\", "/")
            context = self.build_context(
                root,
                reference,
                pending=False,
                chain_active=False,
                lineage_active=False,
                validation_status="fallback_to_best",
            )

            state = load_founder_manual_revision_state(
                project_root=root,
                context=context,
            )

            self.assertIsNotNone(state)
            self.assertTrue(
                state["fallback_recovery_allowed"]
            )
            self.assertEqual(
                state["revised_script_sha256"],
                hashlib.sha256(
                    manual_path.read_bytes()
                ).hexdigest(),
            )

    def test_active_lineage_preserves_repaired_descendant(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manual = self.build_script("Manual founder revision.")
            _, manual_path = self.build_candidate(
                root,
                17,
                manual,
            )
            manual_reference = str(
                manual_path.relative_to(root)
            ).replace("\\", "/")
            context = self.build_context(
                root,
                manual_reference,
                pending=False,
                chain_active=False,
                lineage_active=True,
                validation_status="approved",
            )
            repaired = self.build_script(
                "Unsupported phrase. Repaired descendant."
            )
            record, _ = self.build_candidate(
                root,
                18,
                repaired,
            )

            result = evaluate_founder_manual_candidate_policy(
                project_root=root,
                context=context,
                candidate_record=record,
                script_data=repaired,
                qa_data=self.rejected_qa(),
            )

            self.assertEqual(
                result["action"],
                "preserve_for_section_repair",
            )
            self.assertEqual(
                result["repair_target_count"],
                1,
            )

    def test_active_lineage_high_risk_still_falls_back(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manual = self.build_script("Manual founder revision.")
            _, manual_path = self.build_candidate(
                root,
                17,
                manual,
            )
            reference = str(
                manual_path.relative_to(root)
            ).replace("\\", "/")
            context = self.build_context(
                root,
                reference,
                lineage_active=True,
                validation_status="approved",
            )
            descendant = self.build_script(
                "Unsupported high-risk phrase."
            )
            record, _ = self.build_candidate(
                root,
                18,
                descendant,
            )

            result = evaluate_founder_manual_candidate_policy(
                project_root=root,
                context=context,
                candidate_record=record,
                script_data=descendant,
                qa_data=self.rejected_qa(high_risk=True),
            )

            self.assertEqual(
                result["action"],
                "fallback_to_best",
            )
            self.assertEqual(
                result["reason"],
                "manual_revision_has_high_risk_issue",
            )

    def test_active_lineage_approved_descendant_reaches_editorial(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manual = self.build_script("Manual founder revision.")
            _, manual_path = self.build_candidate(
                root,
                17,
                manual,
            )
            reference = str(
                manual_path.relative_to(root)
            ).replace("\\", "/")
            context = self.build_context(
                root,
                reference,
                lineage_active=True,
                validation_status="approved",
            )
            descendant = self.build_script(
                "Fully supported repaired descendant."
            )
            record, _ = self.build_candidate(
                root,
                19,
                descendant,
            )

            result = evaluate_founder_manual_candidate_policy(
                project_root=root,
                context=context,
                candidate_record=record,
                script_data=descendant,
                qa_data=self.approved_qa(),
            )

            self.assertEqual(
                result["action"],
                "allow_editorial_evaluation",
            )

    def test_orchestrator_preserves_lineage_at_editorial_gate(self):
        root = Path(__file__).resolve().parents[1]
        source = (
            root
            / "agents"
            / "media_video_orchestrator"
            / "run.py"
        ).read_text(encoding="utf-8-sig")

        self.assertIn(
            "manual_revision_lineage_active",
            source,
        )
        self.assertIn(
            "FOUNDER_MANUAL_AUTOMATIC_EDITORIAL_REPAIR: blocked",
            source,
        )
        self.assertIn(
            "FOUNDER_MANUAL_EDITORIAL_CANDIDATE_PRESERVED",
            source,
        )
        self.assertIn(
            "founder_manual_revision_editorial_review_required",
            source,
        )


if __name__ == "__main__":
    unittest.main()
