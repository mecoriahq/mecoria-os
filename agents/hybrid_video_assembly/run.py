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
OUTPUT_FILENAME = "hybrid_video_draft.mp4"
VIDEO_WIDTH = 1920
VIDEO_HEIGHT = 1080
FPS = 30

STOCK_SEGMENT_SECONDS = 6
AI_INSERT_AFTER_STOCK_SEGMENTS = 2
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
    extended_audio_path = PROJECT_ROOT / "agents" / "intro_outro_audio_assembly" / "output" / channel.lower() / "latest.json"

    if extended_audio_path.exists():
        return extended_audio_path

    return PROJECT_ROOT / "agents" / "audio_assembly" / "output" / channel.lower() / "latest.json"


def get_publisher_latest_path(channel: str) -> Path:
    return PROJECT_ROOT / "agents" / "publisher" / "output" / channel.lower() / "latest.json"


def get_stock_manifest_path(channel: str) -> Path:
    return PROJECT_ROOT / "records" / "assets" / channel.lower() / "stock_footage_manifest.json"


def get_ai_generation_latest_path(channel: str) -> Path:
    return PROJECT_ROOT / "agents" / "ai_visual_generation" / "output" / channel.lower() / "latest.json"


def get_ai_qa_latest_path(channel: str) -> Path:
    return PROJECT_ROOT / "agents" / "ai_visual_qa" / "output" / channel.lower() / "latest.json"


def get_relative_path(path: Path) -> str:
    return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")


def get_output_dir(channel: str) -> Path:
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    output_dir = BASE_DIR / "output" / channel.lower() / "drafts" / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


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


def stock_video_filter() -> str:
    return (
        f"scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={VIDEO_WIDTH}:{VIDEO_HEIGHT},"
        f"fps={FPS},"
        "setsar=1,"
        "format=yuv420p"
    )


def ai_image_filter(duration_seconds: float) -> str:
    frames = max(1, int(duration_seconds * FPS))

    return (
        f"scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={VIDEO_WIDTH}:{VIDEO_HEIGHT},"
        "zoompan="
        "z='min(1.0+on*0.00045,1.045)':"
        "x='iw/2-(iw/zoom/2)':"
        "y='ih/2-(ih/zoom/2)':"
        f"d={frames}:s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:fps={FPS},"
        "setsar=1,"
        "format=yuv420p"
    )


def ensure_inputs_ready(audio_data: dict, publisher_data: dict, ai_generation_data: dict, ai_qa_data: dict) -> None:
    if audio_data.get("status") != "assembled":
        raise ValueError("Audio Assembly output is not assembled.")

    if not audio_data["readiness"].get("combined_audio_ready"):
        raise ValueError("Combined narration audio is not ready.")

    if publisher_data.get("status") not in {"metadata_ready", "upload_ready"}:
        raise ValueError("Publisher package is not metadata_ready or upload_ready.")

    if ai_generation_data.get("status") != "images_ready":
        raise ValueError("AI Visual Generation output is not images_ready.")

    if ai_qa_data.get("status") != "approved":
        raise ValueError("AI Visual QA output is not approved.")


def get_audio_path(audio_data: dict) -> Path:
    audio_path = PROJECT_ROOT / audio_data["audio"]["combined_audio"]["relative_path"]

    if not audio_path.exists():
        raise FileNotFoundError(f"Combined audio file not found: {audio_path}")

    return audio_path


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


def load_stock_clips(stock_manifest_data: dict) -> list[dict]:
    clips = []

    for item in stock_manifest_data.get("items", []):
        status = item.get("status", "")

        if status.startswith("rejected"):
            continue

        if item.get("asset_id") not in {"A001", "A010", "A012"}:
            continue

        if status != "downloaded_pending_visual_qa":
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
        raise ValueError("No usable stock clips found.")

    return sorted(clips, key=preferred_stock_sort_key)


def build_stock_segment_specs(stock_clips: list[dict]) -> list[dict]:
    specs = []

    for clip in stock_clips:
        duration = clip["duration_seconds"]
        segment_count = max(1, math.ceil(duration / STOCK_SEGMENT_SECONDS))

        for index in range(segment_count):
            start = index * STOCK_SEGMENT_SECONDS

            if start >= duration:
                continue

            remaining = duration - start
            segment_duration = min(STOCK_SEGMENT_SECONDS, remaining)

            if segment_duration < 2:
                continue

            specs.append({
                "type": "stock",
                "segment_id": f"{clip['candidate_id']}_S{index + 1:02d}",
                "asset_id": clip["asset_id"],
                "candidate_id": clip["candidate_id"],
                "role": clip["role"],
                "source_path": clip["path"],
                "source_relative_path": get_relative_path(clip["path"]),
                "start_seconds": round(start, 2),
                "duration_seconds": round(segment_duration, 2),
                "risk_level": clip.get("risk_level", "unknown")
            })

    return specs


def load_ai_specs(ai_generation_data: dict, ai_qa_data: dict) -> list[dict]:
    approved_ids = {
        item["insert_id"]
        for item in ai_qa_data.get("image_checks", [])
        if item.get("approved") is True
    }

    specs = []

    for item in ai_generation_data.get("generated_images", []):
        insert_id = item["insert_id"]

        if insert_id not in approved_ids:
            continue

        path = PROJECT_ROOT / item["relative_path"]

        if not path.exists():
            raise FileNotFoundError(f"AI visual image not found: {path}")

        specs.append({
            "type": "ai_insert",
            "segment_id": insert_id,
            "insert_id": insert_id,
            "section_hint": item["section_hint"],
            "visual_role": item["visual_role"],
            "source_path": path,
            "source_relative_path": get_relative_path(path),
            "duration_seconds": int(item.get("target_duration_seconds", 5))
        })

    if not specs:
        raise ValueError("No approved AI visual inserts found.")

    return sorted(specs, key=lambda item: item["insert_id"])


def build_hybrid_cycle(stock_specs: list[dict], ai_specs: list[dict]) -> list[dict]:
    cycle = []
    ai_index = 0

    for index, stock_spec in enumerate(stock_specs, start=1):
        cycle.append(stock_spec)

        if index % AI_INSERT_AFTER_STOCK_SEGMENTS == 0 and ai_index < len(ai_specs):
            cycle.append(ai_specs[ai_index])
            ai_index += 1

    while ai_index < len(ai_specs):
        cycle.append(ai_specs[ai_index])
        ai_index += 1

    return cycle


def build_timeline_sequence(cycle: list[dict], audio_duration: float) -> list[dict]:
    cycle_duration = sum(item["duration_seconds"] for item in cycle)

    if cycle_duration <= 0:
        raise ValueError("Hybrid cycle duration is zero.")

    entries = []
    timeline_duration = 0.0
    cycle_number = 1
    sequence = 1

    while timeline_duration < audio_duration + 3:
        for item in cycle:
            entry = dict(item)
            entry["sequence"] = sequence
            entry["cycle"] = cycle_number
            entries.append(entry)

            timeline_duration += item["duration_seconds"]
            sequence += 1

            if timeline_duration >= audio_duration + 3:
                break

        cycle_number += 1

    return entries


def render_stock_segment(spec: dict, segment_path: Path) -> None:
    ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()

    command = [
        ffmpeg_path,
        "-y",
        "-ss",
        f"{spec['start_seconds']:.2f}",
        "-i",
        str(spec["source_path"]),
        "-t",
        f"{spec['duration_seconds']:.2f}",
        "-vf",
        stock_video_filter(),
        "-an",
        "-r",
        str(FPS),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-pix_fmt",
        "yuv420p",
        str(segment_path)
    ]

    run_ffmpeg(command, "ffmpeg stock segment render")


def render_ai_segment(spec: dict, segment_path: Path) -> None:
    ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
    frames = max(1, int(spec["duration_seconds"] * FPS))

    command = [
        ffmpeg_path,
        "-y",
        "-loop",
        "1",
        "-i",
        str(spec["source_path"]),
        "-vf",
        ai_image_filter(spec["duration_seconds"]),
        "-frames:v",
        str(frames),
        "-an",
        "-r",
        str(FPS),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-pix_fmt",
        "yuv420p",
        str(segment_path)
    ]

    run_ffmpeg(command, "ffmpeg AI image segment render")


def render_unique_segments(unique_specs: list[dict], segment_library_dir: Path) -> dict[str, Path]:
    segment_library_dir.mkdir(parents=True, exist_ok=True)
    rendered = {}

    for spec in unique_specs:
        safe_id = spec["segment_id"].lower().replace(" ", "_").replace("/", "_")
        segment_path = segment_library_dir / f"{safe_id}.mp4"

        print(f"Rendering segment: {spec['segment_id']} ({spec['type']})", flush=True)

        if spec["type"] == "stock":
            render_stock_segment(spec, segment_path)
        elif spec["type"] == "ai_insert":
            render_ai_segment(spec, segment_path)
        else:
            raise ValueError(f"Unknown segment type: {spec['type']}")

        if not segment_path.exists() or segment_path.stat().st_size <= 0:
            raise ValueError(f"Segment was not created correctly: {segment_path}")

        rendered[spec["segment_id"]] = segment_path

    return rendered


def write_concat_list(timeline_entries: list[dict], rendered_segments: dict[str, Path], concat_list_path: Path) -> None:
    lines = []

    for entry in timeline_entries:
        segment_path = rendered_segments[entry["segment_id"]]
        safe_path = segment_path.resolve().as_posix().replace("'", "\\'")
        lines.append(f"file '{safe_path}'")

    concat_list_path.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8"
    )


def concat_silent_video(concat_list_path: Path, silent_video_path: Path) -> None:
    ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()

    command = [
        ffmpeg_path,
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_list_path),
        "-c",
        "copy",
        str(silent_video_path)
    ]

    run_ffmpeg(command, "ffmpeg hybrid silent video concatenation")


def attach_audio(silent_video_path: Path, audio_path: Path, output_path: Path, audio_duration: float) -> None:
    ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()

    command = [
        ffmpeg_path,
        "-y",
        "-i",
        str(silent_video_path),
        "-i",
        str(audio_path),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        "copy",
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

    run_ffmpeg(command, "ffmpeg hybrid audio attachment")

    if not output_path.exists() or output_path.stat().st_size <= 0:
        raise ValueError(f"Hybrid video draft was not created: {output_path}")


def build_timeline_plan(
    stock_clips: list[dict],
    stock_specs: list[dict],
    ai_specs: list[dict],
    cycle: list[dict],
    timeline_entries: list[dict],
    audio_duration: float,
    output_dir: Path
) -> Path:
    timeline_plan_path = output_dir / "hybrid_timeline_plan.json"

    timeline_plan = {
        "mode": "hybrid_stock_ai_timeline",
        "audio_duration_seconds": round(audio_duration, 2),
        "stock_source_clip_count": len(stock_clips),
        "stock_segment_count": len(stock_specs),
        "ai_insert_count": len(ai_specs),
        "cycle_entry_count": len(cycle),
        "cycle_duration_seconds": round(sum(item["duration_seconds"] for item in cycle), 2),
        "timeline_entry_count": len(timeline_entries),
        "timeline_duration_before_trim_seconds": round(sum(item["duration_seconds"] for item in timeline_entries), 2),
        "stock_segments": [
            {
                "segment_id": item["segment_id"],
                "candidate_id": item["candidate_id"],
                "role": item["role"],
                "source_relative_path": item["source_relative_path"],
                "start_seconds": item["start_seconds"],
                "duration_seconds": item["duration_seconds"]
            }
            for item in stock_specs
        ],
        "ai_segments": [
            {
                "segment_id": item["segment_id"],
                "section_hint": item["section_hint"],
                "visual_role": item["visual_role"],
                "source_relative_path": item["source_relative_path"],
                "duration_seconds": item["duration_seconds"]
            }
            for item in ai_specs
        ],
        "timeline_entries": [
            {
                "sequence": item["sequence"],
                "cycle": item["cycle"],
                "type": item["type"],
                "segment_id": item["segment_id"],
                "duration_seconds": item["duration_seconds"],
                "source_relative_path": item["source_relative_path"]
            }
            for item in timeline_entries
        ]
    }

    timeline_plan_path.write_text(
        json.dumps(timeline_plan, indent=2),
        encoding="utf-8"
    )

    return timeline_plan_path


def assemble_hybrid_video(
    audio_path: Path,
    stock_clips: list[dict],
    stock_specs: list[dict],
    ai_specs: list[dict],
    output_dir: Path
) -> tuple[Path, dict]:
    audio_duration = get_media_duration_seconds(audio_path)

    cycle = build_hybrid_cycle(
        stock_specs=stock_specs,
        ai_specs=ai_specs
    )

    timeline_entries = build_timeline_sequence(
        cycle=cycle,
        audio_duration=audio_duration
    )

    unique_specs_by_id = {}

    for item in cycle:
        unique_specs_by_id[item["segment_id"]] = item

    unique_specs = list(unique_specs_by_id.values())

    segment_library_dir = output_dir / "segment_library"
    concat_list_path = output_dir / "hybrid_concat_list.txt"
    silent_video_path = output_dir / "hybrid_silent_video.mp4"
    output_path = output_dir / OUTPUT_FILENAME

    timeline_plan_path = build_timeline_plan(
        stock_clips=stock_clips,
        stock_specs=stock_specs,
        ai_specs=ai_specs,
        cycle=cycle,
        timeline_entries=timeline_entries,
        audio_duration=audio_duration,
        output_dir=output_dir
    )

    rendered_segments = render_unique_segments(
        unique_specs=unique_specs,
        segment_library_dir=segment_library_dir
    )

    write_concat_list(
        timeline_entries=timeline_entries,
        rendered_segments=rendered_segments,
        concat_list_path=concat_list_path
    )

    concat_silent_video(
        concat_list_path=concat_list_path,
        silent_video_path=silent_video_path
    )

    attach_audio(
        silent_video_path=silent_video_path,
        audio_path=audio_path,
        output_path=output_path,
        audio_duration=audio_duration
    )

    summary = {
        "audio_duration_seconds": round(audio_duration, 2),
        "stock_source_clip_count": len(stock_clips),
        "stock_segment_count": len(stock_specs),
        "ai_insert_count": len(ai_specs),
        "cycle_entry_count": len(cycle),
        "cycle_duration_seconds": round(sum(item["duration_seconds"] for item in cycle), 2),
        "timeline_entry_count": len(timeline_entries),
        "timeline_plan_path": get_relative_path(timeline_plan_path),
        "concat_list_path": get_relative_path(concat_list_path),
        "silent_video_path": get_relative_path(silent_video_path)
    }

    return output_path, summary


def build_output(
    channel: str,
    mode: str,
    audio_path: Path,
    audio_assembly_path: Path,
    publisher_path: Path,
    stock_manifest_path: Path,
    ai_generation_path: Path,
    ai_qa_path: Path,
    publisher_data: dict,
    video_path: Path | None,
    summary: dict
) -> dict:
    return {
        "agent": "hybrid_video_assembly",
        "version": "1.0",
        "channel": channel,
        "status": "dry_run_ready" if mode == "dry_run" else "draft_ready",
        "summary": summary,
        "video": {
            "filename": video_path.name if video_path else None,
            "relative_path": get_relative_path(video_path) if video_path else None,
            "format": "mp4" if video_path else None,
            "size_bytes": video_path.stat().st_size if video_path else 0,
            "resolution": f"{VIDEO_WIDTH}x{VIDEO_HEIGHT}",
            "fps": FPS,
            "mode": "hybrid_stock_ai_timeline",
            "audio_track_path": get_relative_path(audio_path),
            "timeline_plan_path": summary.get("timeline_plan_path"),
            "upload_ready": False
        },
        "readiness": {
            "video_ready": mode != "dry_run",
            "audio_ready": True,
            "stock_ready": True,
            "ai_visuals_ready": True,
            "upload_ready": False,
            "blocking_notes": [
                "Video QA has not been completed yet.",
                "Stock footage license and visual QA must be confirmed before public usage."
            ]
        },
        "source": {
            "audio_assembly_reference": get_relative_path(audio_assembly_path),
            "publisher_reference": get_relative_path(publisher_path),
            "stock_manifest_reference": get_relative_path(stock_manifest_path),
            "ai_visual_generation_reference": get_relative_path(ai_generation_path),
            "ai_visual_qa_reference": get_relative_path(ai_qa_path),
            "title": publisher_data["publishing_package"]["video_metadata"]["title"]
        },
        "metadata": {
            "next_agent": "video_qa"
        }
    }


def dry_run(final_output: dict, stock_specs: list[dict], ai_specs: list[dict]) -> None:
    print("Hybrid Video Assembly Agent dry-run completed.")
    print(f"Channel: {final_output['channel']}")
    print(f"Status: {final_output['status']}")
    print(f"Audio duration: {final_output['summary']['audio_duration_seconds']}s")
    print(f"Stock source clips: {final_output['summary']['stock_source_clip_count']}")
    print(f"Stock segments: {final_output['summary']['stock_segment_count']}")
    print(f"AI inserts: {final_output['summary']['ai_insert_count']}")
    print(f"Cycle duration: {final_output['summary']['cycle_duration_seconds']}s")
    print(f"Estimated timeline entries: {final_output['summary']['timeline_entry_count']}")
    print("First stock segments:")

    for item in stock_specs[:10]:
        print(
            f"- {item['segment_id']} | {item['role']} | "
            f"{item['duration_seconds']}s"
        )

    print("AI inserts:")

    for item in ai_specs:
        print(
            f"- {item['insert_id']} | {item['section_hint']} | "
            f"{item['duration_seconds']}s"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Assemble a hybrid video from stock footage, AI visual inserts, and narration audio."
    )

    parser.add_argument(
        "--channel",
        default=DEFAULT_CHANNEL,
        help="Channel name. Default: hiddenova"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate timeline without rendering video."
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    channel = args.channel.lower()

    load_dotenv(PROJECT_ROOT / ".env")

    audio_assembly_path = get_audio_assembly_latest_path(channel)
    publisher_path = get_publisher_latest_path(channel)
    stock_manifest_path = get_stock_manifest_path(channel)
    ai_generation_path = get_ai_generation_latest_path(channel)
    ai_qa_path = get_ai_qa_latest_path(channel)

    audio_data = load_json(audio_assembly_path)
    publisher_data = load_json(publisher_path)
    stock_manifest_data = load_json(stock_manifest_path)
    ai_generation_data = load_json(ai_generation_path)
    ai_qa_data = load_json(ai_qa_path)

    ensure_inputs_ready(
        audio_data=audio_data,
        publisher_data=publisher_data,
        ai_generation_data=ai_generation_data,
        ai_qa_data=ai_qa_data
    )

    audio_path = get_audio_path(audio_data)

    stock_clips = load_stock_clips(stock_manifest_data)
    stock_specs = build_stock_segment_specs(stock_clips)
    ai_specs = load_ai_specs(
        ai_generation_data=ai_generation_data,
        ai_qa_data=ai_qa_data
    )

    audio_duration = get_media_duration_seconds(audio_path)
    cycle = build_hybrid_cycle(
        stock_specs=stock_specs,
        ai_specs=ai_specs
    )
    timeline_entries = build_timeline_sequence(
        cycle=cycle,
        audio_duration=audio_duration
    )

    dry_run_summary = {
        "audio_duration_seconds": round(audio_duration, 2),
        "stock_source_clip_count": len(stock_clips),
        "stock_segment_count": len(stock_specs),
        "ai_insert_count": len(ai_specs),
        "cycle_entry_count": len(cycle),
        "cycle_duration_seconds": round(sum(item["duration_seconds"] for item in cycle), 2),
        "timeline_entry_count": len(timeline_entries),
        "timeline_plan_path": None,
        "concat_list_path": None,
        "silent_video_path": None
    }

    if args.dry_run:
        final_output = build_output(
            channel=channel,
            mode="dry_run",
            audio_path=audio_path,
            audio_assembly_path=audio_assembly_path,
            publisher_path=publisher_path,
            stock_manifest_path=stock_manifest_path,
            ai_generation_path=ai_generation_path,
            ai_qa_path=ai_qa_path,
            publisher_data=publisher_data,
            video_path=None,
            summary=dry_run_summary
        )

        schema = load_schema()
        validate(instance=final_output, schema=schema)

        dry_run(
            final_output=final_output,
            stock_specs=stock_specs,
            ai_specs=ai_specs
        )
        return

    output_dir = get_output_dir(channel)

    video_path, render_summary = assemble_hybrid_video(
        audio_path=audio_path,
        stock_clips=stock_clips,
        stock_specs=stock_specs,
        ai_specs=ai_specs,
        output_dir=output_dir
    )

    final_output = build_output(
        channel=channel,
        mode="render",
        audio_path=audio_path,
        audio_assembly_path=audio_assembly_path,
        publisher_path=publisher_path,
        stock_manifest_path=stock_manifest_path,
        ai_generation_path=ai_generation_path,
        ai_qa_path=ai_qa_path,
        publisher_data=publisher_data,
        video_path=video_path,
        summary=render_summary
    )

    schema = load_schema()
    validate(instance=final_output, schema=schema)

    latest_path = save_output(
        channel=final_output["channel"],
        data=final_output
    )

    print("Hybrid Video Assembly Agent completed successfully.")
    print(f"Video draft saved to: {video_path}")
    print(f"Output saved to: {latest_path}")


if __name__ == "__main__":
    main()
