import argparse
import json
import sys
from pathlib import Path

from PIL import Image, ImageOps


PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.asset_usage_registry import (
    build_asset_record,
    register_asset_batch,
    remove_asset_usage_for_path,
)
from core.content_usage_registry import (
    register_context_content,
    remove_video_content_records,
)
from core.thumbnail_standard import (
    assert_thumbnail_text,
    build_thumbnail_qa_checklist,
    load_thumbnail_standard,
)
from core.video_run_context import (
    load_context,
    resolve_output,
    save_context,
    utc_now,
)


def load_json(path: Path) -> dict:
    return json.loads(
        path.read_text(encoding="utf-8-sig")
    )


def save_json(path: Path, data: dict) -> None:
    path.write_text(
        json.dumps(
            data,
            indent=2,
            ensure_ascii=True
        ),
        encoding="utf-8"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Apply a founder-approved thumbnail "
            "without rerendering the video."
        )
    )

    parser.add_argument("--channel", required=True)
    parser.add_argument("--video-id", required=True)
    parser.add_argument("--source-path", required=True)
    parser.add_argument(
        "--thumbnail-text",
        required=True
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    channel = args.channel.lower()
    video_id = args.video_id.lower()
    source_path = Path(args.source_path).resolve()

    if not source_path.exists():
        raise FileNotFoundError(
            f"Approved thumbnail not found: {source_path}"
        )

    context = load_context(channel, video_id)
    standard = load_thumbnail_standard()

    text_result = assert_thumbnail_text(
        args.thumbnail_text,
        standard
    )

    thumbnail_path = resolve_output(
        context,
        "thumbnail"
    )

    thumbnail_record_path = resolve_output(
        context,
        "thumbnail_record"
    )

    visual_plan_path = resolve_output(
        context,
        "visual_plan"
    )

    backup_path = (
        thumbnail_path.parent
        / "thumbnail_before_hiddenova_cinematic_v1.jpg"
    )

    if (
        thumbnail_path.exists()
        and not backup_path.exists()
    ):
        backup_path.write_bytes(
            thumbnail_path.read_bytes()
        )

    with Image.open(source_path) as source:
        final_image = ImageOps.fit(
            source.convert("RGB"),
            (1280, 720),
            method=Image.Resampling.LANCZOS
        )

    final_image.save(
        thumbnail_path,
        format="JPEG",
        quality=96,
        optimize=True
    )

    removed_usage_count = (
        remove_asset_usage_for_path(
            path=thumbnail_path,
            channel=channel,
            video_id=video_id,
            asset_type="thumbnail"
        )
    )

    asset_record = build_asset_record(
        path=thumbnail_path,
        asset_type="thumbnail",
        channel=channel,
        video_id=video_id,
        run_id=context["run_id"],
        shared_brand_asset=False
    )

    registry_path = register_asset_batch(
        records=[asset_record]
    )

    thumbnail_record = load_json(
        thumbnail_record_path
    )

    thumbnail_record.update({
        "version": "2.0",
        "status": "thumbnail_ready"
    })

    thumbnail_record["thumbnail"].update({
        "standard_name": standard[
            "standard_name"
        ],
        "overlay_text": text_result[
            "normalized_text"
        ],
        "text_position": "left",
        "relative_path": str(
            thumbnail_path.relative_to(
                PROJECT_ROOT
            )
        ).replace("\\", "/"),
        "size_bytes": (
            thumbnail_path.stat().st_size
        ),
        "width": 1280,
        "height": 720,
        "sha256": asset_record["sha256"],
        "source_mode": (
            "founder_approved_generated_image"
        ),
        "founder_approved": True,
        "text_style": {
            "size": "very_large",
            "weight": "bold",
            "two_color": True,
            "colors": [
                "white",
                "yellow"
            ],
            "stroke": "black",
            "stroke_weight": "strong",
            "mobile_readable": True
        },
        "qa": build_thumbnail_qa_checklist(
            text_result["normalized_text"],
            standard
        )
    })

    thumbnail_record.setdefault(
        "source",
        {}
    ).update({
        "video_id": video_id,
        "run_id": context["run_id"],
        "asset_registry_reference": str(
            registry_path.relative_to(
                PROJECT_ROOT
            )
        ).replace("\\", "/"),
        "source_mode": (
            "founder_approved_generated_image"
        )
    })

    save_json(
        thumbnail_record_path,
        thumbnail_record
    )

    visual_plan = load_json(
        visual_plan_path
    )

    visual_plan["thumbnail"].update({
        "standard_name": standard[
            "standard_name"
        ],
        "overlay_text": text_result[
            "normalized_text"
        ],
        "text_position": "left",
        "founder_approved": True,
        "source_mode": (
            "founder_approved_generated_image"
        )
    })

    save_json(
        visual_plan_path,
        visual_plan
    )

    context.setdefault(
        "quality_gates",
        {}
    ).update({
        "require_hiddenova_thumbnail_standard": True,
        "thumbnail_style": (
            "hiddenova_cinematic_v1"
        ),
        "thumbnail_text_min_words": 2,
        "thumbnail_text_max_words": 4,
        "thumbnail_text_size": "very_large",
        "thumbnail_mobile_readability_priority": (
            "maximum"
        )
    })

    context.setdefault(
        "history",
        []
    ).append({
        "agent": "thumbnail_revision",
        "status": "founder_approved",
        "output_reference": str(
            thumbnail_path.relative_to(
                PROJECT_ROOT
            )
        ).replace("\\", "/"),
        "recorded_at": utc_now()
    })

    save_context(context)

    remove_video_content_records(
        channel=channel,
        video_id=video_id,
        record_types=["visual_plan"]
    )

    content_result = register_context_content(
        context=context
    )

    print(
        "THUMBNAIL_STANDARD:",
        standard["standard_name"]
    )
    print(
        "THUMBNAIL_TEXT:",
        text_result["normalized_text"]
    )
    print(
        "THUMBNAIL_SHA256:",
        asset_record["sha256"]
    )
    print(
        "REMOVED_OLD_THUMBNAIL_USAGES:",
        removed_usage_count
    )
    print(
        "CONTENT_FINGERPRINT_RECORDS:",
        content_result["record_count"]
    )
    print(
        "APPROVED_THUMBNAIL_APPLIED: passed"
    )


if __name__ == "__main__":
    main()
