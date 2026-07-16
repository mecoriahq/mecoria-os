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
    register_youtube_upload,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Register a YouTube upload against a "
            "video-specific Mecoria context."
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
    parser.add_argument(
        "--youtube-url",
        required=True
    )
    parser.add_argument(
        "--visibility",
        choices=[
            "unlisted",
            "private",
            "public"
        ],
        default="unlisted"
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    context = load_context(
        channel=args.channel.lower(),
        video_id=args.video_id.lower()
    )

    context = register_youtube_upload(
        context=context,
        youtube_url=args.youtube_url,
        visibility=args.visibility
    )

    save_context(context)

    print(
        "VIDEO_CONTEXT_ID:",
        context["video_id"]
    )
    print(
        "YOUTUBE_VIDEO_ID:",
        context["outputs"]["youtube_video_id"]
    )
    print(
        "YOUTUBE_URL:",
        context["outputs"]["youtube_url"]
    )
    print(
        "VISIBILITY:",
        context["release"]["youtube_visibility"]
    )
    print("STATUS:", context["status"])
    print("NEXT_AGENT:", context["next_agent"])
    print("PUBLIC_RELEASE: blocked_pending_founder")


if __name__ == "__main__":
    main()
