import unittest

from core.fact_qa_anchoring import (
    build_anchor_retry_prompt,
    validate_fact_qa_anchors,
)


SCRIPT = {
    "script": {
        "hook": {
            "narration": "The current hook sentence is safe.",
            "claim_ids": ["C01"],
        },
        "introduction": {"narration": "Intro.", "claim_ids": []},
        "main_sections": [
            {
                "narration": (
                    "Boeing announced that the aircraft was certified."
                ),
                "claim_ids": ["C02"],
            }
        ],
        "conclusion": {"narration": "End.", "claim_ids": []},
        "call_to_action": {"narration": "Subscribe.", "claim_ids": []},
    }
}


class FactQaAnchoringTests(unittest.TestCase):
    def test_exact_current_statement_is_anchored(self):
        result = validate_fact_qa_anchors(
            script_data=SCRIPT,
            qa_data={
                "unsupported_statements": [{
                    "location": "main_sections[0].narration",
                    "statement": (
                        "Boeing announced that the aircraft was certified."
                    ),
                }]
            },
        )
        self.assertTrue(result["approved"])
        self.assertEqual(result["anchored_count"], 1)

    def test_paraphrased_or_prior_draft_statement_is_rejected(self):
        result = validate_fact_qa_anchors(
            script_data=SCRIPT,
            qa_data={
                "unsupported_statements": [{
                    "location": "hook.narration",
                    "statement": "An older unsafe hook sentence.",
                }]
            },
        )
        self.assertFalse(result["approved"])
        self.assertEqual(
            result["errors"][0]["reason"],
            "statement_not_verbatim_in_current_narration",
        )

    def test_retry_prompt_forbids_paraphrase_and_prior_drafts(self):
        prompt = build_anchor_retry_prompt(
            base_prompt="BASE",
            validation={"errors": [{"reason": "stale"}]},
        )
        self.assertIn("Do not paraphrase", prompt)
        self.assertIn("prior draft", prompt)
        self.assertIn("BASE", prompt)


if __name__ == "__main__":
    unittest.main()
