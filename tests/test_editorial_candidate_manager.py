import json
import tempfile
import unittest
from pathlib import Path

from core.editorial_candidate_manager import (
    archive_editorial_candidate,
    candidate_is_better,
    editorial_metrics,
    restore_editorial_candidate,
)


FACT_APPROVED = {
    "status": "approved",
    "factual_grounding_score": 100,
    "risk_compliance_score": 100,
    "unsupported_statements": [],
    "risk_issues": [],
}


def script(label: str) -> dict:
    return {
        "agent": "script",
        "script": {
            "title": "Theranos",
            "hook": {"narration": label, "claim_ids": ["C01"]},
            "introduction": {"narration": "Intro", "claim_ids": ["C02"]},
            "main_sections": [],
            "conclusion": {"narration": "End", "claim_ids": ["C24"]},
            "call_to_action": {"narration": "Comment, like, subscribe.", "claim_ids": []},
        },
    }


def seo(label: str) -> dict:
    return {"agent": "seo", "seo": {"video_title": label}}


def qa(score: int, failures: list[dict]) -> dict:
    return {"status": "approved" if not failures else "rejected", "overall_score": score}


class EditorialCandidateManagerTests(unittest.TestCase):
    def test_better_editorial_candidate_replaces_incumbent(self):
        weak = editorial_metrics(
            qa_data=qa(78, [{}]),
            gate_result={
                "approved": False,
                "failures": [{"check": "hook_strength", "score": 74, "minimum": 88}],
            },
            fact_risk_data=FACT_APPROVED,
        )
        strong = editorial_metrics(
            qa_data=qa(90, []),
            gate_result={"approved": True, "failures": []},
            fact_risk_data=FACT_APPROVED,
        )
        self.assertTrue(candidate_is_better(strong, weak))
        self.assertFalse(candidate_is_better(weak, strong))

    def test_worse_candidate_does_not_replace_best(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            context = {
                "channel": "rise_dossier",
                "video_id": "video_001",
                "quality_gates": {},
            }
            first = archive_editorial_candidate(
                project_root=root,
                context=context,
                script_data=script("best"),
                seo_data=seo("best"),
                qa_data=qa(88, []),
                fact_risk_data=FACT_APPROVED,
                gate_result={"approved": True, "failures": []},
            )
            second = archive_editorial_candidate(
                project_root=root,
                context=context,
                script_data=script("worse"),
                seo_data=seo("worse"),
                qa_data=qa(70, [{}]),
                fact_risk_data=FACT_APPROVED,
                gate_result={
                    "approved": False,
                    "failures": [{"check": "hook_strength", "score": 60, "minimum": 88}],
                },
            )
            self.assertTrue(first["accepted_as_best"])
            self.assertFalse(second["accepted_as_best"])

            canonical_script = root / "canonical" / "script.json"
            canonical_seo = root / "canonical" / "seo.json"
            restore_editorial_candidate(
                project_root=root,
                candidate=second["best_candidate"],
                canonical_script_path=canonical_script,
                canonical_seo_path=canonical_seo,
            )
            restored = json.loads(canonical_script.read_text())
            self.assertEqual(restored["script"]["hook"]["narration"], "best")


if __name__ == "__main__":
    unittest.main()
