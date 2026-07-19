import json
import unittest
from pathlib import Path

from core.script_preflight import (
    assert_script_preflight,
    evaluate_script_preflight,
)


def script_with_words(count: int) -> dict:
    narration = " ".join(
        f"word{index}"
        for index in range(count)
    )
    return {
        "script": {
            "hook": {"narration": narration},
            "introduction": {"narration": ""},
            "main_sections": [],
            "conclusion": {"narration": ""},
            "call_to_action": {"narration": ""},
        }
    }


class ScriptPreflightGateTests(unittest.TestCase):
    def test_target_range_passes(self):
        result = evaluate_script_preflight(
            script_data=script_with_words(1340),
            target_minimum=1325,
            target_maximum=1550,
        )

        self.assertEqual(result["status"], "passed")
        self.assertTrue(result["accepted"])

    def test_theranos_1213_is_provisional(self):
        result = evaluate_script_preflight(
            script_data=script_with_words(1213),
            target_minimum=1325,
            target_maximum=1550,
            absolute_floor=1100,
            minimum_ratio=0.85,
            audio_duration_authoritative=True,
        )

        self.assertEqual(result["status"], "provisional")
        self.assertTrue(result["accepted"])
        self.assertEqual(result["provisional_floor"], 1127)
        self.assertEqual(
            result["next_gate"],
            "fact_risk_qa_then_audio_duration",
        )

    def test_theranos_1039_is_rejected(self):
        result = evaluate_script_preflight(
            script_data=script_with_words(1039),
            target_minimum=1325,
            target_maximum=1550,
            absolute_floor=1100,
            minimum_ratio=0.85,
        )

        self.assertEqual(result["status"], "rejected")
        self.assertFalse(result["accepted"])
        self.assertEqual(
            result["reason"],
            "below_pre_audio_word_floor",
        )

    def test_above_maximum_is_rejected(self):
        result = evaluate_script_preflight(
            script_data=script_with_words(1600),
            target_minimum=1325,
            target_maximum=1550,
        )

        self.assertEqual(result["status"], "rejected")
        self.assertEqual(
            result["reason"],
            "above_target_maximum",
        )

    def test_duration_authority_can_be_disabled(self):
        result = evaluate_script_preflight(
            script_data=script_with_words(1213),
            target_minimum=1325,
            target_maximum=1550,
            audio_duration_authoritative=False,
        )

        self.assertEqual(result["status"], "rejected")

    def test_assert_accepts_provisional(self):
        result = assert_script_preflight(
            script_data=script_with_words(1221),
            target_minimum=1325,
            target_maximum=1550,
        )

        self.assertEqual(result["status"], "provisional")

    def test_exact_theranos_fixture(self):
        root = Path(__file__).resolve().parents[1]
        fixture = json.loads(
            (
                root
                / "tests"
                / "fixtures"
                / "rise_dossier"
                / "theranos_stabilization.json"
            ).read_text(encoding="utf-8")
        )

        observed = []

        for candidate in fixture["observed_candidates"]:
            result = evaluate_script_preflight(
                script_data=script_with_words(
                    candidate["word_count"]
                ),
                target_minimum=fixture[
                    "target_word_range"
                ]["minimum"],
                target_maximum=fixture[
                    "target_word_range"
                ]["maximum"],
                absolute_floor=fixture[
                    "pre_audio_policy"
                ]["absolute_floor"],
                minimum_ratio=fixture[
                    "pre_audio_policy"
                ]["minimum_ratio"],
                audio_duration_authoritative=True,
            )
            observed.append(result["status"])

        self.assertEqual(
            observed,
            [
                item["expected_status"]
                for item in fixture["observed_candidates"]
            ],
        )
        self.assertEqual(
            fixture["final_duration_authority"],
            "actual_tts_audio",
        )


if __name__ == "__main__":
    unittest.main()
