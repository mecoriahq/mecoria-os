import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = PROJECT_ROOT / "scripts" / "mecoria_media.py"


def load_runner():
    spec = importlib.util.spec_from_file_location(
        "mecoria_media_reliability_runner",
        RUNNER_PATH,
    )

    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load runner.")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RUNNER = load_runner()


class MediaRunnerReliabilityTests(unittest.TestCase):
    def test_help_exposes_generic_founder_commands(self):
        result = subprocess.run(
            [sys.executable, str(RUNNER_PATH), "--help"],
            cwd=PROJECT_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("approve-topic", result.stdout)
        self.assertIn("approve-editorial", result.stdout)
        self.assertIn("approve-video", result.stdout)

    def test_boeing_checkpoint_is_auto_recoverable(self):
        context = json.loads(
            (
                PROJECT_ROOT
                / "records"
                / "run_contexts"
                / "rise_dossier"
                / "video_002.json"
            ).read_text(encoding="utf-8-sig")
        )
        self.assertEqual(
            RUNNER.classify_context(context),
            "resume_existing",
        )

    def test_video_approved_state_waits_for_upload(self):
        context = {
            "channel": "hiddenova",
            "video_id": "video_006",
            "run_id": "hiddenova_video_006_v1",
            "status": "video_approved_for_upload",
            "topic_title": "Example",
            "release": {"topic_approved": True},
        }
        self.assertEqual(
            RUNNER.classify_context(context),
            "wait_youtube_upload",
        )


if __name__ == "__main__":
    unittest.main()
