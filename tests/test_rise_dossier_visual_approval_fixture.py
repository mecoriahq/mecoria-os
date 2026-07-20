import json
import unittest
from pathlib import Path


class RiseDossierVisualApprovalFixtureTests(unittest.TestCase):
    def test_fixture_represents_founder_approved_low_score(self):
        root = Path(__file__).resolve().parents[1]
        fixture_path = (
            root
            / "tests"
            / "fixtures"
            / "rise_dossier"
            / "effective_content_approval_video_001.json"
        )
        fixture = json.loads(
            fixture_path.read_text(encoding="utf-8")
        )

        self.assertEqual(
            fixture["qa_status"],
            "rejected",
        )
        self.assertEqual(
            fixture["qa_overall_score"],
            79,
        )
        self.assertEqual(
            fixture["minimum_content_qa_score"],
            85,
        )
        self.assertTrue(
            fixture["founder_override_valid"]
        )
        self.assertEqual(
            fixture["expected_approval_source"],
            "founder_editorial_override",
        )
        self.assertTrue(
            fixture["visual_pipeline_should_continue"]
        )


if __name__ == "__main__":
    unittest.main()
