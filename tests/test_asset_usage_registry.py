import tempfile
import unittest
from pathlib import Path

from core.asset_usage_registry import (
    assert_asset_registered,
    build_asset_record,
    register_asset_batch,
    validate_asset_batch,
)


class AssetUsageRegistryTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.registry = (
            self.root
            / "records"
            / "assets"
            / "asset_usage_registry.json"
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def create_file(
        self,
        relative_path: str,
        content: bytes
    ) -> Path:
        path = self.root / relative_path
        path.parent.mkdir(
            parents=True,
            exist_ok=True
        )
        path.write_bytes(content)
        return path

    def build_record(
        self,
        path: Path,
        video_id: str,
        shared: bool = False
    ) -> dict:
        return build_asset_record(
            path=path,
            asset_type="stock",
            channel="hiddenova",
            video_id=video_id,
            run_id=f"hiddenova_{video_id}_v1",
            shared_brand_asset=shared,
            project_root=self.root
        )

    def test_same_asset_same_video_is_idempotent(self):
        path = self.create_file(
            "assets/clip.mp4",
            b"same-content"
        )
        record = self.build_record(
            path,
            "video_001"
        )

        register_asset_batch(
            [record],
            registry_path=self.registry
        )
        register_asset_batch(
            [record],
            registry_path=self.registry
        )

        assert_asset_registered(
            path=path,
            channel="hiddenova",
            video_id="video_001",
            expected_sha256=record["sha256"],
            registry_path=self.registry,
            project_root=self.root
        )

    def test_renamed_same_file_is_blocked(self):
        first = self.create_file(
            "assets/video_001/clip.mp4",
            b"duplicate-content"
        )
        second = self.create_file(
            "assets/video_002/renamed.mp4",
            b"duplicate-content"
        )

        register_asset_batch(
            [
                self.build_record(
                    first,
                    "video_001"
                )
            ],
            registry_path=self.registry
        )

        with self.assertRaises(ValueError):
            validate_asset_batch(
                [
                    self.build_record(
                        second,
                        "video_002"
                    )
                ],
                registry_path=self.registry
            )

    def test_same_path_different_video_is_blocked(self):
        path = self.create_file(
            "assets/shared_path.mp4",
            b"first-content"
        )

        register_asset_batch(
            [
                self.build_record(
                    path,
                    "video_001"
                )
            ],
            registry_path=self.registry
        )

        path.write_bytes(b"new-content")

        with self.assertRaises(ValueError):
            validate_asset_batch(
                [
                    self.build_record(
                        path,
                        "video_002"
                    )
                ],
                registry_path=self.registry
            )

    def test_shared_brand_asset_can_be_reused(self):
        first = self.create_file(
            "assets/brand/intro.mp4",
            b"brand-intro"
        )
        second = self.create_file(
            "assets/brand/intro_copy.mp4",
            b"brand-intro"
        )

        register_asset_batch(
            [
                self.build_record(
                    first,
                    "video_001",
                    shared=True
                )
            ],
            registry_path=self.registry
        )

        validate_asset_batch(
            [
                self.build_record(
                    second,
                    "video_002",
                    shared=True
                )
            ],
            registry_path=self.registry
        )


if __name__ == "__main__":
    unittest.main()
