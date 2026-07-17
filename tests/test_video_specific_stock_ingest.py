import unittest
from pathlib import Path
from unittest.mock import patch

from agents.stock_asset_ingest.run import (
    build_role_catalog,
    classify_file,
)
from agents.video_stock_pipeline.run import (
    build_stock_qa,
    resolve_manifest_source,
)


def sample_script() -> dict:
    return {
        "script": {
            "hook": {
                "narration": (
                    "A card taps a terminal and waits "
                    "for approval."
                )
            },
            "introduction": {
                "narration": (
                    "Follow one payment from checkout "
                    "to settlement."
                )
            },
            "main_sections": [
                {
                    "title": (
                        "The Tap Creates a Question"
                    ),
                    "narration": (
                        "The terminal reads the chip "
                        "and contactless card."
                    ),
                    "visual_direction": (
                        "Close up of a POS terminal, "
                        "card reader and screen."
                    ),
                },
                {
                    "title": (
                        "The Merchant Sends It "
                        "to an Acquirer"
                    ),
                    "narration": (
                        "A store and processor send "
                        "the request onward."
                    ),
                    "visual_direction": (
                        "Retail checkout, cashier and "
                        "acquiring bank."
                    ),
                },
                {
                    "title": (
                        "The Network Finds the Issuer"
                    ),
                    "narration": (
                        "The card network routes data "
                        "to the issuer."
                    ),
                    "visual_direction": (
                        "Data center server racks and "
                        "network infrastructure."
                    ),
                },
                {
                    "title": (
                        "The Issuer Makes the "
                        "Risk Decision"
                    ),
                    "narration": (
                        "Fraud and risk systems decide "
                        "approve or decline."
                    ),
                    "visual_direction": (
                        "Computer screens, monitoring "
                        "and bank analyst."
                    ),
                },
                {
                    "title": (
                        "The Approval Becomes a Hold"
                    ),
                    "narration": (
                        "A pending hold appears in the "
                        "banking app."
                    ),
                    "visual_direction": (
                        "Mobile banking app and "
                        "pending transaction."
                    ),
                },
                {
                    "title": (
                        "Clearing and Settlement "
                        "Move the Money"
                    ),
                    "narration": (
                        "Batch clearing and settlement "
                        "transfer money."
                    ),
                    "visual_direction": (
                        "Financial ledgers and "
                        "bank transfer."
                    ),
                },
            ],
        }
    }


class VideoSpecificStockClassificationTests(
    unittest.TestCase
):
    def setUp(self):
        self.catalog = build_role_catalog(
            sample_script()
        )

    def test_role_catalog_is_video_specific(self):
        role_ids = {
            item["role_id"]
            for item in self.catalog
        }

        self.assertTrue({
            "payment_terminal",
            "merchant_acquirer",
            "payment_network",
            "issuer_risk_decision",
            "authorization_hold",
            "clearing_settlement",
        }.issubset(role_ids))

        self.assertNotIn(
            "home_return_sequence",
            role_ids,
        )

    def test_current_six_clips_are_classified(self):
        expected = {
            (
                "code-and-data-on-computer-screen-"
                "SBV-354713079-4K.mp4"
            ): "issuer_risk_decision",
            (
                "customer-pay-card-machine-terminal-"
                "in-floristic-store-close-up-"
                "brown-skin-hands-buy-"
                "SBV-348714882-4K.mp4"
            ): "payment_terminal",
            (
                "multiple-rack-mounted-servers-"
                "in-data-centre-"
                "SBV-352279989-4K.mp4"
            ): "payment_network",
            (
                "online-banking-unrecognizable-woman-"
                "entering-credit-card-data-on-mobile-"
                "app-sitting-SBV-347446844-4K.mp4"
            ): "authorization_hold",
            (
                "two-cheerful-young-girls-are-buying-"
                "clothes-at-a-cash-desk-in-a-"
                "department-store-"
                "SBV-352114690-4K.mp4"
            ): "merchant_acquirer",
            (
                "use-credit-card-man-hand-using-"
                "credit-card-in-pos-terminal-finger-"
                "enter-pin-code-ba-"
                "SBV-323906936-4K.mp4"
            ): "payment_terminal",
        }

        for filename, role in expected.items():
            with self.subTest(filename=filename):
                result = classify_file(
                    filename=filename,
                    role_catalog=self.catalog,
                )

                self.assertEqual(
                    result["role"],
                    role,
                )
                self.assertNotEqual(
                    result["status"],
                    "review_required",
                )

    def test_customer_word_does_not_trigger_legacy_role(
        self
    ):
        result = classify_file(
            filename=(
                "customer-pay-card-machine-terminal-"
                "SBV-123456789-4K.mp4"
            ),
            role_catalog=self.catalog,
        )

        self.assertEqual(
            result["role"],
            "payment_terminal",
        )


class StockManifestPriorityTests(unittest.TestCase):
    def test_attached_source_manifest_beats_existing_output(self):
        context = {
            "sources": {
                "stock_manifest": (
                    "records/run_contexts/hiddenova/"
                    "video_004/inputs/"
                    "stock_source_manifest.json"
                )
            },
            "outputs": {
                "stock_manifest": (
                    "records/run_contexts/hiddenova/"
                    "video_004/outputs/stock/"
                    "hiddenova_video_004_v1/"
                    "stock_manifest.json"
                )
            },
        }

        expected = Path("new_source_manifest.json")

        with patch(
            "agents.video_stock_pipeline.run.resolve_source",
            return_value=expected,
        ) as source_mock, patch(
            "agents.video_stock_pipeline.run.resolve_output",
        ) as output_mock:
            result = resolve_manifest_source(
                context=context,
                manifest_path=None,
            )

        self.assertEqual(result, expected)
        source_mock.assert_called_once_with(
            context,
            "stock_manifest",
        )
        output_mock.assert_not_called()


class VideoSpecificStockQATests(
    unittest.TestCase
):
    @staticmethod
    def build_manifest(
        clip_count: int,
        role_count: int,
    ) -> dict:
        roles = [
            "payment_terminal",
            "merchant_acquirer",
            "payment_network",
            "issuer_risk_decision",
            "clearing_settlement",
        ][:role_count]

        items = []

        for index in range(clip_count):
            items.append({
                "candidate_id": (
                    f"VIDEO_004-C{index + 1:03d}"
                ),
                "relative_path": (
                    "assets/stock/hiddenova/"
                    "video_004_card_payment/approved/"
                    f"clip_{index + 1:03d}.mp4"
                ),
                "duration_seconds": 20.0,
                "role": roles[index % len(roles)],
                "license_status": (
                    "public_use_confirmed"
                ),
                "storyblocks_id": (
                    f"SBV-{100000000 + index}"
                ),
                "classification_confidence": "high",
            })

        return {
            "items": items,
            "total_duration_seconds": (
                clip_count * 20.0
            ),
        }

    def test_fewer_than_sixteen_clips_fails(self):
        context = {
            "channel": "hiddenova",
            "video_id": "video_004",
            "run_id": "hiddenova_video_004_v1",
            "quality_gates": {
                "minimum_stock_clip_count": 16,
                "minimum_distinct_stock_roles": 5,
            }
        }
        result = build_stock_qa(
            manifest=self.build_manifest(
                clip_count=15,
                role_count=5,
            ),
            context=context,
        )

        self.assertEqual(
            result["status"],
            "rejected",
        )
        self.assertFalse(
            result["checks"][
                "minimum_clip_count"
            ]
        )

    def test_sixteen_clips_and_five_roles_pass(self):
        context = {
            "channel": "hiddenova",
            "video_id": "video_004",
            "run_id": "hiddenova_video_004_v1",
            "quality_gates": {
                "minimum_stock_clip_count": 16,
                "minimum_distinct_stock_roles": 5,
            }
        }
        result = build_stock_qa(
            manifest=self.build_manifest(
                clip_count=16,
                role_count=5,
            ),
            context=context,
        )

        self.assertEqual(
            result["status"],
            "approved",
        )
        self.assertEqual(
            result["summary"][
                "distinct_role_count"
            ],
            5,
        )

    def test_low_confidence_clip_is_blocked(self):
        context = {
            "channel": "hiddenova",
            "video_id": "video_004",
            "run_id": "hiddenova_video_004_v1",
            "quality_gates": {
                "minimum_stock_clip_count": 16,
                "minimum_distinct_stock_roles": 5,
            }
        }
        manifest = self.build_manifest(
            clip_count=16,
            role_count=5,
        )
        manifest["items"][0][
            "classification_confidence"
        ] = "low"

        result = build_stock_qa(
            manifest=manifest,
            context=context,
        )

        self.assertEqual(
            result["status"],
            "rejected",
        )
        self.assertFalse(
            result["checks"][
                "no_manual_review_items"
            ]
        )


if __name__ == "__main__":
    unittest.main()
