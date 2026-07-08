import argparse
import json
import math
import re
import subprocess
from datetime import datetime
from pathlib import Path

import imageio_ffmpeg
from dotenv import load_dotenv
from jsonschema import validate

from output import save_output


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent.parent

DEFAULT_CHANNEL = "hiddenova"
OUTPUT_FILENAME = "video_draft.mp4"
VIDEO_WIDTH = 1920
VIDEO_HEIGHT = 1080
FPS = 30

MODE_ANIMATED_THUMBNAIL = "animated_thumbnail"
MODE_STOCK_TIMELINE = "stock_timeline"

OUTPUT_MODE_LABELS = {
    MODE_ANIMATED_THUMBNAIL: "animated_thumbnail_with_narration",
    MODE_STOCK_TIMELINE: "stock_timeline_with_narration"
}

VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".mkv"}

PREFERRED_STOCK_ORDER = [
    "A001-C001",
    "A010-C005",
    "A010-C001",
    "A010-C006",
    "A012-C001",
    "A010-C007",
    "A010-C008"
]


def load_json(file_path: Path) -> dict:
    if not file_path.exists():
        raise FileNotFoundError(f"Required file not found: {file_path}")

    return json.loads(file_path.read_text(encoding="utf-8-sig"))


def load_schema() -> dict:
    return load_json(BASE_DIR / "schema.json")


def get_audio_assembly_latest_path(channel: str) -> Path:
    return PROJECT_ROOT / "agents" / "audio_assembly" / "output" / channel.lower() / "latest.json"


def get_publisher_latest_path(channel: str) -> Path:
    return PROJECT_ROOT / "agents" / "publisher" / "output" / channel.lower() / "latest.json"


def get_stock_manifest_path(channel: str) -> Path:
    return PROJECT_ROOT / "records" / "assets" / channel.lower() / "stock_footage_manifest.json"


def get_relative_path(path: Path) -> str:
    return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")


def get_video_output_dir(channel: str) -> Path:
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    output_dir = (
        BASE_DIR
        / "output"
        / channel.lower()
        / "drafts"
        / timestamp
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def ensure_inputs_ready(audio_assembly_data: dict, publisher_data: dict) -> None:
    if audio_assembly_data.get("status") != "assembled":
        raise ValueError("Audio Assembly output is not assembled.")

    if not audio_assembly_data["readiness"].get("combined_audio_ready"):
        raise ValueError("Combined audio is not ready.")

    if publisher_data.get("status") not in {"metadata_ready", "upload_ready"}:
        raise ValueError("Publisher package is not metadata_ready or upload_ready.")

    if not publisher_data["publishing_package"]["readiness"].get("thumbnail_ready"):
        raise ValueError("Publisher thumbnail is not ready.")


def get_input_paths(audio_assembly_data: dict, publisher_data: dict) -> tuple[Path, Path]:
    audio_path = PROJECT_ROOT / audio_assembly_data["audio"]["combined_audio"]["relative_path"]
    thumbnail_path = PROJECT_ROOT / publisher_data["publishing_package"]["assets"]["thumbnail_image_path"]

    if not audio_path.exists():
        raise FileNotFoundError(f"Combined audio file not found: {audio_path}")

    if not thumbnail_path.exists():
        raise FileNotFoundError(f"Thumbnail image file not found: {thumbnail_path}")

    return audio_path, thumbnail_path


def run_ffmpeg(command: list[str], error_label: str) -> None:
    result = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"{error_label} failed:\n"
            + result.stderr[-4000:]
        )


def validate_created_video(video_path: Path) -> None:
    if not video_path.exists():
        raise FileNotFoundError(f"Video draft was not created: {video_path}")

    if video_path.stat().st_size <= 0:
        raise ValueError(f"Video draft is empty: {video_path}")


def image_video_filter() -> str:
    return (
        f"[0:v]scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={VIDEO_WIDTH}:{VIDEO_HEIGHT},"
        "zoompan=z='min(1.0+on*0.00002,1.06)':"
        "x='iw/2-(iw/zoom/2)':"
        "y='ih/2-(ih/zoom/2)':"
        f"d=1:s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:fps={FPS},"
        "setsar=1,"
        "format=yuv420p[v]"
    )


def stock_video_filter() -> str:
    return (
        f"scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={VIDEO_WIDTH}:{VIDEO_HEIGHT},"
        f"fps={FPS},"
        "setsar=1,"
        "format=yuv420p"
    )


def get_media_duration_seconds(media_path: Path) -> float:
    ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()

    result = subprocess.run(
        [
            ffmpeg_path,
            "-hide_banner",
            "-i",
            str(media_path)
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
        raise ValueError(f"Could not read media duration: {media_path}")

    hours = int(match.group(1))
    minutes = int(match.group(2))
    seconds = float(match.group(3))

    return hours * 3600 + minutes * 60 + seconds


def assemble_animated_thumbnail_video(
    thumbnail_path: Path,
    audio_path: Path,
    output_dir: Path
) -> Path:
    ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
    output_path = output_dir / OUTPUT_FILENAME

    command = [
        ffmpeg_path,
        "-y",
        "-loop",
        "1",
        "-framerate",
        str(FPS),
        "-i",
        str(thumbnail_path),
        "-i",
        str(audio_path),
        "-filter_complex",
        image_video_filter(),
        "-map",
        "[v]",
        "-map",
        "1:a",
        "-r",
        str(FPS),
        "-c:v",
        "libx264",
        "-tune",
        "stillimage",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-shortest",
        "-movflags",
        "+faststart",
        str(output_path)
    ]

    run_ffmpeg(command, "ffmpeg animated thumbnail video assembly")
    validate_created_video(output_path)
    return output_path


def preferred_stock_sort_key(item: dict) -> tuple[int, int, str]:
    candidate_id = item["candidate_id"]

    if candidate_id in PREFERRED_STOCK_ORDER:
        order_index = PREFERRED_STOCK_ORDER.index(candidate_id)
    else:
        order_index = 999

    return (
        order_index,
        item.get("usage_priority", 999),
        candidate_id
    )


def load_usable_stock_clips(stock_manifest_data: dict) -> list[dict]:
    clips = []

    for item in stock_manifest_data["items"]:
        status = item.get("status", "")

        if status.startswith("rejected"):
            continue

        relative_path = item.get("relative_path")
        if not relative_path:
            continue

        path = PROJECT_ROOT / relative_path

        if path.suffix.lower() not in VIDEO_EXTENSIONS:
            continue

        if not path.exists():
            raise FileNotFoundError(f"Stock footage file not found: {path}")

        clip = dict(item)
        clip["path"] = path
        clip["duration_seconds"] = get_media_duration_seconds(path)
        clips.append(clip)

    if not clips:
        raise ValueError("No usable stock clips found in stock footage manifest.")

    return sorted(clips, key=preferred_stock_sort_key)


def create_stock_concat_list(
    clips: list[dict],
    audio_duration: float,
    concat_list_path: Path
) -> list[dict]:
    total_cycle_duration = sum(clip["duration_seconds"] for clip in clips)

    if total_cycle_duration <= 0:
        raise ValueError("Total stock clip duration is zero.")

    repeat_count = max(1, math.ceil(audio_duration / total_cycle_duration) + 1)

    timeline_entries = []
    lines = []

    sequence = 1

    for cycle in range(repeat_count):
        for clip in clips:
            safe_path = clip["path"].resolve().as_posix().replace("'", "\\'")
            lines.append(f"file '{safe_path}'")

            timeline_entries.append({
                "sequence": sequence,
                "cycle": cycle + 1,
                "asset_id": clip["asset_id"],
                "candidate_id": clip["candidate_id"],
                "role": clip["role"],
                "relative_path": get_relative_path(clip["path"]),
                "source_duration_seconds": round(clip["duration_seconds"], 2)
            })

            sequence += 1

    concat_list_path.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8"
    )

    return timeline_entries


def assemble_stock_timeline_video(
    audio_path: Path,
    stock_manifest_path: Path,
    stock_manifest_data: dict,
    output_dir: Path
) -> tuple[Path, dict]:
    ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()

    output_path = output_dir / OUTPUT_FILENAME
    concat_list_path = output_dir / "stock_concat_list.txt"
    timeline_plan_path = output_dir / "stock_timeline_plan.json"

    audio_duration = get_media_duration_seconds(audio_path)
    clips = load_usable_stock_clips(stock_manifest_data)

    timeline_entries = create_stock_concat_list(
        clips=clips,
        audio_duration=audio_duration,
        concat_list_path=concat_list_path
    )

    timeline_plan = {
        "mode": OUTPUT_MODE_LABELS[MODE_STOCK_TIMELINE],
        "audio_duration_seconds": round(audio_duration, 2),
        "stock_clip_count": len(clips),
        "timeline_entry_count": len(timeline_entries),
        "concat_list_path": get_relative_path(concat_list_path),
        "stock_manifest_path": get_relative_path(stock_manifest_path),
        "clips": [
            {
                "asset_id": clip["asset_id"],
                "candidate_id": clip["candidate_id"],
                "role": clip["role"],
                "relative_path": get_relative_path(clip["path"]),
                "duration_seconds": round(clip["duration_seconds"], 2),
                "usage_priority": clip["usage_priority"],
                "risk_level": clip["risk_level"],
                "status": clip["status"]
            }
            for clip in clips
        ],
        "timeline_entries": timeline_entries
    }

    timeline_plan_path.write_text(
        json.dumps(timeline_plan, indent=2),
        encoding="utf-8"
    )

    command = [
        ffmpeg_path,
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_list_path),
        "-i",
        str(audio_path),
        "-vf",
        stock_video_filter(),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-r",
        str(FPS),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-t",
        f"{audio_duration:.2f}",
        "-movflags",
        "+faststart",
        str(output_path)
    ]

    run_ffmpeg(command, "ffmpeg stock timeline video assembly")
    validate_created_video(output_path)

    summary = {
        "stock_manifest_path": get_relative_path(stock_manifest_path),
        "stock_clip_count": len(clips),
        "timeline_entry_count": len(timeline_entries),
        "timeline_plan_path": get_relative_path(timeline_plan_path),
        "audio_duration_seconds": round(audio_duration, 2),
        "public_usage_allowed": bool(stock_manifest_data.get("public_usage_allowed", False)),
        "license_notes": stock_manifest_data.get("notes", "")
    }

    return output_path, summary


def build_output(
    audio_assembly_data: dict,
    publisher_data: dict,
    audio_assembly_path: Path,
    publisher_path: Path,
    thumbnail_path: Path,
    audio_path: Path,
    video_path: Path,
    mode: str,
    stock_manifest_path: Path | None = None,
    stock_summary: dict | None = None
) -> dict:
    stock_summary = stock_summary or {}

    source_agents = [
        "audio_assembly",
        "publisher"
    ]

    if mode == MODE_STOCK_TIMELINE:
        source_agents.append("stock_footage_manifest")

    return {
        "agent": "video_assembly",
        "version": "2.0",
        "channel": audio_assembly_data["channel"],
        "status": "draft_ready",
        "video": {
            "filename": video_path.name,
            "relative_path": get_relative_path(video_path),
            "format": "mp4",
            "size_bytes": video_path.stat().st_size,
            "resolution": f"{VIDEO_WIDTH}x{VIDEO_HEIGHT}",
            "fps": FPS,
            "mode": OUTPUT_MODE_LABELS[mode],
            "thumbnail_image_path": get_relative_path(thumbnail_path),
            "audio_track_path": get_relative_path(audio_path),
            "stock_manifest_path": stock_summary.get("stock_manifest_path"),
            "stock_clip_count": stock_summary.get("stock_clip_count", 0),
            "timeline_entry_count": stock_summary.get("timeline_entry_count", 0),
            "timeline_plan_path": stock_summary.get("timeline_plan_path"),
            "audio_duration_seconds": stock_summary.get("audio_duration_seconds"),
            "public_usage_allowed": stock_summary.get("public_usage_allowed", False),
            "license_notes": stock_summary.get("license_notes", "")
        },
        "readiness": {
            "thumbnail_ready": True,
            "audio_ready": True,
            "video_ready": True,
            "upload_ready": False,
            "blocking_notes": [
                "Video QA has not been completed yet.",
                "Stock footage license and visual QA must be confirmed before public usage."
            ] if mode == MODE_STOCK_TIMELINE else [
                "Video QA has not been completed yet."
            ]
        },
        "source": {
            "source_agents": source_agents,
            "audio_assembly_reference": get_relative_path(audio_assembly_path),
            "publisher_reference": get_relative_path(publisher_path),
            "stock_manifest_reference": get_relative_path(stock_manifest_path) if stock_manifest_path else None,
            "title": publisher_data["publishing_package"]["video_metadata"]["title"]
        },
        "metadata": {
            "next_agent": "video_qa"
        }
    }


def dry_run(
    mode: str,
    audio_assembly_data: dict,
    publisher_data: dict,
    stock_manifest_path: Path | None = None,
    stock_manifest_data: dict | None = None
) -> None:
    ensure_inputs_ready(
        audio_assembly_data=audio_assembly_data,
        publisher_data=publisher_data
    )

    audio_path, thumbnail_path = get_input_paths(
        audio_assembly_data=audio_assembly_data,
        publisher_data=publisher_data
    )

    ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()

    print("Video Assembly Agent dry-run completed.")
    print(f"FFmpeg: {ffmpeg_path}")
    print(f"Thumbnail: {thumbnail_path}")
    print(f"Audio: {audio_path}")
    print(f"Output filename: {OUTPUT_FILENAME}")
    print(f"Resolution: {VIDEO_WIDTH}x{VIDEO_HEIGHT}")
    print(f"Mode: {OUTPUT_MODE_LABELS[mode]}")

    if mode == MODE_STOCK_TIMELINE:
        if stock_manifest_path is None or stock_manifest_data is None:
            raise ValueError("Stock timeline mode requires a stock footage manifest.")

        clips = load_usable_stock_clips(stock_manifest_data)
        audio_duration = get_media_duration_seconds(audio_path)
        total_cycle_duration = sum(clip["duration_seconds"] for clip in clips)
        repeat_count = max(1, math.ceil(audio_duration / total_cycle_duration) + 1)

        print(f"Stock manifest: {stock_manifest_path}")
        print(f"Stock clips found: {len(clips)}")
        print(f"Audio duration seconds: {audio_duration:.2f}")
        print(f"One visual cycle seconds: {total_cycle_duration:.2f}")
        print(f"Estimated visual cycles: {repeat_count}")
        print("Stock clip order:")

        for clip in clips:
            print(
                f"- {clip['candidate_id']} | {clip['role']} | "
                f"{clip['duration_seconds']:.2f}s | {clip['path']}"
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Assemble a YouTube video draft from narration audio and visual assets."
    )

    parser.add_argument(
        "--channel",
        default=DEFAULT_CHANNEL,
        help="Channel name. Default: hiddenova"
    )

    parser.add_argument(
        "--mode",
        default=MODE_ANIMATED_THUMBNAIL,
        choices=[
            MODE_ANIMATED_THUMBNAIL,
            MODE_STOCK_TIMELINE
        ],
        help="Video assembly mode. Default: animated_thumbnail"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate inputs without creating video."
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    load_dotenv(PROJECT_ROOT / ".env")

    audio_assembly_path = get_audio_assembly_latest_path(args.channel)
    publisher_path = get_publisher_latest_path(args.channel)
    stock_manifest_path = get_stock_manifest_path(args.channel)

    audio_assembly_data = load_json(audio_assembly_path)
    publisher_data = load_json(publisher_path)

    stock_manifest_data = None

    if args.mode == MODE_STOCK_TIMELINE:
        stock_manifest_data = load_json(stock_manifest_path)

    if args.dry_run:
        dry_run(
            mode=args.mode,
            audio_assembly_data=audio_assembly_data,
            publisher_data=publisher_data,
            stock_manifest_path=stock_manifest_path if args.mode == MODE_STOCK_TIMELINE else None,
            stock_manifest_data=stock_manifest_data
        )
        return

    ensure_inputs_ready(
        audio_assembly_data=audio_assembly_data,
        publisher_data=publisher_data
    )

    audio_path, thumbnail_path = get_input_paths(
        audio_assembly_data=audio_assembly_data,
        publisher_data=publisher_data
    )

    output_dir = get_video_output_dir(audio_assembly_data["channel"])

    if args.mode == MODE_STOCK_TIMELINE:
        video_path, stock_summary = assemble_stock_timeline_video(
            audio_path=audio_path,
            stock_manifest_path=stock_manifest_path,
            stock_manifest_data=stock_manifest_data,
            output_dir=output_dir
        )
    else:
        video_path = assemble_animated_thumbnail_video(
            thumbnail_path=thumbnail_path,
            audio_path=audio_path,
            output_dir=output_dir
        )
        stock_summary = None

    final_output = build_output(
        audio_assembly_data=audio_assembly_data,
        publisher_data=publisher_data,
        audio_assembly_path=audio_assembly_path,
        publisher_path=publisher_path,
        thumbnail_path=thumbnail_path,
        audio_path=audio_path,
        video_path=video_path,
        mode=args.mode,
        stock_manifest_path=stock_manifest_path if args.mode == MODE_STOCK_TIMELINE else None,
        stock_summary=stock_summary
    )

    schema = load_schema()
    validate(instance=final_output, schema=schema)

    latest_path = save_output(
        channel=final_output["channel"],
        data=final_output
    )

    print("Video Assembly Agent completed successfully.")
    print(f"Video draft saved to: {video_path}")
    print(f"Output saved to: {latest_path}")


if __name__ == "__main__":
    main()
