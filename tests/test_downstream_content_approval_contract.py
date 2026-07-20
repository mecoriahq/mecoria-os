import unittest
from pathlib import Path


class DownstreamContentApprovalContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.visual_pipeline = (
            root
            / "agents"
            / "video_visual_pipeline"
            / "run.py"
        ).read_text(encoding="utf-8-sig")
        cls.approval_module = (
            root
            / "core"
            / "founder_editorial_override.py"
        ).read_text(encoding="utf-8-sig")

    def test_visual_pipeline_uses_effective_approval(self):
        self.assertIn(
            "effective_content_approval",
            self.visual_pipeline,
        )
        self.assertIn(
            "CONTENT_APPROVAL_SOURCE",
            self.visual_pipeline,
        )
        self.assertIn(
            "CONTENT_APPROVAL_REASON",
            self.visual_pipeline,
        )

    def test_visual_pipeline_has_no_direct_content_qa_gate(self):
        self.assertNotIn(
            'qa_data.get("status") != "approved"',
            self.visual_pipeline,
        )
        self.assertNotIn(
            "Content QA is not approved.",
            self.visual_pipeline,
        )
        self.assertNotIn(
            'qa_data.get("overall_score", 0) < minimum_qa_score',
            self.visual_pipeline,
        )
        self.assertNotIn(
            "Content QA score is below the required gate.",
            self.visual_pipeline,
        )

    def test_central_rule_supports_both_approval_sources(self):
        self.assertIn(
            'qa_data.get("status") == "approved"',
            self.approval_module,
        )
        self.assertIn(
            "founder_editorial_override_matches(",
            self.approval_module,
        )
        self.assertIn(
            '"source": "qa"',
            self.approval_module,
        )
        self.assertIn(
            '"founder_editorial_override"',
            self.approval_module,
        )


if __name__ == "__main__":
    unittest.main()
