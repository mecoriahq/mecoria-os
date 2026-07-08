import argparse
import json
import re
import subprocess
from pathlib import Path

import imageio_ffmpeg
from dotenv import load_dotenv
from jsonschema import validate

from output import save_output


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent.parent

DEFAULT_CHANNEL = "hiddenova"
DEFAULT_SOURCE_AGENT = "hybrid_video_assembly"

MIN_DURATION_SECONDS = 60
MIN_FILE_SIZE_BYTES = 10_000_000
TARGET_WIDTH = 1920
TARGET_HEIGHT = 1080
MIN_FPS = 23
MAX_FPS = 60


def load_json(file_path: Path) -> dict:
    if not file_path.exists():
        raise FileNotFoundError(f"Required file not found: {file_path}")

    return json.loads(file_path.read_text(encoding="utf-8-sig"))


def load_schema() -> dict:
    return load_json(BASE_DIR / "schema.json")


def get_source_latest_path(channel: str, source_agent: str) -> Path:
    return PROJECT_ROOT / "agents" / source_agent / "output" / channel.lower() / "latest.json"


def get_relative_path(path: Path) -> str:
    return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")


def parse_media_info(video_path: Path) -> dict:
    ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()

    result = subprocess.run(
        [
            ffmpeg_path,
            "-hide_banner",
            "-i",
            str(video_path)
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True
    )

    text = result.stderr + result.stdout

    duration_match = re.search(
        r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)",
        text
    )

    if duration_match:
        hours = int(duration_match.group(1))
        minutes = int(duration_match.group(2))
        seconds = float(duration_match.group(3))
        duration_seconds = hours * 3600 + minutes * 60 + seconds
    else:
        duration_seconds = None

    video_match = re.search(
        r"Video:.*?(\d{3,5})x(\d{3,5})",
        text
    )

    if video_match:
        width = int(video_match.group(1))
        height = int(video_match.group(2))
    else:
        width = None
        height = None

    fps_match = re.search(
        r"(\d+(?:\.\d+)?)\s*fps",
        text
    )

    fps = float(fps_match.group(1)) if fps_match else None

    return {
        "duration_seconds": round(duration_seconds, 2) if duration_seconds else None,
        "width": width,
        "height": height,
        "fps": fps,
        "has_video_stream": "Video:" in text,
        "has_audio_stream": "Audio:" in text
    }


def build_output(channel: str, source_agent: str, source_path: Path, source_data: dict) -> dict:
    issues = []
    warnings = []

    if source_data.get("status") != "draft_ready":
        issues.append(f"Source video output is not draft_ready: {source_data.get('status')}")

    video_data = source_data.get("video", {})
    relative_video_path = video_data.get("relative_path")

    if not relative_video_path:
        raise ValueError("Source output does not contain video.relative_path.")

    video_path = PROJECT_ROOT / relative_video_path

    if not video_path.exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")

    size_bytes = video_path.stat().st_size
    media_info = parse_media_info(video_path)

    if size_bytes < MIN_FILE_SIZE_BYTES:
        issues.append("Video file size is too small.")

    if not media_info["has_video_stream"]:
        issues.append("Video stream not found.")

    if not media_info["has_audio_stream"]:
        issues.append("Audio stream not found.")

    duration_seconds = media_info["duration_seconds"]

    if duration_seconds is None:
        issues.append("Could not detect video duration.")
    elif duration_seconds < MIN_DURATION_SECONDS:
        issues.append("Video duration is too short.")

    if media_info["width"] != TARGET_WIDTH or media_info["height"] != TARGET_HEIGHT:
        issues.append(
            f"Resolution mismatch. Expected {TARGET_WIDTH}x{TARGET_HEIGHT}, got {media_info['width']}x{media_info['height']}."
        )

    if media_info["fps"] is None:
        warnings.append("Could not detect FPS.")
    elif not (MIN_FPS <= media_info["fps"] <= MAX_FPS):
        issues.append(f"FPS outside acceptable range: {media_info['fps']}")

    declared_audio_duration = source_data.get("summary", {}).get("audio_duration_seconds")

    if declared_audio_duration and duration_seconds:
        duration_delta = abs(float(declared_audio_duration) - float(duration_seconds))

        if duration_delta > 2:
            warnings.append(
                f"Detected video duration differs from declared audio duration by {duration_delta:.2f}s."
            )

    if video_data.get("mode") == "hybrid_stock_ai_timeline":
        warnings.append("Hybrid video still requires founder creative review before public release.")

    warnings.append("Stock footage license/public usage should be confirmed before public release.")

    status = "approved" if not issues else "needs_revision"

    upload_ready = status == "approved"
    public_ready = False

    return {
        "agent": "video_qa",
        "version": "2.0",
        "channel": channel,
        "status": status,
        "summary": {
            "source_agent": source_agent,
            "video_path": get_relative_path(video_path),
            "duration_seconds": duration_seconds,
            "size_bytes": size_bytes,
            "resolution": f"{media_info['width']}x{media_info['height']}",
            "fps": media_info["fps"],
            "issue_count": len(issues),
            "warning_count": len(warnings),
            "founder_feedback": "hybrid video is better; repeat issue reduced after additional stock ingest",
            "technical_result": "passed" if not issues else "failed",
            "next_agent": "publisher"
        },
        "technical_checks": {
            "exists": True,
            "file_size_ok": size_bytes >= MIN_FILE_SIZE_BYTES,
            "has_video_stream": media_info["has_video_stream"],
            "has_audio_stream": media_info["has_audio_stream"],
            "duration_ok": bool(duration_seconds and duration_seconds >= MIN_DURATION_SECONDS),
            "resolution_ok": media_info["width"] == TARGET_WIDTH and media_info["height"] == TARGET_HEIGHT,
            "fps_ok": bool(media_info["fps"] and MIN_FPS <= media_info["fps"] <= MAX_FPS),
            "issues": issues,
            "warnings": warnings
        },
        "readiness": {
            "video_ready": status == "approved",
            "unlisted_upload_ready": upload_ready,
            "public_upload_ready": public_ready,
            "blocking_notes": [] if status == "approved" else issues,
            "public_release_notes": [
                "Complete final founder watch-through.",
                "Confirm Storyblocks license/public usage before public release.",
                "Use unlisted upload first for final review."
            ]
        },
        "source": {
            "source_agent": source_agent,
            "source_reference": get_relative_path(source_path),
            "video_reference": get_relative_path(video_path),
            "title": source_data.get("source", {}).get("title")
        },
        "metadata": {
            "next_agent": "publisher"
        }
    }


def print_summary(output: dict) -> None:
    print("Video QA Agent completed successfully.")
    print(f"Status: {output['status']}")
    print(f"Duration: {output['summary']['duration_seconds']}s")
    print(f"Resolution: {output['summary']['resolution']}")
    print(f"FPS: {output['summary']['fps']}")
    print(f"Issues: {output['summary']['issue_count']}")
    print(f"Warnings: {output['summary']['warning_count']}")
    print(f"Unlisted upload ready: {output['readiness']['unlisted_upload_ready']}")
    print(f"Public upload ready: {output['readiness']['public_upload_ready']}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run technical QA for assembled video drafts."
    )

    parser.add_argument(
        "--channel",
        default=DEFAULT_CHANNEL,
        help="Channel name. Default: hiddenova"
    )

    parser.add_argument(
        "--source-agent",
        default=DEFAULT_SOURCE_AGENT,
        help="Source assembly agent. Default: hybrid_video_assembly"
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    channel = args.channel.lower()
    source_agent = args.source_agent

    load_dotenv(PROJECT_ROOT / ".env")

    source_path = get_source_latest_path(
        channel=channel,
        source_agent=source_agent
    )

    source_data = load_json(source_path)

    final_output = build_output(
        channel=channel,
        source_agent=source_agent,
        source_path=source_path,
        source_data=source_data
    )

    schema = load_schema()
    validate(instance=final_output, schema=schema)

    latest_path = save_output(
        channel=final_output["channel"],
        data=final_output
    )

    print_summary(final_output)
    print(f"Output saved to: {latest_path}")


if __name__ == "__main__":
    main()
