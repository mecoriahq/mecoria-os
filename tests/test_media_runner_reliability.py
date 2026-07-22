import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = PROJECT_ROOT / "scripts" / "mecoria_media.py"


def load_runner():
    import importlib.util

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


def write_fixture(
    root: Path,
    *,
    status: str,
    script: dict,
    fact: dict,
) -> dict:
    (root / "script.json").write_text(
        json.dumps(script),
        encoding="utf-8",
    )
    (root / "fact.json").write_text(
        json.dumps(fact),
        encoding="utf-8",
    )
    return {
        "channel": "rise_dossier",
        "video_id": "video_002",
        "run_id": "rise_dossier_video_002_v1",
        "status": status,
        "topic_title": "Fixture",
        "release": {"topic_approved": True},
        "outputs": {
            "script": "script.json",
            "fact_risk_qa": "fact.json",
        },
        "quality_gates": {},
    }


def editorial_script() -> dict:
    return {
        "script": {
            "hook": {"narration": " ".join(["h"] * 100)},
            "introduction": {
                "narration": " ".join(["i"] * 100)
            },
            "main_sections": [{
                "narration": " ".join(["m"] * 1069)
            }],
            "conclusion": {
                "narration": " ".join(["c"] * 25)
            },
            "call_to_action": {
                "narration": " ".join(["a"] * 25)
            },
        }
    }


def approved_fact() -> dict:
    return {
        "status": "approved",
        "factual_grounding_score": 100,
        "risk_compliance_score": 100,
        "unsupported_statements": [],
        "risk_issues": [],
        "approved_claim_ids": [],
    }


def factual_script() -> dict:
    return {
        "script": {
            "hook": {
                "narration": "Hook.",
                "claim_ids": [],
            },
            "introduction": {
                "narration": "Introduction.",
                "claim_ids": [],
            },
            "main_sections": [{
                "narration": (
                    "Once the aircraft was grounded, the story "
                    "changed."
                ),
                "claim_ids": ["C09"],
            }],
            "conclusion": {
                "narration": "Conclusion.",
                "claim_ids": [],
            },
            "call_to_action": {
                "narration": "Comment, like, and subscribe.",
                "claim_ids": [],
            },
        }
    }


def factual_qa() -> dict:
    return {
        "status": "rejected",
        "factual_grounding_score": 98,
        "risk_compliance_score": 100,
        "unsupported_statements": [{
            "location": "main_sections[0].narration",
            "statement": "Once the aircraft was grounded...",
            "reason": "C11 is missing.",
            "suggested_action": "Attach C11 to this narration block.",
        }],
        "risk_issues": [{
            "category": "other",
            "severity": "low",
            "location": "main_sections[0].narration",
            "message": "C11 is missing.",
            "required_edit": "Add C11.",
        }],
        "approved_claim_ids": ["C09", "C11"],
    }


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

    def test_editorial_checkpoint_is_auto_recoverable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            context = write_fixture(
                root,
                status="founder_editorial_review_required",
                script=editorial_script(),
                fact=approved_fact(),
            )
            with patch.object(RUNNER, "PROJECT_ROOT", root):
                result = RUNNER.classify_context(context)
        self.assertEqual(result, "resume_existing")

    def test_factual_checkpoint_is_auto_recoverable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            context = write_fixture(
                root,
                status="founder_factual_review_required",
                script=factual_script(),
                fact=factual_qa(),
            )
            with patch.object(RUNNER, "PROJECT_ROOT", root):
                result = RUNNER.classify_context(context)
        self.assertEqual(result, "resume_existing")

    def test_status_prints_video_context_once(self):
        context = {
            "channel": "rise_dossier",
            "video_id": "video_002",
            "run_id": "rise_dossier_video_002_v1",
            "status": "founder_factual_review_required",
            "topic_title": "Fixture",
            "next_agent": "founder_factual_review",
            "release": {"topic_approved": True},
        }
        stream = io.StringIO()

        with redirect_stdout(stream):
            RUNNER.print_context_summary(context)

        self.assertEqual(
            stream.getvalue().count("VIDEO_CONTEXT_ID:"),
            1,
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
