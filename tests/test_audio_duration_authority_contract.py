import json
import unittest
from pathlib import Path


class AudioDurationAuthorityContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.script_agent = (
            root / "agents" / "script" / "run.py"
        ).read_text(encoding="utf-8-sig")
        cls.orchestrator = (
            root
            / "agents"
            / "media_video_orchestrator"
            / "run.py"
        ).read_text(encoding="utf-8-sig")
        cls.audio_pipeline = (
            root
            / "agents"
            / "video_audio_pipeline"
            / "run.py"
        ).read_text(encoding="utf-8-sig")
        cls.profile = json.loads(
            (
                root
                / "config"
                / "editorial_profiles"
                / "rise_dossier.json"
            ).read_text(encoding="utf-8-sig")
        )

    def test_script_agent_can_save_provisional_script(self):
        self.assertIn(
            "assert_script_preflight",
            self.script_agent,
        )
        self.assertIn(
            "SCRIPT_PREFLIGHT_GATE",
            self.script_agent,
        )
        self.assertIn(
            "audio_duration_authoritative",
            self.script_agent,
        )

    def test_orchestrator_accepts_preflight_before_audio(self):
        self.assertIn(
            "evaluate_context_script_preflight",
            self.orchestrator,
        )
        self.assertIn(
            "SCRIPT_PREFLIGHT_STATUS",
            self.orchestrator,
        )
        self.assertIn(
            "script_preflight_status",
            self.orchestrator,
        )

    def test_actual_audio_duration_remains_final_authority(self):
        self.assertIn(
            "get_media_duration_seconds",
            self.audio_pipeline,
        )
        self.assertIn(
            "set_duration_revision_required",
            self.audio_pipeline,
        )
        self.assertIn(
            "audio_duration_revision_required",
            self.orchestrator,
        )
        self.assertIn(
            "AUTO_SCRIPT_DURATION_REVISION",
            self.orchestrator,
        )

    def test_rise_dossier_policy_is_explicit(self):
        policy = self.profile["script"]

        self.assertEqual(
            policy["pre_audio_word_floor"],
            1100,
        )
        self.assertEqual(
            policy["pre_audio_minimum_ratio"],
            0.85,
        )
        self.assertTrue(
            policy["audio_duration_authoritative"]
        )


if __name__ == "__main__":
    unittest.main()
