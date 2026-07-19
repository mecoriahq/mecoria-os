import importlib.util
import argparse
import unittest
from unittest.mock import patch
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "mecoria_media.py"


def load_runner():
    spec = importlib.util.spec_from_file_location(
        "mecoria_media_runner_hardening",
        SCRIPT,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class ControlledPauseRunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runner = load_runner()

    def context(self, status: str) -> dict:
        return {
            "channel": "rise_dossier",
            "video_id": "video_001",
            "run_id": "rise_dossier_video_001_v1",
            "status": status,
            "topic_title": "Theranos",
            "release": {"topic_approved": True},
        }

    def test_model_retry_is_not_reported_as_crash(self):
        context = self.context("model_retry_required")
        self.assertEqual(
            self.runner.classify_context(context),
            "retry_model",
        )
        self.assertIn(
            "run rise_dossier",
            self.runner.next_command(context, "retry_model"),
        )

    def test_editorial_pause_is_founder_action(self):
        context = self.context(
            "founder_editorial_review_required"
        )
        self.assertEqual(
            self.runner.classify_context(context),
            "wait_founder_editorial_review",
        )

    def test_factual_pause_is_founder_action(self):
        context = self.context(
            "founder_factual_review_required"
        )
        self.assertEqual(
            self.runner.classify_context(context),
            "wait_founder_factual_review",
        )

    def test_founder_review_states_never_auto_resume(self):
        for status in (
            "founder_editorial_review_required",
            "founder_factual_review_required",
        ):
            context = self.context(status)
            args = argparse.Namespace(
                channel="rise_dossier",
                video_id="video_001",
                stock_manifest=None,
                selected_index=None,
                dry_run=False,
            )

            with (
                patch.object(
                    self.runner,
                    "resolve_run_target",
                    return_value=("video_001", context),
                ),
                patch.object(
                    self.runner,
                    "run_orchestrator",
                ) as run_orchestrator,
            ):
                self.runner.execute_run(args)

            run_orchestrator.assert_not_called()


if __name__ == "__main__":
    unittest.main()
