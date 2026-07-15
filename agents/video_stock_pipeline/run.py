import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import imageio_ffmpeg


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent.parent
VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".mkv"}

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.video_run_context import (
    load_context,
    register_output,
    resolve_output,
    resolve_source,
    save_context,
    set_status,
)


from core.asset_usage_registry import (
    build_asset_record,
    register_asset_batch,
    validate_asset_batch,
)


def load_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Required file not found: {path}")

    return json.loads(path.read_text(encoding="utf-8-sig"))


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=True),
        encoding="utf-8"
    )


def relative_path(path: Path) -> str:
    return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")


def get_media_duration_seconds(path: Path) -> float:
    ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()

    result = subprocess.run(
        [
            ffmpeg_path,
            "-hide_banner",
            "-i",
            str(path)
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True
    )

    text = result.stderr + result.stdout
    match = re.search(
        r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)",
        text
    )

    if not match:
        raise ValueError(
            f"Could not detect stock duration: {path}"
        )

    hours = int(match.group(1))
    minutes = int(match.group(2))
    seconds = float(match.group(3))

    return round(
        hours * 3600 + minutes * 60 + seconds,
        2
    )


def resolve_manifest_source(
    context: dict,
    manifest_path: str | None
) -> Path:
    if manifest_path:
        path = Path(manifest_path)

        if not path.is_absolute():
            path = PROJECT_ROOT / path

        normalized = relative_path(path).lower()

        if normalized.endswith("/latest.json"):
            raise ValueError(
                "Stock manifest cannot use latest.json."
            )

        if not path.exists():
            raise FileNotFoundError(
                f"Stock manifest not found: {path}"
            )

        return path

    if "stock_manifest" in context.get("outputs", {}):
        return resolve_output(context, "stock_manifest")

    if "stock_manifest" in context.get("sources", {}):
        return resolve_source(context, "stock_manifest")

    raise KeyError(
        "Run context has no stock_manifest reference."
    )


def validate_manifest_identity(
    manifest: dict,
    context: dict
) -> None:
    manifest_channel = manifest.get("channel")

    if (
        manifest_channel
        and manifest_channel.lower() != context["channel"]
    ):
        raise ValueError("Stock manifest channel mismatch.")

    manifest_video_id = manifest.get("video_id")

    if (
        manifest_video_id
        and manifest_video_id != context["video_id"]
    ):
        raise ValueError("Stock manifest video_id mismatch.")

    manifest_run_id = manifest.get("run_id")

    if (
        manifest_run_id
        and manifest_run_id != context["run_id"]
    ):
        raise ValueError("Stock manifest run_id mismatch.")

    video_number = manifest.get("video_number")

    if video_number is not None:
        expected_number = int(
            context["video_id"].split("_")[-1]
        )

        if int(video_number) != expected_number:
            raise ValueError(
                "Stock manifest video_number mismatch."
            )

    status = str(manifest.get("status", "")).lower()

    if not status.startswith("approved"):
        raise ValueError(
            "Stock manifest is not approved."
        )


def normalize_manifest(
    manifest: dict,
    context: dict
) -> dict:
    validate_manifest_identity(manifest, context)

    normalized_items = []
    used_paths = set()

    for index, item in enumerate(
        manifest.get("items", []),
        start=1
    ):
        status = str(item.get("status", "")).lower()

        if not status.startswith("approved"):
            continue

        reference = item.get("relative_path")

        if not reference:
            continue

        normalized_reference = reference.replace("\\", "/")

        if normalized_reference in used_paths:
            raise ValueError(
                f"Duplicate stock path: {normalized_reference}"
            )

        path = PROJECT_ROOT / normalized_reference

        if not path.exists():
            raise FileNotFoundError(
                f"Stock footage file not found: {path}"
            )

        if path.suffix.lower() not in VIDEO_EXTENSIONS:
            continue

        used_paths.add(normalized_reference)

        candidate_id = str(
            item.get("candidate_id")
            or item.get("clip_id")
            or f"{context['video_id'].upper()}-C{index:03d}"
        )

        duration_seconds = get_media_duration_seconds(
            path
        )

        normalized_items.append({
            "asset_id": str(
                item.get("asset_id")
                or f"A{index:03d}"
            ),
            "candidate_id": candidate_id,
            "channel": context["channel"],
            "video_id": context["video_id"],
            "run_id": context["run_id"],
            "status": "approved",
            "role": str(
                item.get("role")
                or "topic_specific_stock_footage"
            ),
            "filename": path.name,
            "relative_path": normalized_reference,
            "size_bytes": path.stat().st_size,
            "duration_seconds": duration_seconds,
            "source": str(
                item.get("source")
                or manifest.get("source")
                or "unknown"
            ),
            "license_status": str(
                item.get("license_status")
                or manifest.get("license_status")
                or "public_use_confirmation_required"
            ),
            "visual_theme": str(
                item.get("visual_theme")
                or manifest.get("topic")
                or context["topic_title"]
            ),
            "usage_priority": int(
                item.get("usage_priority", index)
            )
        })

    if not normalized_items:
        raise ValueError(
            "Stock manifest contains no approved clips."
        )

    total_duration = round(
        sum(
            item["duration_seconds"]
            for item in normalized_items
        ),
        2
    )

    total_size = sum(
        item["size_bytes"]
        for item in normalized_items
    )

    return {
        "record_type": "video_stock_manifest",
        "version": "2.0",
        "channel": context["channel"],
        "video_id": context["video_id"],
        "run_id": context["run_id"],
        "status": "approved_stock_ready",
        "topic": context["topic_title"],
        "item_count": len(normalized_items),
        "total_size_bytes": total_size,
        "total_duration_seconds": total_duration,
        "items": normalized_items
    }



def build_stock_registry_records(
    manifest: dict,
    context: dict
) -> list[dict]:
    records = []

    for item in manifest["items"]:
        path = PROJECT_ROOT / item["relative_path"]

        record = build_asset_record(
            path=path,
            asset_type="stock",
            channel=context["channel"],
            video_id=context["video_id"],
            run_id=context["run_id"],
            shared_brand_asset=False
        )

        item["sha256"] = record["sha256"]
        records.append(record)

    return records


def build_stock_qa(
    manifest: dict,
    context: dict
) -> dict:
    gates = context.get("quality_gates", {})

    minimum_clips = int(
        gates.get("minimum_stock_clip_count", 10)
    )
    minimum_duration = float(
        gates.get("minimum_stock_duration_seconds", 180)
    )
    maximum_share = float(
        gates.get("maximum_single_stock_clip_share", 0.25)
    )

    items = manifest["items"]
    total_duration = manifest["total_duration_seconds"]

    largest_duration = max(
        item["duration_seconds"]
        for item in items
    )

    largest_share = (
        largest_duration / total_duration
        if total_duration > 0
        else 1.0
    )

    unique_paths = {
        item["relative_path"]
        for item in items
    }

    checks = {
        "minimum_clip_count": (
            len(items) >= minimum_clips
        ),
        "minimum_total_duration": (
            total_duration >= minimum_duration
        ),
        "unique_paths": (
            len(unique_paths) == len(items)
        ),
        "maximum_single_clip_share": (
            largest_share <= maximum_share
        )
    }

    issues = []

    for name, passed in checks.items():
        if not passed:
            issues.append({
                "field": name,
                "severity": "high",
                "message": f"Stock QA gate failed: {name}"
            })

    license_warnings = [
        item["candidate_id"]
        for item in items
        if item["license_status"]
        != "public_use_confirmed"
    ]

    status = (
        "approved"
        if all(checks.values())
        else "rejected"
    )

    return {
        "agent": "video_stock_pipeline",
        "version": "1.0",
        "channel": context["channel"],
        "video_id": context["video_id"],
        "run_id": context["run_id"],
        "status": status,
        "summary": {
            "approved_clip_count": len(items),
            "unique_clip_count": len(unique_paths),
            "total_duration_seconds": total_duration,
            "largest_clip_share": round(
                largest_share,
                4
            ),
            "license_confirmation_required_count": len(
                license_warnings
            )
        },
        "checks": checks,
        "issues": issues,
        "warnings": [
            {
                "field": "stock_license",
                "severity": "medium",
                "message": (
                    "Public usage license confirmation is "
                    "required for some stock clips."
                ),
                "candidate_ids": license_warnings
            }
        ] if license_warnings else [],
        "metadata": {
            "next_agent": (
                "hybrid_video_assembly"
                if status == "approved"
                else None
            )
        }
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Normalize and validate a video-specific "
            "stock footage package."
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
        "--manifest-path",
        default=None
    )
    parser.add_argument(
        "--dry-run",
        action="store_true"
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    channel = args.channel.lower()
    video_id = args.video_id.lower()

    context = load_context(
        channel=channel,
        video_id=video_id
    )

    source_path = resolve_manifest_source(
        context=context,
        manifest_path=args.manifest_path
    )

    source_manifest = load_json(source_path)

    normalized_manifest = normalize_manifest(
        manifest=source_manifest,
        context=context
    )

    asset_records = build_stock_registry_records(
        manifest=normalized_manifest,
        context=context
    )

    validate_asset_batch(
        records=asset_records
    )

    qa_output = build_stock_qa(
        manifest=normalized_manifest,
        context=context
    )

    qa_output["checks"][
        "cross_video_asset_reuse"
    ] = True

    qa_output["summary"].update({
        "reused_clip_count": 0,
        "registry_record_count": len(asset_records)
    })

    print(f"VIDEO_CONTEXT_ID: {video_id}")
    print(f"RUN_ID: {context['run_id']}")
    print(
        "SOURCE_MANIFEST: "
        f"{relative_path(source_path)}"
    )
    print(
        "APPROVED_CLIP_COUNT: "
        f"{qa_output['summary']['approved_clip_count']}"
    )
    print(
        "TOTAL_STOCK_DURATION: "
        f"{qa_output['summary']['total_duration_seconds']}s"
    )
    print(
        "LARGEST_CLIP_SHARE: "
        f"{qa_output['summary']['largest_clip_share']}"
    )
    print(f"STOCK_QA_STATUS: {qa_output['status']}")
    print(
        "CROSS_VIDEO_REUSED_CLIP_COUNT: "
        f"{qa_output['summary']['reused_clip_count']}"
    )

    if args.dry_run:
        print("STATUS: stock_pipeline_dry_run_ready")
        return

    if qa_output["status"] != "approved":
        raise ValueError(
            "Stock QA rejected the stock package."
        )

    registry_path = register_asset_batch(
        records=asset_records
    )

    normalized_manifest["asset_registry_reference"] = (
        relative_path(registry_path)
    )

    qa_output["source"] = {
        "asset_registry_reference": relative_path(
            registry_path
        )
    }

    output_dir = (
        PROJECT_ROOT
        / "records"
        / "run_contexts"
        / channel
        / video_id
        / "outputs"
        / "stock"
        / context["run_id"]
    )

    manifest_path = output_dir / "stock_manifest.json"
    qa_path = output_dir / "stock_qa.json"

    save_json(manifest_path, normalized_manifest)
    save_json(qa_path, qa_output)

    context.setdefault("quality_gates", {}).update({
        "minimum_stock_clip_count": 10,
        "minimum_stock_duration_seconds": 180,
        "maximum_single_stock_clip_share": 0.25,
        "maximum_stock_segments_per_clip": 5,
        "minimum_timeline_cycle_coverage": 0.70,
        "maximum_timeline_cycles": 2,
        "require_stock_qa_approval": True,
        "allow_cross_video_asset_reuse": False,
        "require_asset_registry_ownership": True
    })

    context = register_output(
        context=context,
        agent="stock_manifest",
        reference=relative_path(manifest_path),
        status="approved_stock_ready"
    )

    context = register_output(
        context=context,
        agent="stock_qa",
        reference=relative_path(qa_path),
        status="approved"
    )

    if context.get("status") not in {
        "uploaded_for_founder_review",
        "published",
        "public"
    }:
        context = set_status(
            context=context,
            status="stock_ready",
            next_agent="hybrid_video_assembly"
        )

    save_context(context)

    print("Video Stock Pipeline completed successfully.")
    print(
        "STOCK_MANIFEST: "
        f"{relative_path(manifest_path)}"
    )
    print(
        "STOCK_QA: "
        f"{relative_path(qa_path)}"
    )


if __name__ == "__main__":
    main()
