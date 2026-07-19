import unittest

from core.factuality import (
    build_claims_ledger,
    validate_script_claim_references,
)


def build_dossier(
    approved_count: int,
    blocked_count: int,
) -> dict:
    sources = [
        {
            "source_id": "S01",
            "title": "Primary source",
            "url": "https://example.com/primary",
            "publisher": "Example",
            "source_type": "primary",
            "reliability": "high",
        },
        {
            "source_id": "S02",
            "title": "Secondary source",
            "url": "https://example.com/secondary",
            "publisher": "Example",
            "source_type": "secondary",
            "reliability": "high",
        },
    ]
    claims = []

    for index in range(approved_count):
        claims.append({
            "claim_id": f"A{index + 1:02d}",
            "claim": f"Approved claim {index + 1}.",
            "claim_type": "fact",
            "sensitivity": "low",
            "source_ids": ["S01"],
        })

    for index in range(blocked_count):
        claims.append({
            "claim_id": f"B{index + 1:02d}",
            "claim": f"Blocked claim {index + 1}.",
            "claim_type": "legal_conclusion",
            "sensitivity": "high",
            "source_ids": ["S01"],
        })

    return {
        "sources": sources,
        "candidate_claims": claims,
    }


class ClaimsLedgerQuarantineTests(unittest.TestCase):
    def test_sufficient_approved_claims_can_continue(self):
        ledger = build_claims_ledger(
            dossier=build_dossier(19, 6),
            minimum_sources_per_high_risk_claim=2,
            minimum_approved_claims=15,
            minimum_coverage_rate=0.6,
        )

        self.assertEqual(ledger["status"], "approved")
        self.assertTrue(
            ledger["summary"]["continuation_eligible"]
        )
        self.assertEqual(
            ledger["summary"]["approved_claim_count"],
            19,
        )
        self.assertEqual(
            ledger["summary"]["quarantined_claim_count"],
            6,
        )

    def test_too_few_approved_claims_still_rejects(self):
        ledger = build_claims_ledger(
            dossier=build_dossier(14, 6),
            minimum_sources_per_high_risk_claim=2,
            minimum_approved_claims=15,
            minimum_coverage_rate=0.6,
        )

        self.assertEqual(ledger["status"], "rejected")
        self.assertFalse(
            ledger["summary"]["continuation_eligible"]
        )

    def test_low_coverage_still_rejects(self):
        ledger = build_claims_ledger(
            dossier=build_dossier(15, 15),
            minimum_sources_per_high_risk_claim=2,
            minimum_approved_claims=15,
            minimum_coverage_rate=0.6,
        )

        self.assertEqual(ledger["status"], "rejected")

    def test_quarantined_claim_cannot_enter_script(self):
        ledger = build_claims_ledger(
            dossier=build_dossier(19, 6),
            minimum_sources_per_high_risk_claim=2,
            minimum_approved_claims=15,
            minimum_coverage_rate=0.6,
        )
        script = {
            "script": {
                "hook": {
                    "narration": "A blocked claim.",
                    "claim_ids": ["B01"],
                },
                "introduction": {
                    "narration": "An approved claim.",
                    "claim_ids": ["A01"],
                },
                "main_sections": [
                    {
                        "title": "Section",
                        "narration": "An approved claim.",
                        "claim_ids": ["A02"],
                    }
                ],
                "conclusion": {
                    "narration": "An approved claim.",
                    "claim_ids": ["A03"],
                },
                "call_to_action": {
                    "narration": "Comment, like, and subscribe.",
                    "claim_ids": [],
                },
            }
        }

        result = validate_script_claim_references(
            script,
            ledger,
        )

        self.assertFalse(result["approved"])
        self.assertTrue(
            any(
                "blocked_claim_used=hook:B01" in error
                for error in result["errors"]
            )
        )


if __name__ == "__main__":
    unittest.main()
