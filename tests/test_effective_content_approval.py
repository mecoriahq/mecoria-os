import json
import tempfile
import unittest
from pathlib import Path

from core.founder_editorial_override import (
    current_editorial_scores,
    current_factual_snapshot,
    effective_content_approval,
    sha256_file,
)


REJECTED_QA = {
    "status": "rejected",
    "overall_score": 79,
    "checks": {
        "hook_strength": {"score": 80},
        "hook_intro_distinctness": {"score": 60},
        "narrative_spine": {"score": 88},
        "specificity": {"score": 86},
        "repetition_risk": {"score": 50},
        "title_thumbnail_synergy": {"score": 87},
        "standard_cta": {"score": 100},
    },
}

APPROVED_FACT = {
    "status": "approved",
    "factual_grounding_score": 100,
    "risk_compliance_score": 100,
    "unsupported_statements": [],
    "risk_issues": [],
}


class EffectiveContentApprovalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        outputs = self.root / "outputs"
        outputs.mkdir(parents=True)

        self.script_path = outputs / "script.json"
        self.qa_path = outputs / "qa.json"
        self.fact_path = outputs / "fact.json"

        self.script_path.write_text(
            '{"script":{"hook":{"narration":"safe"}}}\n',
            encoding="utf-8",
        )
        self.qa_path.write_text(
            json.dumps(REJECTED_QA, indent=2) + "\n",
            encoding="utf-8",
        )
        self.fact_path.write_text(
            json.dumps(APPROVED_FACT, indent=2) + "\n",
            encoding="utf-8",
        )

        self.context = {
            "channel": "rise_dossier",
            "video_id": "video_001",
            "run_id": "rise_dossier_video_001_v1",
            "outputs": {
                "script": "outputs/script.json",
                "qa": "outputs/qa.json",
                "fact_risk_qa": "outputs/fact.json",
            },
            "quality_gates": {
                "editorial_best_candidate": {
                    "candidate_index": 4,
                },
                "founder_editorial_override": {
                    "approved": True,
                    "override_version": 2,
                    "scope": (
                        "rise_dossier/video_001/"
                        "rise_dossier_video_001_v1"
                    ),
                    "global_profile_changed": False,
                    "approved_candidate_index": 4,
                    "factual_snapshot": (
                        current_factual_snapshot(
                            APPROVED_FACT
                        )
                    ),
                    "editorial_scores": (
                        current_editorial_scores(
                            REJECTED_QA
                        )
                    ),
                    "script_sha256": sha256_file(
                        self.script_path
                    ),
                    "qa_sha256": sha256_file(
                        self.qa_path
                    ),
                    "fact_risk_sha256": sha256_file(
                        self.fact_path
                    ),
                    "consumed": True,
                },
            },
        }

    def tearDown(self):
        self.temp.cleanup()

    def test_direct_qa_approval_is_accepted(self):
        result = effective_content_approval(
            project_root=self.root,
            context={},
            qa_data={"status": "approved"},
        )

        self.assertEqual(
            result,
            {
                "approved": True,
                "source": "qa",
                "reason": "qa_approved",
            },
        )

    def test_valid_founder_override_is_accepted(self):
        result = effective_content_approval(
            project_root=self.root,
            context=self.context,
            qa_data=REJECTED_QA,
        )

        self.assertTrue(result["approved"])
        self.assertEqual(
            result["source"],
            "founder_editorial_override",
        )
        self.assertEqual(
            result["reason"],
            "validated",
        )

    def test_changed_script_blocks_override(self):
        self.script_path.write_text(
            '{"script":{"hook":{"narration":"changed"}}}\n',
            encoding="utf-8",
        )

        result = effective_content_approval(
            project_root=self.root,
            context=self.context,
            qa_data=REJECTED_QA,
        )

        self.assertFalse(result["approved"])
        self.assertEqual(
            result["reason"],
            "output_hash_mismatch:script",
        )

    def test_missing_fact_output_is_blocked(self):
        self.context["outputs"].pop("fact_risk_qa")

        result = effective_content_approval(
            project_root=self.root,
            context=self.context,
            qa_data=REJECTED_QA,
        )

        self.assertFalse(result["approved"])
        self.assertEqual(
            result["reason"],
            "fact_risk_output_missing",
        )

    def test_unsafe_fact_output_is_blocked(self):
        unsafe = dict(APPROVED_FACT)
        unsafe["factual_grounding_score"] = 96

        result = effective_content_approval(
            project_root=self.root,
            context=self.context,
            qa_data=REJECTED_QA,
            fact_risk_data=unsafe,
        )

        self.assertFalse(result["approved"])
        self.assertEqual(
            result["reason"],
            "factual_safety_mismatch",
        )


if __name__ == "__main__":
    unittest.main()
