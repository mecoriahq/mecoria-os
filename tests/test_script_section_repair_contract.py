import json
import unittest
from pathlib import Path

from core.script_candidate_manager import (
    candidate_is_better,
    extract_repair_targets,
    qa_metrics,
)


class ScriptSectionRepairContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[1]
        cls.fixture = json.loads(
            (
                cls.root
                / "tests"
                / "fixtures"
                / "rise_dossier"
                / "theranos_candidate_repair.json"
            ).read_text(encoding="utf-8-sig")
        )
        cls.orchestrator = (
            cls.root
            / "agents"
            / "media_video_orchestrator"
            / "run.py"
        ).read_text(encoding="utf-8-sig")
        cls.repair_agent = (
            cls.root
            / "agents"
            / "script_section_repair"
            / "run.py"
        ).read_text(encoding="utf-8-sig")
        cls.profile = json.loads(
            (
                cls.root
                / "config"
                / "editorial_profiles"
                / "rise_dossier.json"
            ).read_text(encoding="utf-8-sig")
        )

    def test_theranos_better_candidate_beats_worse_revision(self):
        better = qa_metrics(
            self.fixture["better_candidate_qa"]
        )
        worse = qa_metrics(
            self.fixture["worse_candidate_qa"]
        )

        self.assertTrue(
            candidate_is_better(better, worse)
        )
        self.assertEqual(
            better["unsupported_statement_count"],
            5,
        )
        self.assertEqual(
            worse["unsupported_statement_count"],
            16,
        )

    def test_theranos_targets_only_flagged_sections(self):
        better_targets = extract_repair_targets(
            self.fixture["better_candidate_qa"]
        )
        worse_targets = extract_repair_targets(
            self.fixture["worse_candidate_qa"]
        )

        self.assertEqual(
            len(better_targets),
            self.fixture[
                "expected_better_unique_repair_locations"
            ],
        )
        self.assertEqual(
            len(worse_targets),
            self.fixture[
                "expected_worse_unique_repair_locations"
            ],
        )
        self.assertNotIn(
            "hook.narration",
            [
                item["location"]
                for item in worse_targets
            ],
        )

    def test_orchestrator_preserves_best_candidate(self):
        self.assertIn(
            "archive_fact_risk_candidate",
            self.orchestrator,
        )
        self.assertIn(
            "worse_candidate_rejected",
            self.orchestrator,
        )
        self.assertIn(
            "restore_best_candidate_script",
            self.orchestrator,
        )
        self.assertIn(
            "script_section_repair",
            self.orchestrator,
        )
        self.assertNotIn(
            "write_fact_risk_revision_brief(\n"
            "                    context=context,\n"
            "                    fact_risk_data=fact_risk_data,",
            self.orchestrator,
        )

    def test_repair_agent_is_section_scoped(self):
        self.assertIn(
            "Repair ONLY the narration blocks listed below",
            self.repair_agent,
        )
        self.assertIn(
            "merge_script_repairs",
            self.repair_agent,
        )
        self.assertIn(
            "required_locations=target_locations",
            self.repair_agent,
        )
        self.assertIn(
            "validate_script_claim_references",
            self.repair_agent,
        )

    def test_profile_has_separate_repair_budget(self):
        factuality = self.profile["factuality"]
        self.assertEqual(
            factuality["max_section_repair_attempts"],
            3,
        )
        self.assertEqual(
            factuality["candidate_selection_policy"],
            "best_fact_risk_score",
        )


if __name__ == "__main__":
    unittest.main()
