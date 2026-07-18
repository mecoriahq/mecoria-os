import ast
import unittest
from pathlib import Path


class ThumbnailV3ExportContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.project_root = Path(__file__).resolve().parent.parent
        cls.script_path = (
            cls.project_root
            / "scripts"
            / "export_upload_package.py"
        )
        cls.source = cls.script_path.read_text(
            encoding="utf-8-sig"
        )
        cls.tree = ast.parse(cls.source)
        cls.function_names = {
            node.name
            for node in cls.tree.body
            if isinstance(node, ast.FunctionDef)
        }

    def test_export_supports_finalist_folder(self):
        self.assertIn(
            "export_thumbnail_finalists",
            self.function_names,
        )
        self.assertIn(
            "thumbnail_finalists",
            self.source,
        )

    def test_export_keeps_selected_thumbnail(self):
        self.assertIn(
            'thumbnail_target = export_dir / "thumbnail.png"',
            self.source,
        )

    def test_founder_review_scope_is_recorded(self):
        self.assertIn(
            "finalists_only",
            self.source,
        )


if __name__ == "__main__":
    unittest.main()
