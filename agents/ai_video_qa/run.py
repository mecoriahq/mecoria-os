import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import imageio_ffmpeg


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.ai_video_standard import (
    MAX_DURATION_SECONDS,
    MIN_DURATION_SECONDS,
    load_json,
)
from core.asset_usage_registry import (
    build_asset_record,
    register_asset_batch,
    validate_asset_batch,
)
from core.video_run_context import (
    load_context,
    register_output,
    resolve_output,
    save_context,
)


DEFAULT_CHANNEL = "hiddenova"


def relative_path(path: Path) -> str:
    return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")


def inspect_video(path: Path) -> dict:
    if not path.exists() or path.stat().st_size <= 0:
        return {
            "approved": False,
            "issues": ["Video file is missing or empty."]
        }

    ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
    result = subprocess.run(
        [ffmpeg_path, "-hide_banner", "-i", str(path)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True
    )
    text = result.stderr + result.stdout

    duration_match = re.search(
        r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)",
        text
    )
    video_match = re.search(
        r"Video:.*?(\d{3,5})x(\d{3,5}).*?"
        r"(\d+(?:\.\d+)?)\s*fps",
        text,
        flags=re.DOTALL
    )

    issues = []

    if not duration_match:
        issues.append("Could not read video duration.")
        duration = None
    else:
        duration = (
            int(duration_match.group(1)) * 3600
            + int(duration_match.group(2)) * 60
            + float(duration_match.group(3))
        )

        if (
            duration < MIN_DURATION_SECONDS
            or duration > MAX_DURATION_SECONDS
        ):
            issues.append(
                "Video duration is outside the 3-10 second gate."
            )

    if not video_match:
        issues.append("Could not read video resolution or FPS.")
        width = None
        height = None
        fps = None
    else:
        width = int(video_match.group(1))
        height = int(video_match.group(2))
        fps = float(video_match.group(3))

        if width < 1280 or height < 720:
            issues.append("Video resolution is below 1280x720.")

        ratio = width / height

        if ratio < 1.70 or ratio > 1.85:
            issues.append("Video aspect ratio is not 16:9.")

        if fps < 23:
            issues.append("Video FPS is below the production minimum.")

    has_audio = bool(re.search(r"Audio:", text))

    if has_audio:
        issues.append("Generated audio must be stripped.")

    return {
        "approved": not issues,
        "duration_seconds": duration,
        "width": width,
        "height": height,
        "fps": fps,
        "has_audio": has_audio,
        "size_bytes": path.stat().st_size,
        "issues": issues
    }


def get_generation_path(
    context: dict,
    explicit_path: str | None
) -> Path:
    if explicit_path:
        path = Path(explicit_path)

        if not path.is_absolute():
            path = PROJECT_ROOT / path

        return path

    return resolve_output(
        context=context,
        key="ai_video_generation"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run technical and ownership QA for AI video inserts."
        )
    )
    parser.add_argument("--channel", default=DEFAULT_CHANNEL)
    parser.add_argument("--video-id", required=True)
    parser.add_argument("--generation-path", default=None)
    parser.add_argument(
        "--dry-run",
        action="store_true"
    )
    parser.add_argument(
        "--attach-context",
        action="store_true",
        help="Attach approved live QA output to production context."
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
    generation_path = get_generation_path(
        context=context,
        explicit_path=args.generation_path
    )
    generation = load_json(generation_path)

    for key in ("channel", "video_id", "run_id"):
        if generation.get(key) != context.get(key):
            raise ValueError(
                f"AI video generation {key} mismatch."
            )

    mode = generation.get("generation_mode")
    checks = []
    records = []

    for item in generation.get("generated_videos", []):
        path = PROJECT_ROOT / item["relative_path"]
        inspection = inspect_video(path)

        checks.append({
            "insert_id": item["insert_id"],
            "relative_path": item["relative_path"],
            **inspection
        })

        if inspection["approved"] and mode == "live":
            record = build_asset_record(
                path=path,
                asset_type="ai_video",
                channel=context["channel"],
                video_id=context["video_id"],
                run_id=context["run_id"],
                shared_brand_asset=False
            )

            if record["sha256"] != item.get("sha256"):
                raise ValueError(
                    "AI video SHA-256 fingerprint mismatch."
                )

            records.append(record)

    approved_count = sum(
        1 for item in checks if item["approved"]
    )
    failed_count = len(checks) - approved_count

    if mode == "live":
        status = (
            "approved"
            if failed_count == 0 and approved_count >= 4
            else "rejected"
        )
    else:
        status = (
            "mock_valid_not_production"
            if failed_count == 0 and approved_count > 0
            else "rejected"
        )

    qa_output = {
        "agent": "ai_video_qa",
        "version": "1.0",
        "channel": channel,
        "video_id": video_id,
        "run_id": context["run_id"],
        "status": status,
        "generation_mode": mode,
        "summary": {
            "generated_video_count": len(checks),
            "approved_video_count": approved_count,
            "failed_video_count": failed_count,
            "minimum_live_video_count": 4,
            "production_ready": status == "approved",
            "cross_video_reused_video_count": 0
        },
        "video_checks": checks,
        "checks": {
            "technical_video_quality": failed_count == 0,
            "silent_video_required": all(
                item.get("has_audio") is False
                for item in checks
            ),
            "asset_registry_ownership": (
                status == "approved"
                and len(records) == approved_count
            ),
            "cross_video_asset_reuse": (
                status == "approved"
                and len(records) == approved_count
            )
        },
        "source": {
            "generation_reference": relative_path(generation_path)
        },
        "readiness": {
            "hybrid_assembly_ready": status == "approved",
            "blocking_notes": (
                []
                if status == "approved"
                else [
                    "Mock outputs are never production-ready."
                    if mode != "live"
                    else "AI video QA failed."
                ]
            )
        }
    }

    print(f"VIDEO_CONTEXT_ID: {video_id}")
    print(f"GENERATION_MODE: {mode}")
    print(f"APPROVED_VIDEO_COUNT: {approved_count}")
    print(f"FAILED_VIDEO_COUNT: {failed_count}")
    print(f"STATUS: {status}")

    if args.dry_run:
        print("CONTEXT_CHANGED: false")
        return

    output_dir = (
        BASE_DIR
        / "output"
        / channel
        / video_id
        / context["run_id"]
        / str(mode)
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "ai_video_qa.json"
    output_path.write_text(
        json.dumps(qa_output, indent=2, ensure_ascii=True),
        encoding="utf-8"
    )

    if status == "approved":
        validate_asset_batch(records=records)
        registry_path = register_asset_batch(records=records)
        qa_output["asset_registry_reference"] = relative_path(
            registry_path
        )
        output_path.write_text(
            json.dumps(qa_output, indent=2, ensure_ascii=True),
            encoding="utf-8"
        )

    if args.attach_context:
        if status != "approved":
            raise ValueError(
                "Only approved live AI video QA may be attached "
                "to production context."
            )

        context = register_output(
            context=context,
            agent="ai_video_qa",
            reference=relative_path(output_path),
            status="approved"
        )
        save_context(context)

    print(f"OUTPUT: {relative_path(output_path)}")


if __name__ == "__main__":
    main()
