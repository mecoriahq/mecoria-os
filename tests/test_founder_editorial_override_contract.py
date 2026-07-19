import unittest
from pathlib import Path


class FounderEditorialOverrideContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.orchestrator = (
            root
            / "agents"
            / "media_video_orchestrator"
            / "run.py"
        ).read_text(encoding="utf-8-sig")

    def test_orchestrator_consumes_validated_override(self):
        self.assertIn(
            "founder_editorial_override_matches",
            self.orchestrator,
        )
        self.assertIn(
            "consume_founder_editorial_override",
            self.orchestrator,
        )
        self.assertIn(
            "FOUNDER_EDITORIAL_OVERRIDE_CONSUMED",
            self.orchestrator,
        )

    def test_override_is_checked_before_repair_limit(self):
        override_position = self.orchestrator.index(
            "consume_founder_editorial_override("
        )
        gate_position = self.orchestrator.index(
            'if gate_result["approved"]:',
            override_position,
        )
        repair_position = self.orchestrator.index(
            "max_revisions = int(",
            gate_position,
        )

        self.assertLess(
            override_position,
            gate_position,
        )
        self.assertLess(
            gate_position,
            repair_position,
        )


if __name__ == "__main__":
    unittest.main()
