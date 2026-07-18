import unittest

from core.factuality import (
    build_claims_ledger,
    validate_research_dossier,
    validate_script_claim_references,
)


def build_dossier():
    sources = []

    for index in range(1, 9):
        sources.append({
            "source_id": f"S{index:02d}",
            "title": f"Source {index}",
            "url": f"https://example.com/source-{index}",
            "publisher": "Example",
            "source_type": "primary" if index <= 2 else "secondary",
            "reliability": "high",
        })

    return {
        "sources": sources,
        "candidate_claims": [
            {
                "claim_id": "C01",
                "claim": "The company launched its first product.",
                "claim_type": "fact",
                "sensitivity": "low",
                "source_ids": ["S01"],
            },
            {
                "claim_id": "C02",
                "claim": "Regulators alleged financial misconduct.",
                "claim_type": "misconduct_allegation",
                "sensitivity": "high",
                "source_ids": ["S02", "S03"],
            },
        ],
    }


class RiseDossierFactualityTests(unittest.TestCase):
    def test_valid_research_dossier_passes(self):
        dossier = build_dossier()
        cited_urls = {
            item["url"]
            for item in dossier["sources"]
        }
        result = validate_research_dossier(
            dossier=dossier,
            minimum_sources=8,
            minimum_primary_sources=2,
            cited_urls=cited_urls,
        )

        self.assertTrue(result["approved"])
        self.assertEqual(result["source_count"], 8)
        self.assertEqual(result["primary_source_count"], 2)

    def test_insufficient_sources_are_blocked(self):
        dossier = build_dossier()
        dossier["sources"] = dossier["sources"][:4]
        result = validate_research_dossier(
            dossier=dossier,
            minimum_sources=8,
            minimum_primary_sources=2,
        )

        self.assertFalse(result["approved"])
        self.assertTrue(
            any(
                item.startswith("source_count=")
                for item in result["errors"]
            )
        )

    def test_high_risk_claim_requires_two_sources(self):
        dossier = build_dossier()
        dossier["candidate_claims"][1]["source_ids"] = ["S02"]
        ledger = build_claims_ledger(
            dossier=dossier,
            minimum_sources_per_high_risk_claim=2,
        )

        self.assertEqual(ledger["status"], "rejected")
        self.assertEqual(
            ledger["claims"][1]["verification_status"],
            "blocked",
        )

    def test_script_claim_references_must_be_approved(self):
        ledger = build_claims_ledger(
            dossier=build_dossier(),
            minimum_sources_per_high_risk_claim=2,
        )
        script = {
            "script": {
                "hook": {"narration": "A launch changed the market.", "claim_ids": ["C01"]},
                "introduction": {"narration": "Regulators later alleged misconduct.", "claim_ids": ["C02"]},
                "main_sections": [
                    {"title": "Launch", "narration": "The product launched.", "claim_ids": ["C01"]}
                ],
                "conclusion": {"narration": "The decision shaped the company.", "claim_ids": ["C01"]},
                "call_to_action": {"narration": "Comment, like, and subscribe.", "claim_ids": []},
            }
        }
        result = validate_script_claim_references(script, ledger)

        self.assertTrue(result["approved"])

        script["script"]["hook"]["claim_ids"] = ["C99"]
        result = validate_script_claim_references(script, ledger)
        self.assertFalse(result["approved"])
        self.assertTrue(
            any("unknown_claim_id" in item for item in result["errors"])
        )


if __name__ == "__main__":
    unittest.main()
