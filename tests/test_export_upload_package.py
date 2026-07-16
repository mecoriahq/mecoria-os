import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.export_upload_package import (
    create_export_dir,
)


class ExportUploadPackageTests(unittest.TestCase):
    def test_video_specific_export_dir_is_created(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)

            with patch(
                "scripts.export_upload_package.PROJECT_ROOT",
                root
            ):
                export_dir = create_export_dir(
                    channel="hiddenova",
                    video_id="video_003",
                    run_id="hiddenova_video_003_v1"
                )

            self.assertTrue(export_dir.exists())
            self.assertIn(
                "hiddenova/video_003/"
                "hiddenova_video_003_v1",
                export_dir.as_posix()
            )


if __name__ == "__main__":
    unittest.main()
