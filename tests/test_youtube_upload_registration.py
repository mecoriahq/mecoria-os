import unittest

from core.youtube_upload import (
    approve_public_release,
    extract_youtube_video_id,
    register_youtube_upload,
)


class YouTubeUploadRegistrationTests(
    unittest.TestCase
):
    def build_context(self) -> dict:
        return {
            "channel": "hiddenova",
            "video_id": "video_003",
            "run_id": "hiddenova_video_003_v1",
            "status": "founder_review_required",
            "outputs": {},
            "release": {
                "public_release_approved": False
            },
            "history": []
        }

    def register_unlisted(self) -> dict:
        return register_youtube_upload(
            context=self.build_context(),
            youtube_url=(
                "https://youtu.be/xZkkc1U2orI"
            ),
            visibility="unlisted"
        )

    def test_short_url_is_parsed(self):
        self.assertEqual(
            extract_youtube_video_id(
                "https://youtu.be/xZkkc1U2orI"
            ),
            "xZkkc1U2orI"
        )

    def test_watch_url_is_parsed(self):
        self.assertEqual(
            extract_youtube_video_id(
                "https://www.youtube.com/"
                "watch?v=xZkkc1U2orI"
            ),
            "xZkkc1U2orI"
        )

    def test_unlisted_upload_is_registered(self):
        context = self.register_unlisted()

        self.assertEqual(
            context["status"],
            "uploaded_for_founder_review"
        )
        self.assertFalse(
            context["release"][
                "public_release_approved"
            ]
        )

    def test_public_upload_without_approval_fails(
        self
    ):
        context = self.register_unlisted()

        with self.assertRaises(ValueError):
            register_youtube_upload(
                context=context,
                youtube_url=(
                    "https://youtu.be/xZkkc1U2orI"
                ),
                visibility="public"
            )

    def test_founder_can_approve_public_release(self):
        context = approve_public_release(
            self.register_unlisted()
        )

        self.assertTrue(
            context["release"][
                "founder_video_review_approved"
            ]
        )
        self.assertTrue(
            context["release"][
                "public_release_approved"
            ]
        )
        self.assertEqual(
            context["status"],
            "public_release_approved"
        )

    def test_public_visibility_preserves_approval(self):
        context = approve_public_release(
            self.register_unlisted()
        )

        context = register_youtube_upload(
            context=context,
            youtube_url=(
                "https://youtu.be/xZkkc1U2orI"
            ),
            visibility="public"
        )

        self.assertEqual(
            context["status"],
            "public"
        )
        self.assertEqual(
            context["next_agent"],
            "analytics_48h"
        )
        self.assertTrue(
            context["release"][
                "public_release_approved"
            ]
        )


if __name__ == "__main__":
    unittest.main()
