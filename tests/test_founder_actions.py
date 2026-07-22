import copy
import json
import tempfile
import unittest
from pathlib import Path

from core.founder_actions import (
    FounderActionError,
    approve_editorial_context,
    approve_video_context,
)


class FounderActionsTests(unittest.TestCase):
    def write_json(self, path: Path, payload: dict) -> str:
        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        path.write_text(
            json.dumps(payload, indent=2) + "\n",
            encoding="utf-8",
        )
        return str(path)

    def build_editorial_fixture(
        self,
        root: Path,
        *,
        factual_status: str = "approved",
    ) -> dict:
        script = {
            "channel": "rise_dossier",
            "video_id": "video_002",
            "run_id": "rise_dossier_video_002_v1",
            "script": {
                "hook": {"narration": "A factual hook."},
            },
        }
        qa = {
            "status": "rejected",
            "overall_score": 82,
            "checks": {
                "hook_strength": {"score": 86},
                "hook_intro_distinctness": {"score": 84},
                "narrative_spine": {"score": 88},
                "specificity": {"score": 86},
                "repetition_risk": {"score": 50},
                "title_thumbnail_synergy": {"score": 88},
                "standard_cta": {"score": 100},
            },
        }
        fact = {
            "status": factual_status,
            "factual_grounding_score": (
                100 if factual_status == "approved" else 96
            ),
            "risk_compliance_score": 100,
            "unsupported_statements": (
                [] if factual_status == "approved"
                else [{"statement": "unsupported"}]
            ),
            "risk_issues": [],
        }
        script_path = root / "script.json"
        qa_path = root / "qa.json"
        fact_path = root / "fact.json"
        self.write_json(script_path, script)
        self.write_json(qa_path, qa)
        self.write_json(fact_path, fact)
        return {
            "channel": "rise_dossier",
            "video_id": "video_002",
            "run_id": "rise_dossier_video_002_v1",
            "status": "founder_editorial_review_required",
            "next_agent": "founder_editorial_review",
            "outputs": {
                "script": "script.json",
                "qa": "qa.json",
                "fact_risk_qa": "fact.json",
            },
            "quality_gates": {
                "editorial_best_candidate": {
                    "candidate_index": 4,
                },
                "minimum_editorial_overall_score": 87,
            },
            "history": [],
        }

    def test_editorial_approval_is_hash_locked(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            context = self.build_editorial_fixture(root)
            result = approve_editorial_context(
                project_root=root,
                context=context,
                reason="Founder accepts the factual-safe script.",
            )
            override = result["override"]
            self.assertTrue(override["approved"])
            self.assertEqual(
                override["override_version"],
                2,
            )
            self.assertEqual(
                len(override["script_sha256"]),
                64,
            )
            self.assertEqual(
                result["context"]["status"],
                "fact_risk_qa_ready",
            )
            self.assertEqual(
                result["context"]["next_agent"],
                "qa",
            )

    def test_editorial_approval_rejects_unsafe_script(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            context = self.build_editorial_fixture(
                root,
                factual_status="rejected",
            )

            with self.assertRaises(FounderActionError):
                approve_editorial_context(
                    project_root=root,
                    context=context,
                    reason="Unsafe approval attempt.",
                )

    def test_editorial_approval_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            context = self.build_editorial_fixture(root)
            first = approve_editorial_context(
                project_root=root,
                context=context,
                reason="Approved.",
            )
            second = approve_editorial_context(
                project_root=root,
                context=first["context"],
                reason="Approved again.",
            )
            self.assertFalse(first["already_approved"])
            self.assertTrue(second["already_approved"])

    def test_video_approval_is_idempotent(self):
        context = {
            "channel": "hiddenova",
            "video_id": "video_006",
            "run_id": "hiddenova_video_006_v1",
            "status": "founder_review_required",
            "next_agent": "founder_video_review",
            "release": {},
            "history": [],
        }
        first = approve_video_context(
            context=context,
            reason="Founder approved.",
        )
        second = approve_video_context(
            context=first["context"],
            reason="Founder approved again.",
        )
        self.assertFalse(first["already_approved"])
        self.assertTrue(second["already_approved"])
        self.assertEqual(
            first["context"]["status"],
            "video_approved_for_upload",
        )
        self.assertFalse(
            first["context"]["release"].get(
                "public_release_approved",
                False,
            )
        )


if __name__ == "__main__":
    unittest.main()
