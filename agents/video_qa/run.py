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
EXPECTED_RESOLUTION = "1920x1080"
MIN_VIDEO_BYTES = 1024 * 1024
MIN_DURATION_SECONDS = 10


def load_json(file_path: Path) -> dict:
    if not file_path.exists():
        raise FileNotFoundError(f"Required file not found: {file_path}")

    return json.loads(file_path.read_text(encoding="utf-8"))


def load_schema() -> dict:
    return load_json(BASE_DIR / "schema.json")


def get_video_assembly_latest_path(channel: str) -> Path:
    return PROJECT_ROOT / "agents" / "video_assembly" / "output" / channel.lower() / "latest.json"


def get_relative_path(path: Path) -> str:
    return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")


def parse_duration_seconds(probe_text: str) -> float | None:
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", probe_text)

    if not match:
        return None

    hours = int(match.group(1))
    minutes = int(match.group(2))
    seconds = float(match.group(3))

    return round(hours * 3600 + minutes * 60 + seconds, 2)


def parse_resolution(probe_text: str) -> str | None:
    matches = re.findall(r"Video:.*?(\d{3,5})x(\d{3,5})", probe_text)

    if not matches:
        return None

    width, height = matches[0]
    return f"{width}x{height}"


def probe_video(video_path: Path) -> dict:
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

    probe_text = (result.stderr or "") + "\n" + (result.stdout or "")

    return {
        "probe_ran": bool(probe_text.strip()),
        "has_video_stream": "Video:" in probe_text,
        "has_audio_stream": "Audio:" in probe_text,
        "duration_seconds": parse_duration_seconds(probe_text),
        "resolution": parse_resolution(probe_text)
    }


def build_issue(field: str, message: str, severity: str = "high") -> dict:
    return {
        "field": field,
        "severity": severity,
        "message": message
    }


def build_video_qa_output(video_assembly_data: dict, video_assembly_path: Path) -> dict:
    video_relative_path = video_assembly_data["video"]["relative_path"]
    video_path = PROJECT_ROOT / video_relative_path

    file_exists = video_path.exists()
    file_readable = False
    size_bytes = None

    if file_exists:
        try:
            size_bytes = video_path.stat().st_size
            with video_path.open("rb") as file:
                file.read(1)
            file_readable = True
        except OSError:
            file_readable = False

    format_valid = (
        video_assembly_data["video"]["format"] == "mp4"
        and video_path.suffix.lower() == ".mp4"
    )

    size_valid = size_bytes is not None and size_bytes >= MIN_VIDEO_BYTES

    probe = probe_video(video_path) if file_exists else {
        "probe_ran": False,
        "has_video_stream": False,
        "has_audio_stream": False,
        "duration_seconds": None,
        "resolution": None
    }

    resolution_valid = probe["resolution"] == EXPECTED_RESOLUTION
    duration_valid = (
        probe["duration_seconds"] is not None
        and probe["duration_seconds"] >= MIN_DURATION_SECONDS
    )

    assembly_ready = (
        video_assembly_data.get("status") == "draft_ready"
        and video_assembly_data["readiness"].get("video_ready") is True
    )

    checks = {
        "video_assembly_status": video_assembly_data.get("status"),
        "video_assembly_ready": assembly_ready,
        "file_exists": file_exists,
        "file_readable": file_readable,
        "format_valid": format_valid,
        "size_bytes": size_bytes,
        "size_valid": size_valid,
        "probe_ran": probe["probe_ran"],
        "has_video_stream": probe["has_video_stream"],
        "has_audio_stream": probe["has_audio_stream"],
        "duration_seconds": probe["duration_seconds"],
        "duration_valid": duration_valid,
        "resolution": probe["resolution"],
        "expected_resolution": EXPECTED_RESOLUTION,
        "resolution_valid": resolution_valid
    }

    critical_results = [
        assembly_ready,
        file_exists,
        file_readable,
        format_valid,
        size_valid,
        probe["probe_ran"],
        probe["has_video_stream"],
        probe["has_audio_stream"],
        duration_valid,
        resolution_valid
    ]

    passed_checks = sum(1 for result in critical_results if result)
    total_checks = len(critical_results)
    overall_score = round((passed_checks / total_checks) * 100)

    issues = []

    if not assembly_ready:
        issues.append(build_issue("video_assembly", "Video Assembly output is not draft_ready."))

    if not file_exists:
        issues.append(build_issue("video_file", "Video file does not exist."))

    if file_exists and not file_readable:
        issues.append(build_issue("video_file", "Video file is not readable."))

    if not format_valid:
        issues.append(build_issue("format", "Video file is not valid MP4 format."))

    if not size_valid:
        issues.append(build_issue("size", "Video file is missing or too small."))

    if not probe["has_video_stream"]:
        issues.append(build_issue("video_stream", "Video stream was not detected."))

    if not probe["has_audio_stream"]:
        issues.append(build_issue("audio_stream", "Audio stream was not detected."))

    if not duration_valid:
        issues.append(build_issue("duration", "Video duration is missing or too short."))

    if not resolution_valid:
        issues.append(build_issue("resolution", "Video resolution does not match expected 1920x1080."))

    approved = not issues

    recommendations = []

    if approved:
        recommendations.append({
            "field": "publisher",
            "suggestion": "Proceed to publisher package update with the approved video file."
        })
    else:
        recommendations.append({
            "field": "video_assembly",
            "suggestion": "Fix failed technical checks and regenerate the video draft."
        })

    return {
        "agent": "video_qa",
        "version": "1.0",
        "channel": video_assembly_data["channel"],
        "status": "approved" if approved else "rejected",
        "overall_score": overall_score,
        "checks": checks,
        "issues": issues,
        "recommendations": recommendations,
        "source": {
            "source_agents": [
                "video_assembly"
            ],
            "video_assembly_reference": get_relative_path(video_assembly_path),
            "video_path": video_relative_path
        },
        "metadata": {
            "next_agent": "publisher" if approved else "video_assembly"
        }
    }


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")

    video_assembly_path = get_video_assembly_latest_path(DEFAULT_CHANNEL)
    video_assembly_data = load_json(video_assembly_path)

    final_output = build_video_qa_output(
        video_assembly_data=video_assembly_data,
        video_assembly_path=video_assembly_path
    )

    schema = load_schema()
    validate(instance=final_output, schema=schema)

    latest_path = save_output(
        channel=final_output["channel"],
        data=final_output
    )

    print("Video QA Agent completed successfully.")
    print(f"Output saved to: {latest_path}")


if __name__ == "__main__":
    main()
