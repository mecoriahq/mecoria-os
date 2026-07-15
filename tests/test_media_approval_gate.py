import unittest

from core.video_run_context import (
    assert_topic_approved,
    topic_is_approved,
)


class MediaApprovalGateTests(unittest.TestCase):
    def build_context(
        self,
        required: bool = True,
        approved: bool = False
    ) -> dict:
        return {
            "channel": "hiddenova",
            "video_id": "video_003",
            "run_id": "hiddenova_video_003_v1",
            "quality_gates": {
                "require_topic_approval": required
            },
            "release": {
                "topic_approved": approved
            }
        }

    def test_unapproved_topic_is_blocked(self):
        context = self.build_context(
            required=True,
            approved=False
        )

        with self.assertRaises(ValueError):
            assert_topic_approved(context)

    def test_approved_topic_can_continue(self):
        context = self.build_context(
            required=True,
            approved=True
        )

        assert_topic_approved(context)
        self.assertTrue(
            topic_is_approved(context)
        )

    def test_legacy_context_without_gate_can_continue(self):
        context = self.build_context(
            required=False,
            approved=False
        )

        assert_topic_approved(context)

    def test_missing_release_is_not_approved(self):
        context = self.build_context()
        context.pop("release")

        self.assertFalse(
            topic_is_approved(context)
        )


if __name__ == "__main__":
    unittest.main()
