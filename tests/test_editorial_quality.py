import unittest
from pathlib import Path

from core.content_quality import (
    evaluate_editorial_structure,
    evaluate_hiddenova_channel_contract,
    evaluate_qa_editorial_gate,
)


def make_strong_script() -> dict:
    return {
        "script": {
            "hook": {
                "narration": (
                    "A cashier sees APPROVED, but the money has not "
                    "moved. The terminal has only asked a bank for "
                    "temporary permission. Before the receipt prints, "
                    "the request crosses a processor, a card network, "
                    "the issuing bank, and several risk checks. Each "
                    "system has milliseconds to decide whether the "
                    "purchase is genuine, affordable, and allowed. "
                    "That creates the central question: who actually "
                    "decides whether one ordinary card tap succeeds?"
                )
            },
            "introduction": {
                "narration": (
                    "This is Hiddenova. Follow one ten-dollar purchase "
                    "from the reader to "
                    "final settlement. The first stage captures a token "
                    "and merchant data. The second routes the message "
                    "through the merchant's acquirer. The third asks the "
                    "issuer to evaluate funds and fraud signals. Only "
                    "later do clearing files calculate obligations and "
                    "settlement transfers value between institutions. "
                    "This sequence explains why a payment can be "
                    "approved in seconds while still appearing as "
                    "pending for much longer."
                )
            },
            "main_sections": [
                {
                    "title": "The Terminal Builds the Request",
                    "narration": (
                        "The reader combines the amount, merchant "
                        "identity, device data, and a protected card "
                        "credential. Because the message must follow a "
                        "shared format, the processor can validate it "
                        "before routing it onward."
                    )
                },
                {
                    "title": "The Acquirer Opens the Route",
                    "narration": (
                        "The merchant does not maintain a direct "
                        "connection to every bank. Instead, the acquirer "
                        "represents the merchant and forwards the request, "
                        "which means one connection can reach many issuers."
                    )
                },
                {
                    "title": "The Network Finds the Issuer",
                    "narration": (
                        "The card network reads routing data and sends the "
                        "message to the correct issuer. Yet it still does "
                        "not move the final funds; it coordinates rules "
                        "and communication."
                    )
                },
                {
                    "title": "The Issuer Prices the Risk",
                    "narration": (
                        "The issuer checks account status, available "
                        "funds, location, merchant type, and recent "
                        "activity. As a result, one response compresses "
                        "several financial and security decisions."
                    )
                },
                {
                    "title": "Settlement Finishes the Journey",
                    "narration": (
                        "Approval reserves permission. Clearing later "
                        "calculates fees and obligations, therefore "
                        "settlement can transfer the net value after the "
                        "customer has already left the store."
                    )
                },
            ],
            "conclusion": {
                "narration": (
                    "The beep is not the payment's ending. It is the "
                    "fastest decision in a longer chain of routing, risk, "
                    "clearing, and settlement."
                )
            },
            "call_to_action": {
                "narration": (
                    "Comment with the next system you want decoded, "
                    "like this documentary, and subscribe to Hiddenova "
                    "for more stories about everyday technology."
                )
            },
        }
    }


def make_repetitive_script() -> dict:
    repeated = (
        "This hidden system works beneath the surface of the modern "
        "world. The quiet technology feels deceptively simple. "
    )

    data = make_strong_script()
    data["script"]["hook"]["narration"] = (
        repeated * 4
    )
    data["script"]["introduction"]["narration"] = (
        repeated * 4
    )

    for section in data["script"]["main_sections"]:
        section["narration"] = repeated * 2

    return data


class EditorialStructureTests(unittest.TestCase):
    def test_strong_structure_passes(self):
        result = evaluate_editorial_structure(
            make_strong_script()
        )

        self.assertTrue(result["approved"])
        self.assertGreaterEqual(
            result["checks"]["hook_strength"]["score"],
            85
        )
        self.assertGreaterEqual(
            result["checks"]["narrative_spine"]["score"],
            85
        )
        self.assertGreaterEqual(
            result["checks"]["repetition_risk"]["score"],
            80
        )

    def test_repetitive_abstract_script_fails(self):
        result = evaluate_editorial_structure(
            make_repetitive_script()
        )

        self.assertFalse(result["approved"])
        self.assertLess(
            result["checks"]["repetition_risk"]["score"],
            80
        )
        self.assertLess(
            result["checks"][
                "hook_intro_distinctness"
            ]["score"],
            80
        )


class HiddenovaChannelContractTests(unittest.TestCase):
    def test_complete_contract_passes(self):
        result = evaluate_hiddenova_channel_contract(
            make_strong_script()
        )

        self.assertTrue(result["approved"])
        self.assertEqual(
            result["checks"][
                "hiddenova_brand_intro"
            ]["score"],
            100
        )
        self.assertEqual(
            result["checks"][
                "standard_cta"
            ]["score"],
            100
        )

    def test_missing_brand_intro_fails(self):
        data = make_strong_script()
        data["script"]["introduction"]["narration"] = (
            "Follow one payment from the reader to settlement."
        )

        result = evaluate_hiddenova_channel_contract(data)

        self.assertFalse(result["approved"])
        self.assertEqual(
            result["checks"][
                "hiddenova_brand_intro"
            ]["score"],
            0
        )

    def test_incomplete_cta_fails(self):
        data = make_strong_script()
        data["script"]["call_to_action"]["narration"] = (
            "Subscribe for more documentaries about payments."
        )

        result = evaluate_hiddenova_channel_contract(data)

        self.assertFalse(result["approved"])
        self.assertEqual(
            result["checks"]["standard_cta"]["score"],
            0
        )


class EditorialQAGateTests(unittest.TestCase):
    def make_qa(self) -> dict:
        critical = {
            "hook_strength": 90,
            "hook_intro_distinctness": 88,
            "narrative_spine": 91,
            "specificity": 84,
            "repetition_risk": 86,
            "title_thumbnail_synergy": 90,
            "hiddenova_brand_intro": 100,
            "standard_cta": 100,
        }
        checks = {
            name: {
                "status": "pass",
                "score": score
            }
            for name, score in critical.items()
        }

        return {
            "status": "approved",
            "overall_score": 88,
            "checks": checks,
        }

    def test_complete_qa_passes(self):
        result = evaluate_qa_editorial_gate(
            self.make_qa()
        )

        self.assertTrue(result["approved"])
        self.assertEqual(result["failures"], [])

    def test_missing_critical_check_fails(self):
        qa = self.make_qa()
        qa["checks"].pop("specificity")

        result = evaluate_qa_editorial_gate(qa)

        self.assertFalse(result["approved"])
        self.assertIn(
            "specificity",
            {
                item["check"]
                for item in result["failures"]
            }
        )

    def test_below_threshold_fails(self):
        qa = self.make_qa()
        qa["checks"]["hook_strength"] = {
            "status": "warning",
            "score": 82
        }

        result = evaluate_qa_editorial_gate(qa)

        self.assertFalse(result["approved"])


class EditorialPromptContractTests(unittest.TestCase):
    def test_script_prompt_supports_revision_brief(self):
        prompt_path = (
            Path(__file__).resolve().parents[1]
            / "agents"
            / "script"
            / "prompt.py"
        )
        text = prompt_path.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "MANDATORY EDITORIAL REVISION BRIEF",
            text
        )
        self.assertIn(
            "strongest counterintuitive fact",
            text
        )
        self.assertIn(
            'exact word "Hiddenova"',
            text
        )
        self.assertIn(
            "comment,\n  like, and subscribe",
            text
        )

    def test_seo_prompt_blocks_estimated_chapters(self):
        prompt_path = (
            Path(__file__).resolve().parents[1]
            / "agents"
            / "seo"
            / "prompt.py"
        )
        text = prompt_path.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "chapters MUST be an empty array",
            text
        )
        self.assertIn(
            "thumbnail text must be 2 to 4 words",
            text.lower()
        )


if __name__ == "__main__":
    unittest.main()
