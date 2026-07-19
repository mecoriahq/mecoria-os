import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from core.founder_editorial_override import (
    current_editorial_scores,
    current_factual_snapshot,
    founder_editorial_override_matches,
    sha256_file,
)


QA_DATA = {
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

FACT_DATA = {
    "status": "approved",
    "factual_grounding_score": 100,
    "risk_compliance_score": 100,
    "unsupported_statements": [],
    "risk_issues": [],
}


class FounderEditorialOverrideTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

        outputs = self.root / "outputs"
        outputs.mkdir(parents=True)

        self.script_path = outputs / "script.json"
        self.qa_path = outputs / "qa.json"
        self.fact_path = outputs / "fact.json"

        self.script_path.write_text(
            json.dumps(
                {"script": {"hook": {"narration": "x"}}},
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        self.qa_path.write_text(
            json.dumps(QA_DATA, indent=2) + "\n",
            encoding="utf-8",
        )
        self.fact_path.write_text(
            json.dumps(FACT_DATA, indent=2) + "\n",
            encoding="utf-8",
        )

        factual_snapshot = current_factual_snapshot(
            FACT_DATA
        )
        editorial_scores = current_editorial_scores(
            QA_DATA
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
                    "factual_snapshot": factual_snapshot,
                    "editorial_scores": editorial_scores,
                    "script_sha256": sha256_file(
                        self.script_path
                    ),
                    "qa_sha256": sha256_file(
                        self.qa_path
                    ),
                    "fact_risk_sha256": sha256_file(
                        self.fact_path
                    ),
                },
            },
        }

    def tearDown(self):
        self.temp.cleanup()

    def evaluate(self):
        return founder_editorial_override_matches(
            project_root=self.root,
            context=self.context,
            qa_data=QA_DATA,
            fact_risk_data=FACT_DATA,
        )

    def test_exact_approved_candidate_matches(self):
        self.assertEqual(
            self.evaluate(),
            (True, "validated"),
        )

    def test_changed_script_is_rejected(self):
        self.script_path.write_text(
            '{"script":{"hook":{"narration":"changed"}}}\n',
            encoding="utf-8",
        )

        applies, reason = self.evaluate()

        self.assertFalse(applies)
        self.assertEqual(
            reason,
            "output_hash_mismatch:script",
        )

    def test_other_video_scope_is_rejected(self):
        self.context["video_id"] = "video_002"

        applies, reason = self.evaluate()

        self.assertFalse(applies)
        self.assertEqual(reason, "scope_mismatch")

    def test_unsafe_factual_output_is_rejected(self):
        unsafe = dict(FACT_DATA)
        unsafe["factual_grounding_score"] = 96

        applies, reason = (
            founder_editorial_override_matches(
                project_root=self.root,
                context=self.context,
                qa_data=QA_DATA,
                fact_risk_data=unsafe,
            )
        )

        self.assertFalse(applies)
        self.assertEqual(
            reason,
            "factual_safety_mismatch",
        )

    def test_changed_qa_score_is_rejected(self):
        changed = json.loads(json.dumps(QA_DATA))
        changed["checks"]["hook_strength"]["score"] = 81

        applies, reason = (
            founder_editorial_override_matches(
                project_root=self.root,
                context=self.context,
                qa_data=changed,
                fact_risk_data=FACT_DATA,
            )
        )

        self.assertFalse(applies)
        self.assertEqual(
            reason,
            "editorial_score_mismatch:hook_strength",
        )

    def test_changed_candidate_index_is_rejected(self):
        self.context["quality_gates"][
            "editorial_best_candidate"
        ]["candidate_index"] = 5

        applies, reason = self.evaluate()

        self.assertFalse(applies)
        self.assertEqual(
            reason,
            "candidate_index_mismatch",
        )


if __name__ == "__main__":
    unittest.main()
