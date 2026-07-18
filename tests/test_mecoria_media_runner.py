import json
import tempfile
import unittest
from pathlib import Path

from scripts.mecoria_media import (
    RunnerError,
    active_contexts,
    build_orchestrator_command,
    build_storyblocks_bridge_command,
    classify_context,
    list_contexts,
    next_video_id,
    normalize_channel,
    normalize_video_id,
    resolve_run_target,
)


class MecoriaMediaRunnerTests(unittest.TestCase):
    def build_context(
        self,
        video_id: str,
        status: str,
        topic_approved: bool = True,
    ) -> dict:
        return {
            "schema_version": "1.0",
            "channel": "hiddenova",
            "video_id": video_id,
            "run_id": f"hiddenova_{video_id}_v1",
            "status": status,
            "topic_title": f"Topic {video_id}",
            "sources": {},
            "outputs": {},
            "quality_gates": {},
            "next_agent": None,
            "release": {
                "topic_approved": topic_approved,
                "public_release_approved": False,
            },
            "history": [],
        }

    def write_context(
        self,
        root: Path,
        context: dict,
    ) -> None:
        path = (
            root
            / "records"
            / "run_contexts"
            / context["channel"]
            / f"{context['video_id']}.json"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(context),
            encoding="utf-8",
        )

    def test_channel_normalization(self):
        self.assertEqual(
            normalize_channel(" Hiddenova "),
            "hiddenova",
        )

    def test_invalid_channel_is_blocked(self):
        with self.assertRaises(RunnerError):
            normalize_channel("hiddenova media")

    def test_video_id_normalization(self):
        self.assertEqual(
            normalize_video_id(" VIDEO_005 "),
            "video_005",
        )

    def test_invalid_video_id_is_blocked(self):
        with self.assertRaises(RunnerError):
            normalize_video_id("video5")

    def test_next_video_id_empty_is_video_001(self):
        self.assertEqual(
            next_video_id([]),
            "video_001",
        )

    def test_next_video_id_uses_highest_context(self):
        contexts = [
            self.build_context("video_002", "public"),
            self.build_context("video_009", "public"),
        ]

        self.assertEqual(
            next_video_id(contexts),
            "video_010",
        )

    def test_unapproved_topic_waits_for_founder(self):
        context = self.build_context(
            "video_005",
            "topic_approval_required",
            topic_approved=False,
        )

        self.assertEqual(
            classify_context(context),
            "wait_topic_approval",
        )

    def test_approved_context_resumes(self):
        context = self.build_context(
            "video_005",
            "content_qa_ready",
            topic_approved=True,
        )

        self.assertEqual(
            classify_context(context),
            "resume_existing",
        )

    def test_stock_gate_waits_for_automation(self):
        context = self.build_context(
            "video_005",
            "stock_source_required",
        )

        self.assertEqual(
            classify_context(context),
            "wait_stock_source",
        )

    def test_founder_review_waits(self):
        context = self.build_context(
            "video_005",
            "founder_review_required",
        )

        self.assertEqual(
            classify_context(context),
            "wait_founder_video_review",
        )

    def test_public_context_is_complete(self):
        context = self.build_context(
            "video_005",
            "public",
        )

        self.assertEqual(
            classify_context(context),
            "complete",
        )

    def test_single_active_context_is_resolved(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.write_context(
                root,
                self.build_context(
                    "video_004",
                    "public",
                ),
            )
            active = self.build_context(
                "video_005",
                "content_qa_ready",
            )
            self.write_context(root, active)

            video_id, context = resolve_run_target(
                channel="hiddenova",
                requested_video_id=None,
                project_root=root,
            )

            self.assertEqual(video_id, "video_005")
            self.assertEqual(
                context["status"],
                "content_qa_ready",
            )

    def test_multiple_active_contexts_are_blocked(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.write_context(
                root,
                self.build_context(
                    "video_005",
                    "content_qa_ready",
                ),
            )
            self.write_context(
                root,
                self.build_context(
                    "video_006",
                    "stock_source_required",
                ),
            )

            with self.assertRaises(RunnerError):
                resolve_run_target(
                    channel="hiddenova",
                    requested_video_id=None,
                    project_root=root,
                )

    def test_new_command_contains_selected_index(self):
        command = build_orchestrator_command(
            channel="hiddenova",
            video_id="video_005",
            action="create_new_video",
            selected_index=3,
            python_executable="python",
            project_root=Path("repo"),
        )

        self.assertIn("--selected-index", command)
        self.assertIn("3", command)
        self.assertNotIn("--resume", command)

    def test_resume_command_contains_resume_and_manifest(self):
        command = build_orchestrator_command(
            channel="hiddenova",
            video_id="video_005",
            action="resume_existing",
            stock_manifest="records/stock/video_005.json",
            python_executable="python",
            project_root=Path("repo"),
        )

        self.assertIn("--resume", command)
        self.assertIn("--stock-manifest", command)
        self.assertIn(
            "records/stock/video_005.json",
            command,
        )

    def test_storyblocks_bridge_command_is_video_specific(self):
        command = build_storyblocks_bridge_command(
            channel="hiddenova",
            video_id="video_005",
            dry_run=True,
            python_executable="python",
            project_root=Path("repo"),
        )

        self.assertIn(
            "storyblocks_bridge",
            "/".join(command).replace("\\", "/"),
        )
        self.assertIn("video_005", command)
        self.assertIn("--dry-run", command)
        self.assertIn("--no-open", command)

    def test_approve_command_contains_explicit_gate(self):
        command = build_orchestrator_command(
            channel="hiddenova",
            video_id="video_005",
            action="approve_topic",
            python_executable="python",
            project_root=Path("repo"),
        )

        self.assertIn("--approve-topic", command)
        self.assertNotIn("--resume", command)

    def test_list_contexts_is_numeric_not_lexical(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.write_context(
                root,
                self.build_context(
                    "video_010",
                    "public",
                ),
            )
            self.write_context(
                root,
                self.build_context(
                    "video_002",
                    "public",
                ),
            )

            contexts = list_contexts(
                channel="hiddenova",
                project_root=root,
            )

            self.assertEqual(
                [
                    item["video_id"]
                    for item in contexts
                ],
                ["video_002", "video_010"],
            )

    def test_uploaded_review_is_still_active(self):
        contexts = [
            self.build_context(
                "video_005",
                "uploaded_for_founder_review",
            ),
            self.build_context(
                "video_004",
                "public",
            ),
        ]

        self.assertEqual(
            [
                item["video_id"]
                for item in active_contexts(contexts)
            ],
            ["video_005"],
        )


if __name__ == "__main__":
    unittest.main()
