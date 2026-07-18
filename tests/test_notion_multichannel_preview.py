from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from core.notion_multichannel_preview import (
    build_publishing_queue_rows,
    build_youtube_channel_rows,
)


class NotionMultichannelPreviewTests(unittest.TestCase):
    def write_json(
        self,
        path: Path,
        payload: dict,
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload),
            encoding="utf-8",
        )

    def channel_config(
        self,
        *,
        channel: str,
        display_name: str,
        production_enabled: bool,
        latest_public_video_id: str | None,
    ) -> dict:
        return {
            "channel": channel,
            "display_name": display_name,
            "status": "active",
            "production_enabled": production_enabled,
            "integrations": {
                "notion_sync": True,
            },
            "youtube": {
                "handle": display_name.replace(" ", ""),
                "latest_public_video_id": (
                    latest_public_video_id
                ),
                "public_video_count": (
                    1 if latest_public_video_id else 0
                ),
            },
            "analytics": {
                "next_action": "review",
            },
        }

    def test_youtube_preview_contains_both_channels(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_json(
                root / "config/channels/hiddenova.json",
                self.channel_config(
                    channel="hiddenova",
                    display_name="Hiddenova",
                    production_enabled=True,
                    latest_public_video_id="abc123",
                ),
            )
            rise = self.channel_config(
                channel="rise_dossier",
                display_name="Rise Dossier",
                production_enabled=False,
                latest_public_video_id=None,
            )
            rise["brand"] = {
                "domain": "risedossier.com",
                "youtube_ready": True,
            }
            self.write_json(
                root / "config/channels/rise_dossier.json",
                rise,
            )

            rows = build_youtube_channel_rows(root)

            self.assertEqual(
                [row["key"] for row in rows],
                ["hiddenova", "rise_dossier"],
            )
            self.assertEqual(
                rows[1]["properties"]["display_name"],
                "Rise Dossier",
            )
            self.assertEqual(
                rows[0]["properties"]["public_video_url"],
                "https://youtu.be/abc123",
            )

    def test_publishing_queue_uses_video_contexts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_json(
                root / "config/channels/hiddenova.json",
                self.channel_config(
                    channel="hiddenova",
                    display_name="Hiddenova",
                    production_enabled=True,
                    latest_public_video_id="abc123",
                ),
            )
            self.write_json(
                root / "config/channels/rise_dossier.json",
                self.channel_config(
                    channel="rise_dossier",
                    display_name="Rise Dossier",
                    production_enabled=False,
                    latest_public_video_id=None,
                ),
            )
            self.write_json(
                (
                    root
                    / "records/run_contexts/hiddenova"
                    / "video_005.json"
                ),
                {
                    "channel": "hiddenova",
                    "video_id": "video_005",
                    "run_id": "hiddenova_video_005_v1",
                    "status": "public",
                    "topic_title": "Waste Systems",
                    "outputs": {
                        "video_file_path": "video.mp4",
                        "thumbnail_image_path": "thumb.jpg",
                    },
                    "quality_gates": {},
                    "release": {
                        "youtube_url": (
                            "https://youtu.be/abc123"
                        ),
                        "visibility": "public",
                    },
                    "next_agent": "analytics_48h",
                },
            )

            rows = build_publishing_queue_rows(root)

            self.assertEqual(len(rows), 1)
            self.assertEqual(
                rows[0]["key"],
                "hiddenova:video_005",
            )
            self.assertEqual(
                rows[0]["properties"]["source_record"],
                (
                    "records/run_contexts/hiddenova/"
                    "video_005.json"
                ),
            )
            self.assertNotEqual(
                rows[0]["key"],
                "publisher_latest",
            )
            self.assertFalse(
                rows[0]["properties"][
                    "source_record"
                ].endswith("latest.json")
            )

    def test_channel_filter_is_supported(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for channel, display_name in [
                ("hiddenova", "Hiddenova"),
                ("rise_dossier", "Rise Dossier"),
            ]:
                self.write_json(
                    root / f"config/channels/{channel}.json",
                    self.channel_config(
                        channel=channel,
                        display_name=display_name,
                        production_enabled=False,
                        latest_public_video_id=None,
                    ),
                )

            rows = build_youtube_channel_rows(
                root,
                channel_filter="rise_dossier",
            )

            self.assertEqual(
                [row["key"] for row in rows],
                ["rise_dossier"],
            )


if __name__ == "__main__":
    unittest.main()
