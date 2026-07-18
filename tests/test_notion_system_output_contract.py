from __future__ import annotations

import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class NotionSystemOutputContractTests(unittest.TestCase):
    def test_notion_agents_use_system_output(self):
        agent_files = [
            "notion_ai_agents_schema_patch",
            "notion_ai_agents_sync",
            "notion_connection_test",
            "notion_os_sync_runner",
            "notion_publishing_queue_sync",
            "notion_write_test",
            "notion_youtube_channels_sync",
        ]

        for agent in agent_files:
            path = (
                PROJECT_ROOT
                / "agents"
                / agent
                / "run.py"
            )
            text = path.read_text(encoding="utf-8")

            self.assertIn(
                '"output" / "system" / "latest.json"',
                text,
                msg=agent,
            )
            self.assertNotIn(
                '"output" / "hiddenova" / "latest.json"',
                text,
                msg=agent,
            )

    def test_preview_is_multichannel_and_context_based(self):
        preview_path = (
            PROJECT_ROOT
            / "agents"
            / "notion_sync_dry_run"
            / "run.py"
        )
        preview_text = preview_path.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            'SYSTEM_OUTPUT_CHANNEL = "system"',
            preview_text,
        )
        self.assertIn(
            'default="all"',
            preview_text,
        )
        self.assertIn(
            "build_youtube_channel_rows",
            preview_text,
        )
        self.assertIn(
            "build_publishing_queue_rows",
            preview_text,
        )
        self.assertNotIn(
            'DEFAULT_CHANNEL = "hiddenova"',
            preview_text,
        )
        self.assertNotIn(
            "agents/publisher/output",
            preview_text,
        )

    def test_sync_consumers_do_not_default_to_hiddenova(self):
        publishing_path = (
            PROJECT_ROOT
            / "agents"
            / "notion_publishing_queue_sync"
            / "run.py"
        )
        publishing_text = publishing_path.read_text(
            encoding="utf-8"
        )
        youtube_path = (
            PROJECT_ROOT
            / "agents"
            / "notion_youtube_channels_sync"
            / "run.py"
        )
        youtube_text = youtube_path.read_text(
            encoding="utf-8"
        )

        self.assertNotIn(
            'props.get("channel") or "hiddenova"',
            publishing_text,
        )
        self.assertIn(
            'props.get("display_name")',
            youtube_text,
        )


if __name__ == "__main__":
    unittest.main()
