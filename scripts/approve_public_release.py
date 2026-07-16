import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.video_run_context import (
    load_context,
    save_context,
)
from core.youtube_upload import (
    approve_public_release,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Record founder approval for public "
            "YouTube release."
        )
    )

    parser.add_argument(
        "--channel",
        default="hiddenova"
    )
    parser.add_argument(
        "--video-id",
        required=True
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    context = load_context(
        channel=args.channel.lower(),
        video_id=args.video_id.lower()
    )

    context = approve_public_release(context)
    save_context(context)

    print("VIDEO_CONTEXT_ID:", context["video_id"])
    print(
        "YOUTUBE_URL:",
        context["outputs"]["youtube_url"]
    )
    print(
        "FOUNDER_VIDEO_REVIEW_APPROVED:",
        context["release"][
            "founder_video_review_approved"
        ]
    )
    print(
        "PUBLIC_RELEASE_APPROVED:",
        context["release"][
            "public_release_approved"
        ]
    )
    print(
        "CURRENT_YOUTUBE_VISIBILITY:",
        context["release"]["youtube_visibility"]
    )
    print("STATUS:", context["status"])
    print("NEXT_AGENT:", context["next_agent"])


if __name__ == "__main__":
    main()
