import argparse
import json
import math
import re
import subprocess
import sys
from pathlib import Path

import imageio_ffmpeg
from dotenv import load_dotenv
from openai import OpenAI


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.video_run_context import (
    load_context,
    register_output,
    resolve_context_input,
    save_context,
    set_status,
)


from core.asset_usage_registry import (
    build_asset_record,
    register_asset_batch,
    validate_asset_batch,
)

from core.content_quality import (
    DEFAULT_MEDIA_DURATION_MAX_SECONDS,
    DEFAULT_MEDIA_DURATION_MIN_SECONDS,
    evaluate_duration_seconds,
)


DEFAULT_MODEL = "gpt-4o-mini-tts"
DEFAULT_VOICE = "cedar"
MIN_AUDIO_BYTES = 1024

VOICE_INSTRUCTIONS = (
    "Speak as a clear, engaging premium YouTube documentary narrator. "
    "Use a smooth, natural pace with investigative energy. "
    "Avoid sounding robotic, theatrical, promotional, or like a news anchor."
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


def count_words(text: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", text))


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
        raise ValueError(
            f"Could not read media duration: {media_path}"
        )

    hours = int(match.group(1))
    minutes = int(match.group(2))
    seconds = float(match.group(3))

    return hours * 3600 + minutes * 60 + seconds


def add_actual_section_timing(
    sections: list[dict]
) -> list[dict]:
    cursor = 0.0
    timed_sections = []

    for section in sorted(
        sections,
        key=lambda item: item["sequence"]
    ):
        path = PROJECT_ROOT / section["relative_path"]
        duration = get_media_duration_seconds(path)

        if duration <= 0:
            raise ValueError(
                f"Audio section has invalid duration: {path}"
            )

        timed = dict(section)
        timed["start_seconds"] = round(cursor, 2)
        timed["duration_seconds"] = round(duration, 2)
        cursor += duration
        timed["end_seconds"] = round(cursor, 2)
        timed_sections.append(timed)

    return timed_sections


def format_chapter_time(seconds: float) -> str:
    total = max(0, int(math.floor(seconds)))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)

    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"

    return f"{minutes}:{secs:02d}"


def build_actual_chapters(
    sections: list[dict],
    total_duration_seconds: float
) -> list[dict]:
    candidates = []

    # The public 0:00 chapter covers the hook and introduction.
    candidates.append({
        "start_seconds": 0.0,
        "title": "Introduction"
    })

    for section in sections:
        if section["section_type"] not in {
            "main_section",
            "conclusion"
        }:
            continue

        candidates.append({
            "start_seconds": float(section["start_seconds"]),
            "title": str(section["title"]).strip()
        })

    chapters = []
    last_start = None

    for candidate in candidates:
        start = float(candidate["start_seconds"])

        if last_start is not None and start - last_start < 10:
            continue

        if total_duration_seconds - start < 10:
            continue

        title = candidate["title"] or "Section"
        chapters.append({
            "time": format_chapter_time(start),
            "title": title,
            "start_seconds": round(start, 2)
        })
        last_start = start

    if len(chapters) < 3:
        raise ValueError(
            "Actual chapter generation produced fewer than "
            "three valid chapters."
        )

    return chapters


def get_duration_bounds(context: dict) -> tuple[int, int]:
    gates = context.get("quality_gates", {})
    minimum = int(
        gates.get(
            "target_audio_duration_min_seconds",
            DEFAULT_MEDIA_DURATION_MIN_SECONDS
        )
    )
    maximum = int(
        gates.get(
            "target_audio_duration_max_seconds",
            DEFAULT_MEDIA_DURATION_MAX_SECONDS
        )
    )
    return minimum, maximum


def calculate_adjusted_word_targets(
    word_count: int,
    actual_seconds: float,
    minimum_seconds: int,
    maximum_seconds: int
) -> tuple[int, int]:
    target_seconds = (minimum_seconds + maximum_seconds) / 2
    estimated_center = max(
        1,
        round(word_count * target_seconds / actual_seconds)
    )

    target_min = max(1100, round(estimated_center * 0.90))
    target_max = min(2100, round(estimated_center * 1.10))

    if target_max - target_min < 150:
        target_max = min(2100, target_min + 150)

    if target_max <= target_min:
        target_min = max(900, target_max - 150)

    return target_min, target_max


def set_duration_revision_required(
    context: dict,
    duration_gate: dict,
    word_count: int
) -> dict:
    gates = context.setdefault("quality_gates", {})
    revision_count = int(
        gates.get("audio_duration_revision_count", 0)
    ) + 1

    target_min, target_max = calculate_adjusted_word_targets(
        word_count=word_count,
        actual_seconds=duration_gate["actual_seconds"],
        minimum_seconds=duration_gate["minimum_seconds"],
        maximum_seconds=duration_gate["maximum_seconds"]
    )

    gates.update({
        "audio_duration_revision_count": revision_count,
        "last_actual_audio_duration_seconds": (
            duration_gate["actual_seconds"]
        ),
        "last_audio_duration_gate_reason": duration_gate["reason"],
        "target_script_word_count_min": target_min,
        "target_script_word_count_max": target_max,
    })

    context.setdefault("history", []).append({
        "agent": "audio_duration_gate",
        "status": "revision_required",
        "output_reference": (
            f"actual={duration_gate['actual_seconds']}s;"
            f"reason={duration_gate['reason']};"
            f"next_word_range={target_min}-{target_max}"
        )
    })

    context = set_status(
        context=context,
        status="audio_duration_revision_required",
        next_agent="script"
    )
    save_context(context)
    return context


def create_section(
    sequence: int,
    section_type: str,
    title: str,
    narration: str,
    visual_direction: str | None = None
) -> dict:
    narration = narration.strip()

    if not narration:
        raise ValueError(f"Empty narration section: {title}")

    return {
        "sequence": sequence,
        "section_type": section_type,
        "title": title,
        "narration": narration,
        "word_count": count_words(narration),
        "visual_direction": visual_direction
    }


def build_sections(script_data: dict) -> list[dict]:
    script = script_data["script"]
    sections = []
    sequence = 1

    sections.append(
        create_section(
            sequence=sequence,
            section_type="hook",
            title="Hook",
            narration=script["hook"]["narration"]
        )
    )
    sequence += 1

    sections.append(
        create_section(
            sequence=sequence,
            section_type="introduction",
            title="Introduction",
            narration=script["introduction"]["narration"]
        )
    )
    sequence += 1

    for item in script.get("main_sections", []):
        sections.append(
            create_section(
                sequence=sequence,
                section_type="main_section",
                title=item["title"],
                narration=item["narration"],
                visual_direction=item.get("visual_direction")
            )
        )
        sequence += 1

    sections.append(
        create_section(
            sequence=sequence,
            section_type="conclusion",
            title="Conclusion",
            narration=script["conclusion"]["narration"]
        )
    )
    sequence += 1

    sections.append(
        create_section(
            sequence=sequence,
            section_type="call_to_action",
            title="Call to Action",
            narration=script["call_to_action"]["narration"]
        )
    )

    return sections


def build_voice_output(
    context: dict,
    script_data: dict,
    script_path: Path,
    sections: list[dict]
) -> dict:
    full_text = "\n\n".join(
        item["narration"] for item in sections
    )
    word_count = sum(item["word_count"] for item in sections)

    return {
        "agent": "voice",
        "version": "2.0",
        "channel": context["channel"],
        "video_id": context["video_id"],
        "run_id": context["run_id"],
        "status": "narration_ready",
        "voice_package": {
            "voice_profile": {
                "language": "English",
                "provider": "openai",
                "model": DEFAULT_MODEL,
                "voice_id": DEFAULT_VOICE
            },
            "narration": {
                "title": script_data["script"]["title"],
                "word_count": word_count,
                "section_count": len(sections),
                "estimated_voice_duration_minutes": round(
                    word_count / 145,
                    2
                ),
                "sections": sections,
                "full_text": full_text
            },
            "readiness": {
                "script_loaded": True,
                "narration_ready": True,
                "audio_ready": False,
                "blocking_notes": []
            }
        },
        "source": {
            "parent_agent": "script",
            "parent_reference": relative_path(script_path)
        },
        "metadata": {
            "next_agent": "voice_generation"
        }
    }


def get_output_dir(context: dict) -> Path:
    return (
        BASE_DIR
        / "output"
        / context["channel"]
        / context["video_id"]
        / context["run_id"]
    )


def generate_audio_sections(
    voice_data: dict,
    output_dir: Path,
    model: str,
    voice: str
) -> list[dict]:
    client = OpenAI()
    audio_dir = output_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    generated = []

    for section in voice_data["voice_package"]["narration"]["sections"]:
        filename = f"section_{section['sequence']:02d}.mp3"
        audio_path = audio_dir / filename

        print(
            f"Generating section {section['sequence']}: "
            f"{section['title']}",
            flush=True
        )

        with client.audio.speech.with_streaming_response.create(
            model=model,
            voice=voice,
            input=section["narration"],
            instructions=VOICE_INSTRUCTIONS,
            response_format="mp3"
        ) as response:
            response.stream_to_file(audio_path)

        generated.append({
            "sequence": section["sequence"],
            "section_type": section["section_type"],
            "title": section["title"],
            "word_count": section["word_count"],
            "filename": filename,
            "relative_path": relative_path(audio_path),
            "format": "mp3"
        })

    return generated


def build_generation_output(
    context: dict,
    voice_path: Path,
    sections: list[dict],
    model: str,
    voice: str
) -> dict:
    total_duration = sum(
        float(item.get("duration_seconds", 0))
        for item in sections
    )

    return {
        "agent": "voice_generation",
        "version": "2.0",
        "channel": context["channel"],
        "video_id": context["video_id"],
        "run_id": context["run_id"],
        "status": "audio_ready",
        "provider": "openai",
        "model": model,
        "voice": voice,
        "audio": {
            "format": "mp3",
            "sections": sections,
            "actual_section_duration_seconds": round(
                total_duration,
                2
            ),
            "combined_audio_file_path": None
        },
        "readiness": {
            "sections_generated": len(sections),
            "audio_ready": len(sections) > 0,
            "combined_audio_ready": False,
            "blocking_notes": []
        },
        "source": {
            "parent_agent": "voice",
            "parent_reference": relative_path(voice_path)
        },
        "metadata": {
            "next_agent": "audio_qa"
        }
    }


def inspect_audio_sections(sections: list[dict]) -> list[dict]:
    checks = []

    for section in sections:
        path = PROJECT_ROOT / section["relative_path"]
        exists = path.exists()
        size_bytes = path.stat().st_size if exists else None
        readable = False

        if exists:
            try:
                with path.open("rb") as file:
                    readable = bool(file.read(1))
            except OSError:
                readable = False

        valid = (
            exists
            and readable
            and path.suffix.lower() == ".mp3"
            and size_bytes is not None
            and size_bytes >= MIN_AUDIO_BYTES
            and float(section.get("duration_seconds", 0)) > 0
        )

        checks.append({
            "sequence": section["sequence"],
            "title": section["title"],
            "relative_path": section["relative_path"],
            "file_exists": exists,
            "file_readable": readable,
            "size_bytes": size_bytes,
            "start_seconds": section.get("start_seconds"),
            "duration_seconds": section.get("duration_seconds"),
            "end_seconds": section.get("end_seconds"),
            "approved": valid
        })

    return checks


def build_qa_output(
    context: dict,
    generation_path: Path,
    generation_data: dict
) -> dict:
    checks = inspect_audio_sections(
        generation_data["audio"]["sections"]
    )
    approved_count = sum(
        1 for item in checks if item["approved"]
    )
    approved = bool(checks) and approved_count == len(checks)
    total_duration = sum(
        float(item.get("duration_seconds") or 0)
        for item in checks
    )

    return {
        "agent": "audio_qa",
        "version": "2.0",
        "channel": context["channel"],
        "video_id": context["video_id"],
        "run_id": context["run_id"],
        "status": "approved" if approved else "rejected",
        "overall_score": round(
            approved_count / len(checks) * 100
        ) if checks else 0,
        "summary": {
            "expected_sections": len(checks),
            "valid_sections": approved_count,
            "failed_sections": len(checks) - approved_count,
            "actual_section_duration_seconds": round(
                total_duration,
                2
            )
        },
        "section_checks": checks,
        "source": {
            "parent_agent": "voice_generation",
            "parent_reference": relative_path(generation_path)
        },
        "metadata": {
            "next_agent": (
                "audio_assembly"
                if approved
                else "voice_generation"
            )
        }
    }


def assemble_audio(
    sections: list[dict],
    output_dir: Path
) -> Path:
    ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
    assembly_dir = output_dir / "assembled"
    assembly_dir.mkdir(parents=True, exist_ok=True)

    concat_path = assembly_dir / "concat_list.txt"
    output_path = assembly_dir / "narration_track.mp3"

    lines = []

    for section in sorted(
        sections,
        key=lambda item: item["sequence"]
    ):
        source_path = (
            PROJECT_ROOT / section["relative_path"]
        ).resolve()
        safe_path = source_path.as_posix().replace("'", "\\'")
        lines.append(f"file '{safe_path}'")

    concat_path.write_text(
        "\n".join(lines) + "\n",
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
        str(concat_path),
        "-c",
        "copy",
        str(output_path)
    ]

    result = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        raise RuntimeError(
            "FFmpeg audio assembly failed:\n"
            + result.stderr[-3000:]
        )

    if not output_path.exists() or output_path.stat().st_size <= 0:
        raise ValueError("Assembled audio was not created.")

    return output_path


def build_assembly_output(
    context: dict,
    generation_path: Path,
    qa_path: Path,
    generation_data: dict,
    qa_data: dict,
    audio_path: Path,
    actual_duration_seconds: float,
    duration_gate: dict,
    chapters: list[dict]
) -> dict:
    sections = generation_data["audio"]["sections"]

    return {
        "agent": "audio_assembly",
        "version": "2.0",
        "channel": context["channel"],
        "video_id": context["video_id"],
        "run_id": context["run_id"],
        "status": (
            "assembled"
            if duration_gate["approved"]
            else "duration_revision_required"
        ),
        "audio": {
            "format": "mp3",
            "section_count": len(sections),
            "source_sections": sections,
            "actual_duration_seconds": round(
                actual_duration_seconds,
                2
            ),
            "chapters": chapters,
            "combined_audio": {
                "filename": audio_path.name,
                "relative_path": relative_path(audio_path),
                "format": "mp3",
                "size_bytes": audio_path.stat().st_size
            }
        },
        "readiness": {
            "audio_qa_approved": qa_data["status"] == "approved",
            "sections_loaded": len(sections),
            "combined_audio_ready": True,
            "duration_gate_approved": duration_gate["approved"],
            "blocking_notes": (
                []
                if duration_gate["approved"]
                else [
                    "Narration duration must be between "
                    "480 and 720 seconds."
                ]
            )
        },
        "duration_gate": duration_gate,
        "source": {
            "parent_agents": [
                "voice_generation",
                "audio_qa"
            ],
            "voice_generation_reference": relative_path(
                generation_path
            ),
            "audio_qa_reference": relative_path(qa_path)
        },
        "metadata": {
            "next_agent": (
                "hybrid_video_assembly"
                if duration_gate["approved"]
                else "script"
            )
        }
    }



def register_audio_asset_ownership(
    context: dict,
    generation_data: dict,
    qa_data: dict,
    assembly_data: dict
) -> Path:
    records = []
    section_hashes = {}

    sections = generation_data["audio"]["sections"]

    for section in sections:
        path = PROJECT_ROOT / section["relative_path"]

        record = build_asset_record(
            path=path,
            asset_type="narration_section",
            channel=context["channel"],
            video_id=context["video_id"],
            run_id=context["run_id"],
            shared_brand_asset=False
        )

        section["sha256"] = record["sha256"]
        section_hashes[section["sequence"]] = record[
            "sha256"
        ]
        records.append(record)

    for check in qa_data.get("section_checks", []):
        sequence = check["sequence"]

        if sequence not in section_hashes:
            raise ValueError(
                f"Audio QA section has no asset: {sequence}"
            )

        check["sha256"] = section_hashes[sequence]

    combined = assembly_data["audio"]["combined_audio"]
    combined_path = PROJECT_ROOT / combined["relative_path"]

    combined_record = build_asset_record(
        path=combined_path,
        asset_type="narration_audio",
        channel=context["channel"],
        video_id=context["video_id"],
        run_id=context["run_id"],
        shared_brand_asset=False
    )

    combined["sha256"] = combined_record["sha256"]
    records.append(combined_record)

    validate_asset_batch(records=records)

    registry_path = register_asset_batch(
        records=records
    )

    registry_reference = relative_path(registry_path)

    generation_data.setdefault(
        "source",
        {}
    ).update({
        "video_id": context["video_id"],
        "run_id": context["run_id"],
        "asset_registry_reference": registry_reference
    })

    qa_data.setdefault(
        "checks",
        {}
    ).update({
        "cross_video_asset_reuse": True,
        "asset_registry_ownership": True
    })

    qa_data.setdefault(
        "summary",
        {}
    ).update({
        "registered_audio_asset_count": len(records),
        "reused_audio_asset_count": 0
    })

    qa_data.setdefault(
        "source",
        {}
    ).update({
        "video_id": context["video_id"],
        "run_id": context["run_id"],
        "asset_registry_reference": registry_reference
    })

    assembly_data.setdefault(
        "source",
        {}
    ).update({
        "video_id": context["video_id"],
        "run_id": context["run_id"],
        "asset_registry_reference": registry_reference
    })

    assembly_data.setdefault(
        "readiness",
        {}
    ).update({
        "asset_registry_ownership": True,
        "cross_video_asset_reuse": False
    })

    return registry_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate video-specific narration audio without "
            "production latest.json dependencies."
        )
    )
    parser.add_argument("--channel", default="hiddenova")
    parser.add_argument("--video-id", required=True)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--voice", default=DEFAULT_VOICE)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    channel = args.channel.lower()
    video_id = args.video_id.lower()

    load_dotenv(PROJECT_ROOT / ".env")

    context = load_context(
        channel=channel,
        video_id=video_id
    )
    script_path = resolve_context_input(
        context=context,
        key="script"
    )
    script_data = load_json(script_path)
    sections = build_sections(script_data)
    output_dir = get_output_dir(context)

    print(f"VIDEO_CONTEXT_ID: {video_id}")
    print(f"RUN_ID: {context['run_id']}")
    print(f"SCRIPT_SOURCE: {relative_path(script_path)}")
    print(f"SECTION_COUNT: {len(sections)}")
    print(
        "WORD_COUNT: "
        f"{sum(item['word_count'] for item in sections)}"
    )
    print(f"VOICE_MODEL: {args.model}")
    print(f"VOICE_ID: {args.voice}")
    print(f"OUTPUT_DIR: {relative_path(output_dir)}")

    if args.dry_run:
        print("STATUS: audio_pipeline_dry_run_ready")
        return

    output_dir.mkdir(parents=True, exist_ok=True)

    voice_data = build_voice_output(
        context=context,
        script_data=script_data,
        script_path=script_path,
        sections=sections
    )
    voice_path = output_dir / "voice.json"
    save_json(voice_path, voice_data)

    generated_sections = generate_audio_sections(
        voice_data=voice_data,
        output_dir=output_dir,
        model=args.model,
        voice=args.voice
    )
    generated_sections = add_actual_section_timing(
        generated_sections
    )

    generation_data = build_generation_output(
        context=context,
        voice_path=voice_path,
        sections=generated_sections,
        model=args.model,
        voice=args.voice
    )
    generation_path = output_dir / "voice_generation.json"
    save_json(generation_path, generation_data)

    qa_data = build_qa_output(
        context=context,
        generation_path=generation_path,
        generation_data=generation_data
    )
    qa_path = output_dir / "audio_qa.json"
    save_json(qa_path, qa_data)

    if qa_data["status"] != "approved":
        raise ValueError("Audio QA rejected generated sections.")

    assembled_audio_path = assemble_audio(
        sections=generated_sections,
        output_dir=output_dir
    )

    actual_duration_seconds = get_media_duration_seconds(
        assembled_audio_path
    )
    duration_min, duration_max = get_duration_bounds(context)
    duration_gate = evaluate_duration_seconds(
        actual_seconds=actual_duration_seconds,
        minimum=duration_min,
        maximum=duration_max
    )
    chapters = (
        build_actual_chapters(
            sections=generated_sections,
            total_duration_seconds=actual_duration_seconds
        )
        if duration_gate["approved"]
        else []
    )

    assembly_data = build_assembly_output(
        context=context,
        generation_path=generation_path,
        qa_path=qa_path,
        generation_data=generation_data,
        qa_data=qa_data,
        audio_path=assembled_audio_path,
        actual_duration_seconds=actual_duration_seconds,
        duration_gate=duration_gate,
        chapters=chapters
    )

    assembly_path = output_dir / "audio_assembly.json"
    save_json(assembly_path, assembly_data)

    print(
        "ACTUAL_AUDIO_DURATION_SECONDS: "
        f"{duration_gate['actual_seconds']}"
    )
    print(
        "AUDIO_DURATION_GATE: "
        f"{duration_gate['status']}"
    )
    print(
        "ACTUAL_CHAPTER_COUNT: "
        f"{len(chapters)}"
    )

    if not duration_gate["approved"]:
        set_duration_revision_required(
            context=context,
            duration_gate=duration_gate,
            word_count=sum(
                item["word_count"]
                for item in sections
            )
        )
        raise ValueError(
            "Narration duration is outside the approved "
            "8-12 minute range. Script revision is required."
        )

    registry_path = register_audio_asset_ownership(
        context=context,
        generation_data=generation_data,
        qa_data=qa_data,
        assembly_data=assembly_data
    )

    save_json(generation_path, generation_data)
    save_json(qa_path, qa_data)

    save_json(assembly_path, assembly_data)

    print(
        "AUDIO_ASSET_REGISTRY: "
        f"{relative_path(registry_path)}"
    )

    context = register_output(
        context,
        "voice",
        relative_path(voice_path),
        "narration_ready"
    )
    context = register_output(
        context,
        "voice_generation",
        relative_path(generation_path),
        "audio_ready"
    )
    context = register_output(
        context,
        "audio_qa",
        relative_path(qa_path),
        "approved"
    )
    context = register_output(
        context,
        "audio_assembly",
        relative_path(assembly_path),
        "assembled"
    )
    context = register_output(
        context,
        "narration_audio",
        relative_path(assembled_audio_path),
        "assembled"
    )

    context.setdefault(
        "quality_gates",
        {}
    ).update({
        "allow_cross_video_asset_reuse": False,
        "require_audio_asset_registry_ownership": True
    })

    context = set_status(
        context,
        "audio_ready",
        "video_visual_pipeline"
    )
    save_context(context)

    print("Video Audio Pipeline completed successfully.")
    print(f"AUDIO_QA_STATUS: {qa_data['status']}")
    print(
        "AUDIO_ASSEMBLY: "
        f"{relative_path(assembly_path)}"
    )
    print(
        "NARRATION_TRACK: "
        f"{relative_path(assembled_audio_path)}"
    )


if __name__ == "__main__":
    main()
