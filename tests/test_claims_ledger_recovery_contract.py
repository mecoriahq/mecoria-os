import json
import unittest
from pathlib import Path


class ClaimsLedgerRecoveryContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.orchestrator = (
            root
            / "agents"
            / "media_video_orchestrator"
            / "run.py"
        ).read_text(encoding="utf-8-sig")
        cls.claims_agent = (
            root
            / "agents"
            / "claims_ledger"
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

    def test_legacy_rejected_ledger_is_rebuilt(self):
        self.assertIn(
            "invalidate_stale_claims_ledger",
            self.orchestrator,
        )
        self.assertIn(
            "legacy_all_or_nothing_policy",
            self.orchestrator,
        )

    def test_claims_agent_uses_quarantine_thresholds(self):
        self.assertIn(
            "minimum_approved_claims_for_script",
            self.claims_agent,
        )
        self.assertIn(
            "minimum_claim_coverage_rate",
            self.claims_agent,
        )

    def test_rise_dossier_policy_is_explicit(self):
        factuality = self.profile["factuality"]
        self.assertEqual(
            factuality["minimum_approved_claims_for_script"],
            15,
        )
        self.assertEqual(
            factuality["minimum_claim_coverage_rate"],
            0.6,
        )
        self.assertEqual(
            factuality["blocked_claim_policy"],
            "quarantine",
        )


if __name__ == "__main__":
    unittest.main()
