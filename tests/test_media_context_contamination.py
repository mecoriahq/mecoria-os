import tempfile
import unittest
from pathlib import Path

from core.asset_usage_registry import (
    assert_asset_registered,
    build_asset_record,
    register_asset_batch,
)
from core.media_context_integrity import (
    assert_record_identity,
)
from core.video_run_context import (
    assert_no_latest_outputs,
)


class MediaContextContaminationTests(
    unittest.TestCase
):
    def setUp(self):
        self.context = {
            "channel": "hiddenova",
            "video_id": "video_002",
            "run_id": "hiddenova_video_002_v1",
            "sources": {},
            "outputs": {}
        }

    def test_all_content_record_types_reject_wrong_video(
        self
    ):
        record_types = [
            "script",
            "seo",
            "qa",
            "audio_assembly",
            "stock_manifest",
            "stock_qa",
            "thumbnail_strategy",
            "visual_asset_plan",
            "visual_plan",
            "ai_visual_generation",
            "ai_visual_qa",
            "thumbnail_record",
            "hybrid_video_assembly",
            "video_qa",
            "publisher",
        ]

        contaminated = {
            "channel": "hiddenova",
            "video_id": "video_999",
            "run_id": "hiddenova_video_999_v1"
        }

        for record_type in record_types:
            with self.subTest(
                record_type=record_type
            ):
                with self.assertRaises(ValueError):
                    assert_record_identity(
                        data=contaminated,
                        context=self.context,
                        label=record_type
                    )

    def test_wrong_run_id_is_rejected(self):
        contaminated = {
            "channel": "hiddenova",
            "video_id": "video_002",
            "run_id": "hiddenova_video_002_v999"
        }

        with self.assertRaises(ValueError):
            assert_record_identity(
                data=contaminated,
                context=self.context,
                label="script"
            )

    def test_missing_identity_is_rejected(self):
        with self.assertRaises(ValueError):
            assert_record_identity(
                data={},
                context=self.context,
                label="script"
            )

    def test_latest_output_is_rejected(self):
        contaminated_context = dict(self.context)
        contaminated_context["outputs"] = {
            "publisher": (
                "agents/publisher/output/"
                "hiddenova/latest.json"
            )
        }

        with self.assertRaises(ValueError):
            assert_no_latest_outputs(
                contaminated_context
            )

    def test_all_binary_asset_types_reject_other_video(
        self
    ):
        asset_types = [
            "stock",
            "ai_visual",
            "thumbnail",
            "narration_section",
            "narration_audio",
            "final_video",
        ]

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            registry_path = (
                root
                / "records"
                / "assets"
                / "asset_usage_registry.json"
            )

            for index, asset_type in enumerate(
                asset_types,
                start=1
            ):
                path = (
                    root
                    / "assets"
                    / f"{asset_type}_{index}.bin"
                )
                path.parent.mkdir(
                    parents=True,
                    exist_ok=True
                )
                path.write_bytes(
                    f"{asset_type}-{index}".encode(
                        "utf-8"
                    )
                )

                record = build_asset_record(
                    path=path,
                    asset_type=asset_type,
                    channel="hiddenova",
                    video_id="video_001",
                    run_id="hiddenova_video_001_v1",
                    shared_brand_asset=False,
                    project_root=root
                )

                register_asset_batch(
                    records=[record],
                    registry_path=registry_path
                )

                with self.subTest(
                    asset_type=asset_type
                ):
                    with self.assertRaises(
                        ValueError
                    ):
                        assert_asset_registered(
                            path=path,
                            channel="hiddenova",
                            video_id="video_002",
                            expected_sha256=record[
                                "sha256"
                            ],
                            registry_path=registry_path,
                            project_root=root
                        )


if __name__ == "__main__":
    unittest.main()
