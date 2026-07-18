import ast
import unittest
from pathlib import Path


class ThumbnailV3PipelineContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.project_root = Path(__file__).resolve().parent.parent
        cls.pipeline_path = (
            cls.project_root
            / "agents"
            / "video_visual_pipeline"
            / "run.py"
        )
        cls.source = cls.pipeline_path.read_text(
            encoding="utf-8-sig"
        )
        cls.tree = ast.parse(cls.source)
        cls.function_names = {
            node.name
            for node in cls.tree.body
            if isinstance(node, ast.FunctionDef)
        }

    def test_pipeline_has_actual_image_vision_qa(self):
        self.assertIn(
            "call_thumbnail_vision_qa",
            self.function_names,
        )
        self.assertIn('"type": "image_url"', self.source)

    def test_pipeline_generates_three_candidates(self):
        self.assertIn("thumbnail_concepts", self.source)
        self.assertIn("thumbnail_candidates", self.source)
        self.assertIn("candidate_count", self.source)

    def test_pipeline_records_finalists_and_selected_winner(self):
        self.assertIn("finalists_only", self.source)
        self.assertIn(
            "highest_scoring_approved_candidate",
            self.source,
        )
        self.assertIn("selected_concept_id", self.source)

    def test_pipeline_rejects_all_failed_candidates(self):
        self.assertIn(
            "All thumbnail candidates failed v3 QA",
            self.source,
        )


if __name__ == "__main__":
    unittest.main()
