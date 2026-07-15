import tempfile
import unittest
from pathlib import Path

from core.asset_usage_registry import (
    build_asset_record,
    load_registry,
    register_asset_batch,
    remove_asset_usage_for_path,
)


class AssetUsageReplacementTests(unittest.TestCase):
    def test_thumbnail_usage_can_be_replaced(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)

            registry_path = (
                root
                / "records"
                / "assets"
                / "registry.json"
            )

            thumbnail = (
                root
                / "assets"
                / "thumbnail.jpg"
            )

            thumbnail.parent.mkdir(
                parents=True,
                exist_ok=True
            )

            thumbnail.write_bytes(b"old-thumbnail")

            old_record = build_asset_record(
                path=thumbnail,
                asset_type="thumbnail",
                channel="hiddenova",
                video_id="video_003",
                run_id="hiddenova_video_003_v1",
                project_root=root
            )

            register_asset_batch(
                [old_record],
                registry_path=registry_path
            )

            removed = remove_asset_usage_for_path(
                path=thumbnail,
                channel="hiddenova",
                video_id="video_003",
                asset_type="thumbnail",
                registry_path=registry_path,
                project_root=root
            )

            self.assertEqual(removed, 1)

            thumbnail.write_bytes(b"new-thumbnail")

            new_record = build_asset_record(
                path=thumbnail,
                asset_type="thumbnail",
                channel="hiddenova",
                video_id="video_003",
                run_id="hiddenova_video_003_v1",
                project_root=root
            )

            register_asset_batch(
                [new_record],
                registry_path=registry_path
            )

            registry = load_registry(
                registry_path
            )

            thumbnail_assets = [
                asset
                for asset in registry["assets"].values()
                if asset["asset_type"] == "thumbnail"
            ]

            self.assertEqual(
                len(thumbnail_assets),
                1
            )

            self.assertEqual(
                thumbnail_assets[0]["sha256"],
                new_record["sha256"]
            )


if __name__ == "__main__":
    unittest.main()
