import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.media_context_integrity import (
    validate_media_context,
)
from core.video_run_context import load_context


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate complete video-specific production "
            "context and asset ownership."
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

    result = validate_media_context(context)

    print(
        f"CHANNEL: {result['channel']}"
    )
    print(
        f"VIDEO_ID: {result['video_id']}"
    )
    print(
        f"RUN_ID: {result['run_id']}"
    )
    print(
        "VALIDATED_JSON_RECORDS: "
        f"{result['validated_json_record_count']}"
    )
    print(
        "VALIDATED_ASSETS: "
        f"{result['validated_asset_count']}"
    )
    print(
        "VALIDATED_CONTENT_RECORDS: "
        f"{result['validated_content_record_count']}"
    )
    print(
        "MEDIA_CONTEXT_INTEGRITY: passed"
    )


if __name__ == "__main__":
    main()
