import argparse
import json
import shutil
from datetime import datetime
import sys
from pathlib import Path

from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CHANNEL = "hiddenova"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.video_run_context import (
    load_context,
    register_output,
    save_context,
    set_status,
)

YOUTUBE_THUMBNAIL_SIZE = (1280, 720)
YOUTUBE_THUMBNAIL_RATIO = 16 / 9


def load_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Required file not found: {path}")

    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_text(path: Path, text: str) -> None:
    path.write_text(text.strip() + "\n", encoding="utf-8")


def normalize_thumbnail(source_path: Path, target_path: Path) -> None:
    image = Image.open(source_path).convert("RGB")

    width, height = image.size
    current_ratio = width / height

    if current_ratio > YOUTUBE_THUMBNAIL_RATIO:
        new_width = int(height * YOUTUBE_THUMBNAIL_RATIO)
        left = (width - new_width) // 2
        image = image.crop((left, 0, left + new_width, height))
    else:
        new_height = int(width / YOUTUBE_THUMBNAIL_RATIO)
        top = (height - new_height) // 2
        image = image.crop((0, top, width, top + new_height))

    image = image.resize(YOUTUBE_THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
    image.save(target_path, quality=95)


def get_publisher_path(
    channel: str,
    video_id: str | None = None
) -> tuple[Path, dict | None]:
    if video_id:
        context = load_context(
            channel=channel,
            video_id=video_id
        )

        reference = context.get(
            "outputs",
            {}
        ).get("publisher")

        if not reference:
            raise ValueError(
                "Run context has no publisher output."
            )

        if reference.replace("\\", "/").lower().endswith(
            "/latest.json"
        ):
            raise ValueError(
                "Production export cannot use publisher latest.json."
            )

        return PROJECT_ROOT / reference, context

    legacy_path = (
        PROJECT_ROOT
        / "agents"
        / "publisher"
        / "output"
        / channel.lower()
        / "latest.json"
    )
    return legacy_path, None



def export_thumbnail_finalists(
    context: dict | None,
    export_dir: Path
) -> list[dict]:
    if not context:
        return []

    reference = context.get(
        "outputs",
        {}
    ).get("thumbnail_record")

    if not reference:
        return []

    record_path = PROJECT_ROOT / reference

    if not record_path.exists():
        return []

    record = load_json(record_path)
    thumbnail = record.get("thumbnail", {})
    finalists = thumbnail.get("finalists", [])

    if not isinstance(finalists, list):
        return []

    finalist_dir = (
        export_dir / "thumbnail_finalists"
    )
    exported = []

    for index, item in enumerate(
        finalists,
        start=1
    ):
        source_reference = item.get(
            "relative_path"
        )

        if not source_reference:
            continue

        source_path = (
            PROJECT_ROOT / source_reference
        )

        if not source_path.exists():
            continue

        target_name = (
            f"finalist_{index:02d}_"
            f"{item.get('concept_id', 'concept').lower()}.png"
        )
        target_path = finalist_dir / target_name
        finalist_dir.mkdir(
            parents=True,
            exist_ok=True
        )
        normalize_thumbnail(
            source_path,
            target_path
        )
        exported.append({
            "concept_id": item.get("concept_id"),
            "concept_type": item.get("concept_type"),
            "overlay_text": item.get("overlay_text"),
            "final_score": item.get("final_score"),
            "file": (
                "thumbnail_finalists/"
                + target_name
            ),
        })

    return exported


def create_export_dir(
    channel: str,
    video_id: str | None = None,
    run_id: str | None = None
) -> Path:
    timestamp = datetime.now().strftime(
        "%Y-%m-%d_%H-%M-%S"
    )

    export_dir = (
        PROJECT_ROOT
        / "exports"
        / "upload_packages"
        / channel.lower()
    )

    if video_id:
        export_dir = export_dir / video_id

    if run_id:
        export_dir = export_dir / run_id

    export_dir = export_dir / timestamp
    export_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    return export_dir



def export_upload_package(
    channel: str,
    video_id: str | None = None,
    dry_run: bool = False
) -> Path | None:
    publisher_path, context = get_publisher_path(
        channel=channel,
        video_id=video_id
    )
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

    if dry_run:
        print(f"CHANNEL: {channel}")
        print(f"VIDEO_ID: {video_id}")
        print(
            "PUBLISHER_SOURCE: "
            + str(
                publisher_path.relative_to(PROJECT_ROOT)
            ).replace("\\", "/")
        )
        print(f"VIDEO_SOURCE: {assets['video_file_path']}")
        print(
            "THUMBNAIL_SOURCE: "
            f"{assets['thumbnail_image_path']}"
        )
        print("STATUS: export_dry_run_ready")
        return None

    export_dir = create_export_dir(
        channel=channel,
        video_id=video_id,
        run_id=context["run_id"] if context else None
    )

    video_target = export_dir / "video.mp4"
    thumbnail_target = export_dir / "thumbnail.png"

    shutil.copy2(video_source, video_target)
    normalize_thumbnail(thumbnail_source, thumbnail_target)
    thumbnail_finalists = export_thumbnail_finalists(
        context=context,
        export_dir=export_dir
    )

    write_text(export_dir / "title.txt", metadata["title"])
    write_text(export_dir / "description.txt", metadata["description"])
    write_text(export_dir / "tags.txt", ", ".join(metadata["tags"]))
    write_text(export_dir / "hashtags.txt", " ".join(metadata["hashtags"]))

    chapters_text = "\n".join(
        f'{chapter["time"]} {chapter["title"]}'
        for chapter in metadata.get("chapters", [])
    )

    write_text(export_dir / "chapters.txt", chapters_text)

    description_youtube_ready = "\n\n".join(
        part for part in [
            metadata["description"].strip(),
            chapters_text.strip(),
            " ".join(metadata["hashtags"]).strip()
        ]
        if part
    )

    write_text(
        export_dir / "description_youtube_ready.txt",
        description_youtube_ready
    )

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
            "description_youtube_ready": "description_youtube_ready.txt",
            "tags": "tags.txt",
            "hashtags": "hashtags.txt",
            "chapters": "chapters.txt",
            "thumbnail_finalists": (
                "thumbnail_finalists/"
                if thumbnail_finalists
                else None
            )
        },
        "readiness": package["readiness"],
        "thumbnail_standard": {
            "size": "1280x720",
            "aspect_ratio": "16:9",
            "normalization": "center_crop_resize",
            "purpose": "YouTube-compatible thumbnail export without black bars.",
            "finalists": thumbnail_finalists,
            "founder_review_scope": (
                "finalists_only"
                if thumbnail_finalists
                else "selected_thumbnail_only"
            )
        }
    }

    metadata_path = export_dir / "metadata.json"

    metadata_path.write_text(
        json.dumps(
            export_metadata,
            indent=2,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )

    write_text(
        export_dir / "upload_checklist.md",
        """
# Upload Checklist

- Upload video.mp4 to YouTube Studio.
- Set visibility to Unlisted for first test.
- Copy title from title.txt.
- Copy description from description_youtube_ready.txt.
- Review thumbnail_finalists/ when present.
- Upload thumbnail.png.
- Add tags from tags.txt.
- Confirm chapters appear correctly.
- Do not publish publicly until final review.
"""
    )

    if context:
        context = register_output(
            context=context,
            agent="export_package",
            reference=str(
                metadata_path.relative_to(
                    PROJECT_ROOT
                )
            ).replace("\\", "/"),
            status="export_ready"
        )

        protected_statuses = {
            "founder_review_required",
            "uploaded_for_founder_review",
            "published",
            "public",
        }

        if context.get("status") not in protected_statuses:
            context = set_status(
                context=context,
                status="export_ready",
                next_agent="youtube_upload"
            )

        save_context(context)

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

    parser.add_argument(
        "--video-id",
        default=None,
        help="Video context identifier, for example video_003."
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate package sources without exporting files."
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    export_dir = export_upload_package(
        channel=args.channel.lower(),
        video_id=(
            args.video_id.lower()
            if args.video_id
            else None
        ),
        dry_run=args.dry_run
    )

    if export_dir:
        print("Upload package exported successfully.")
        print(f"Export directory: {export_dir}")


if __name__ == "__main__":
    main()
