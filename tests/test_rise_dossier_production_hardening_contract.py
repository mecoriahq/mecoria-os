import json
import unittest
from pathlib import Path


class RiseDossierProductionHardeningContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[1]
        cls.orchestrator = (
            cls.root / "agents" / "media_video_orchestrator" / "run.py"
        ).read_text(encoding="utf-8-sig")
        cls.script = (
            cls.root / "agents" / "script" / "run.py"
        ).read_text(encoding="utf-8-sig")
        cls.repair = (
            cls.root / "agents" / "script_section_repair" / "run.py"
        ).read_text(encoding="utf-8-sig")
        cls.qa = (
            cls.root / "agents" / "qa" / "run.py"
        ).read_text(encoding="utf-8-sig")
        cls.fact_qa = (
            cls.root / "agents" / "fact_risk_qa" / "run.py"
        ).read_text(encoding="utf-8-sig")
        cls.seo = (
            cls.root / "agents" / "seo" / "run.py"
        ).read_text(encoding="utf-8-sig")
        cls.profile = json.loads(
            (
                cls.root
                / "config"
                / "editorial_profiles"
                / "rise_dossier.json"
            ).read_text(encoding="utf-8-sig")
        )
        cls.fixture = json.loads(
            (
                cls.root
                / "tests"
                / "fixtures"
                / "rise_dossier"
                / "theranos_production_hardening.json"
            ).read_text(encoding="utf-8-sig")
        )

    def test_locked_factual_candidate_is_recoverable(self):
        self.assertIn("recover_locked_factual_candidate", self.orchestrator)
        self.assertIn("FACTUAL_APPROVED_SCRIPT_RESTORED", self.orchestrator)
        self.assertIn(
            "SCRIPT_GENERATION_CONTROLLED_PAUSE",
            self.script,
        )
        self.assertEqual(
            self.fixture["locked_factual_candidate"]["factual_grounding_score"],
            100,
        )

    def test_factual_channel_uses_section_editorial_repairs(self):
        self.assertIn("write_editorial_section_repair_brief", self.orchestrator)
        self.assertIn("FULL_SCRIPT_REWRITE: false", self.orchestrator)
        self.assertIn("editorial_section_repair_brief", self.repair)
        self.assertIn("repair_mode == \"editorial\"", self.repair)
        self.assertIn(
            "SECTION_REPAIR_VALIDATION_PAUSE",
            self.repair,
        )
        self.assertEqual(self.profile["qa"]["revision_mode"], "section_level")
        self.assertIn(
            'gates["fact_risk_section_repair_count"] = 0',
            self.orchestrator,
        )

    def test_worse_candidates_are_rejected(self):
        self.assertIn("consider_editorial_candidate", self.orchestrator)
        self.assertIn("worse_candidate_rejected", self.orchestrator)
        self.assertIn("factually_equivalent_candidate", self.orchestrator)

    def test_founder_manual_revision_is_repaired_before_fallback(self):
        self.assertIn(
            "recover_pending_founder_manual_revision_candidate",
            self.orchestrator,
        )
        self.assertIn(
            "FOUNDER_MANUAL_FACTUAL_CANDIDATE_PRESERVED",
            self.orchestrator,
        )
        self.assertIn(
            "founder_manual_candidate_repair_required",
            self.orchestrator,
        )
        candidate_manager = (
            self.root
            / "core"
            / "script_candidate_manager.py"
        ).read_text(encoding="utf-8-sig")
        self.assertIn(
            "evaluate_founder_manual_candidate_policy",
            candidate_manager,
        )
        self.assertIn(
            "find_recoverable_founder_manual_candidate",
            candidate_manager,
        )
        self.assertIn(
            "manual_revision_has_high_risk_issue",
            candidate_manager,
        )

    def test_all_model_agents_retry_empty_responses(self):
        for source in (
            self.script,
            self.repair,
            self.qa,
            self.fact_qa,
            self.seo,
        ):
            self.assertIn("call_with_retry", source)
            self.assertIn("max_attempts=3", source)

    def test_exhausted_model_calls_pause_without_stack_trace(self):
        self.assertIn("CONTROLLED_MODEL_RETRY_STATUS", self.orchestrator)
        self.assertIn("PIPELINE_CONTROLLED_PAUSE", self.orchestrator)
        model_pause = (
            self.root / "core" / "model_pause.py"
        ).read_text(encoding="utf-8-sig")
        self.assertIn("model_retry_required", model_pause)
        self.assertEqual(
            self.profile["qa"]["fallback_status"],
            "founder_editorial_review_required",
        )

    def test_quality_limits_pause_instead_of_crashing(self):
        self.assertIn(
            "pause_for_founder_factual_review",
            self.orchestrator,
        )
        self.assertIn(
            "factual_research_revision_limit_reached",
            self.orchestrator,
        )
        self.assertIn(
            "claims_ledger_revision_limit_reached",
            self.orchestrator,
        )
        self.assertIn(
            "script_preflight_rejected",
            self.orchestrator,
        )


if __name__ == "__main__":
    unittest.main()
