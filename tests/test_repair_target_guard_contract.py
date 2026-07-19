import unittest
from pathlib import Path


class RepairTargetGuardContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.repair_agent = (
            root
            / "agents"
            / "script_section_repair"
            / "run.py"
        ).read_text(encoding="utf-8-sig")
        cls.orchestrator = (
            root
            / "agents"
            / "media_video_orchestrator"
            / "run.py"
        ).read_text(encoding="utf-8-sig")

    def test_repair_agent_filters_targets_against_script(self):
        self.assertIn(
            "resolve_repair_targets_for_script",
            self.repair_agent,
        )
        self.assertIn(
            "STALE_REPAIR_TARGET_COUNT",
            self.repair_agent,
        )
        self.assertIn(
            "RELOCATED_REPAIR_TARGET_COUNT",
            self.repair_agent,
        )

    def test_orchestrator_filters_before_writing_brief(self):
        self.assertIn(
            "resolve_repair_targets_for_script",
            self.orchestrator,
        )
        self.assertIn(
            "STALE_FACT_RISK_TARGET_COUNT",
            self.orchestrator,
        )
        self.assertIn(
            "STALE_FACT_RISK_QA_INVALIDATED",
            self.orchestrator,
        )


if __name__ == "__main__":
    unittest.main()
