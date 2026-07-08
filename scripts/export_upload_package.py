import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CHANNEL = "hiddenova"


def load_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Required file not found: {path}")

    return json.loads(path.read_text(encoding="utf-8"))


def write_text(path: Path, text: str) -> None:
    path.write_text(text.strip() + "\n", encoding="utf-8")


def get_publisher_latest_path(channel: str) -> Path:
    return PROJECT_ROOT / "agents" / "publisher" / "output" / channel.lower() / "latest.json"


def create_export_dir(channel: str) -> Path:
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    export_dir = PROJECT_ROOT / "exports" / "upload_packages" / channel.lower() / timestamp
    export_dir.mkdir(parents=True, exist_ok=True)
    return export_dir


def export_upload_package(channel: str) -> Path:
    publisher_path = get_publisher_latest_path(channel)
    publisher_data = load_json(publisher_path)

    if publisher_data.get("status") != "upload_ready":
        raise ValueError("Publisher package is not upload_ready.")

    package = publisher_data["publishing_package"]
    metadata = package["video_metadata"]
    assets = package["assets"]

    video_source = PROJECT_ROOT / assets["video_file_path"]
    thumbnail_source = PROJECT_ROOT / assets["thumbnail_image_path"]

    if not video_source.exists():
        raise FileNotFoundError(f"Video file not found: {video_source}")

    if not thumbnail_source.exists():
        raise FileNotFoundError(f"Thumbnail file not found: {thumbnail_source}")

    export_dir = create_export_dir(channel)

    video_target = export_dir / "video.mp4"
    thumbnail_target = export_dir / "thumbnail.png"

    shutil.copy2(video_source, video_target)
    shutil.copy2(thumbnail_source, thumbnail_target)

    write_text(export_dir / "title.txt", metadata["title"])
    write_text(export_dir / "description.txt", metadata["description"])
    write_text(export_dir / "tags.txt", ", ".join(metadata["tags"]))
    write_text(export_dir / "hashtags.txt", " ".join(metadata["hashtags"]))

    chapters_text = "\n".join(
        f'{chapter["time"]} {chapter["title"]}'
        for chapter in metadata.get("chapters", [])
    )
    write_text(export_dir / "chapters.txt", chapters_text)

    export_metadata = {
        "channel": publisher_data["channel"],
        "platform": publisher_data["platform"],
        "status": publisher_data["status"],
        "source_publisher_package": str(publisher_path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
        "files": {
            "video": "video.mp4",
            "thumbnail": "thumbnail.png",
            "title": "title.txt",
            "description": "description.txt",
            "tags": "tags.txt",
            "hashtags": "hashtags.txt",
            "chapters": "chapters.txt"
        },
        "readiness": package["readiness"]
    }

    (export_dir / "metadata.json").write_text(
        json.dumps(export_metadata, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    write_text(
        export_dir / "upload_checklist.md",
        """
# Upload Checklist

- Upload video.mp4 to YouTube Studio.
- Set visibility to Unlisted for first test.
- Copy title from title.txt.
- Copy description from description.txt.
- Upload thumbnail.png.
- Add tags from tags.txt.
- Confirm chapters appear correctly.
- Do not publish publicly until final review.
"""
    )

    return export_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export a YouTube-ready upload package from Publisher output."
    )

    parser.add_argument(
        "--channel",
        default=DEFAULT_CHANNEL,
        help="Channel name. Default: hiddenova"
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    export_dir = export_upload_package(args.channel)

    print("Upload package exported successfully.")
    print(f"Export directory: {export_dir}")


if __name__ == "__main__":
    main()
