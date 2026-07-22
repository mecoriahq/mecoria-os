import copy
import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from core import model_pause


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ORCHESTRATOR_PATH = (
    PROJECT_ROOT
    / "agents"
    / "media_video_orchestrator"
    / "run.py"
)


def set_status_fixture(
    *,
    context: dict,
    status: str,
    next_agent: str,
) -> dict:
    updated = copy.deepcopy(context)
    updated["status"] = status
    updated["next_agent"] = next_agent
    return updated


class ModelRetryResumeTests(unittest.TestCase):
    def test_legacy_retry_checkpoint_resumes_failed_agent(self):
        context = {
            "status": "model_retry_required",
            "next_agent": "seo",
            "outputs": {"script": "script.json"},
            "quality_gates": {
                "model_retry_state": {
                    "agent": "seo",
                    "pause_count": 1,
                    "error_type": "RateLimitError",
                    "preserved_outputs": ["script"],
                }
            },
        }
        stream = io.StringIO()

        with (
            patch.object(
                model_pause,
                "set_status",
                side_effect=set_status_fixture,
            ),
            patch.object(model_pause, "save_context") as save,
            redirect_stdout(stream),
        ):
            updated, resumed = (
                model_pause.prepare_model_retry_resume(
                    context=context,
                )
            )

        self.assertTrue(resumed)
        self.assertEqual(
            updated["status"],
            "model_retry_resuming",
        )
        self.assertEqual(updated["next_agent"], "seo")
        self.assertEqual(
            updated["quality_gates"]["model_retry_state"][
                "resume_count"
            ],
            1,
        )
        self.assertTrue(
            updated["quality_gates"]["model_retry_state"][
                "resume_in_progress"
            ]
        )
        save.assert_called_once()
        self.assertIn("MODEL_RETRY_RESUME: started", stream.getvalue())

    def test_resume_is_idempotent_after_status_changes(self):
        context = {
            "status": "model_retry_resuming",
            "next_agent": "seo",
            "quality_gates": {
                "model_retry_state": {"agent": "seo"}
            },
        }

        with patch.object(model_pause, "save_context") as save:
            updated, resumed = (
                model_pause.prepare_model_retry_resume(
                    context=context,
                )
            )

        self.assertFalse(resumed)
        self.assertIs(updated, context)
        save.assert_not_called()

    def test_agent_mismatch_keeps_controlled_pause(self):
        context = {
            "status": "model_retry_required",
            "next_agent": "seo",
            "quality_gates": {
                "model_retry_state": {
                    "agent": "fact_risk_qa"
                }
            },
        }
        stream = io.StringIO()

        with (
            patch.object(model_pause, "save_context") as save,
            redirect_stdout(stream),
        ):
            updated, resumed = (
                model_pause.prepare_model_retry_resume(
                    context=context,
                )
            )

        self.assertFalse(resumed)
        self.assertIs(updated, context)
        save.assert_not_called()
        self.assertIn(
            "MODEL_RETRY_RESUME_BLOCKED: agent_mismatch",
            stream.getvalue(),
        )

    def test_pause_records_resume_diagnostics(self):
        context = {
            "status": "script_ready",
            "next_agent": "seo",
            "outputs": {"script": "script.json"},
            "quality_gates": {},
        }

        with (
            patch.object(
                model_pause,
                "set_status",
                side_effect=set_status_fixture,
            ),
            patch.object(model_pause, "save_context"),
        ):
            updated = model_pause.record_model_retry_pause(
                context=context,
                agent="seo",
                error=RuntimeError("temporary"),
            )

        state = updated["quality_gates"]["model_retry_state"]
        self.assertEqual(state["paused_from_status"], "script_ready")
        self.assertEqual(state["paused_from_next_agent"], "seo")
        self.assertFalse(state["resume_in_progress"])

    def test_orchestrator_resumes_before_general_pause_gate(self):
        source = ORCHESTRATOR_PATH.read_text(encoding="utf-8")
        body = source.split("def run_content_phase(", 1)[1]
        resume_call = body.index("prepare_model_retry_resume(")
        checkpoint_call = body.index(
            "activate_automatic_editorial_checkpoint_recovery("
        )
        pause_gate = body.index("elif is_controlled_pause(context):")

        self.assertLess(resume_call, checkpoint_call)
        self.assertLess(checkpoint_call, pause_gate)
        self.assertIn(
            "CONTROLLED_MODEL_RETRY_STATUS,",
            source.split("CONTROLLED_PAUSE_STATES", 1)[1]
            .split("}", 1)[0],
        )


if __name__ == "__main__":
    unittest.main()
