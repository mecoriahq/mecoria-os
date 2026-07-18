import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jsonschema import validate

from core import channel_registry


class ChannelRegistryTests(unittest.TestCase):
    def test_configs_validate(self):
        schema = channel_registry.load_schema()

        for config in channel_registry.list_channels():
            validate(instance=config, schema=schema)

    def test_hiddenova_is_registered_and_safe(self):
        config = channel_registry.load_channel("hiddenova")

        self.assertEqual(config["status"], "active")
        self.assertTrue(config["production_enabled"])
        self.assertFalse(
            config["pipeline"]["auto_create_next_video"]
        )
        self.assertFalse(
            config["pipeline"]["automatic_public_release"]
        )

    def test_rise_dossier_is_registered_but_blocked(self):
        config = channel_registry.load_channel("rise_dossier")

        self.assertEqual(config["display_name"], "Rise Dossier")
        self.assertEqual(config["status"], "planning")
        self.assertFalse(config["production_enabled"])
        self.assertEqual(
            config["brand"]["domain"],
            "risedossier.com",
        )
        self.assertEqual(
            config["youtube"]["handle"],
            "RiseDossier",
        )
        self.assertIn(
            "editorial_system_required",
            config["blockers"],
        )

    def test_latest_context_is_numeric_not_lexical(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            channel_dir = root / "hiddenova"
            channel_dir.mkdir(parents=True)

            for video_id in ["video_009", "video_010"]:
                (channel_dir / f"{video_id}.json").write_text(
                    json.dumps(
                        {
                            "video_id": video_id,
                            "status": "public",
                        }
                    ),
                    encoding="utf-8",
                )

            with patch.object(
                channel_registry,
                "RUN_CONTEXT_ROOT",
                root,
            ):
                latest = channel_registry.latest_context(
                    "hiddenova"
                )

            self.assertEqual(latest["video_id"], "video_010")


if __name__ == "__main__":
    unittest.main()
