import argparse
import json
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
OUTPUT_FILENAME = "narration_track.mp3"


def load_json(file_path: Path) -> dict:
    if not file_path.exists():
        raise FileNotFoundError(f"Required file not found: {file_path}")

    return json.loads(file_path.read_text(encoding="utf-8"))


def load_schema() -> dict:
    return load_json(BASE_DIR / "schema.json")


def get_voice_generation_latest_path(channel: str) -> Path:
    return PROJECT_ROOT / "agents" / "voice_generation" / "output" / channel.lower() / "latest.json"


def get_audio_qa_latest_path(channel: str) -> Path:
    return PROJECT_ROOT / "agents" / "audio_qa" / "output" / channel.lower() / "latest.json"


def get_relative_path(path: Path) -> str:
    return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")


def get_assembly_output_dir(channel: str) -> Path:
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    output_dir = (
        BASE_DIR
        / "output"
        / channel.lower()
        / "assembled"
        / timestamp
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def ensure_audio_qa_approved(audio_qa_data: dict) -> None:
    if audio_qa_data.get("status") != "approved":
        raise ValueError("Audio QA is not approved. Audio Assembly Agent should not run.")

    if audio_qa_data["metadata"].get("next_agent") != "audio_assembly":
        raise ValueError("Audio QA next_agent is not audio_assembly.")


def get_ordered_audio_sections(voice_generation_data: dict) -> list[dict]:
    sections = voice_generation_data["audio"]["sections"]

    return sorted(
        sections,
        key=lambda section: section["sequence"]
    )


def validate_audio_files(sections: list[dict]) -> None:
    if not sections:
        raise ValueError("No audio sections found.")

    for section in sections:
        audio_path = PROJECT_ROOT / section["relative_path"]

        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        if audio_path.suffix.lower() != ".mp3":
            raise ValueError(f"Audio file is not MP3: {audio_path}")

        if audio_path.stat().st_size <= 0:
            raise ValueError(f"Audio file is empty: {audio_path}")


def create_concat_list(sections: list[dict], concat_list_path: Path) -> None:
    lines = []

    for section in sections:
        audio_path = (PROJECT_ROOT / section["relative_path"]).resolve()
        safe_path = audio_path.as_posix().replace("'", "\\'")
        lines.append(f"file '{safe_path}'")

    concat_list_path.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8"
    )


def assemble_audio_with_ffmpeg(
    sections: list[dict],
    output_dir: Path
) -> Path:
    ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()

    concat_list_path = output_dir / "concat_list.txt"
    output_path = output_dir / OUTPUT_FILENAME

    create_concat_list(
        sections=sections,
        concat_list_path=concat_list_path
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
            "ffmpeg audio assembly failed:\n"
            + result.stderr[-4000:]
        )

    if not output_path.exists():
        raise FileNotFoundError(f"Assembled audio was not created: {output_path}")

    if output_path.stat().st_size <= 0:
        raise ValueError(f"Assembled audio is empty: {output_path}")

    return output_path


def build_output(
    voice_generation_data: dict,
    audio_qa_data: dict,
    voice_generation_path: Path,
    audio_qa_path: Path,
    assembled_audio_path: Path,
    sections: list[dict]
) -> dict:
    return {
        "agent": "audio_assembly",
        "version": "1.0",
        "channel": voice_generation_data["channel"],
        "status": "assembled",
        "audio": {
            "format": "mp3",
            "section_count": len(sections),
            "source_sections": [
                {
                    "sequence": section["sequence"],
                    "title": section["title"],
                    "relative_path": section["relative_path"]
                }
                for section in sections
            ],
            "combined_audio": {
                "filename": assembled_audio_path.name,
                "relative_path": get_relative_path(assembled_audio_path),
                "format": "mp3",
                "size_bytes": assembled_audio_path.stat().st_size
            }
        },
        "readiness": {
            "audio_qa_approved": audio_qa_data["status"] == "approved",
            "sections_loaded": len(sections),
            "combined_audio_ready": True,
            "blocking_notes": []
        },
        "source": {
            "source_agents": [
                "voice_generation",
                "audio_qa"
            ],
            "voice_generation_reference": get_relative_path(voice_generation_path),
            "audio_qa_reference": get_relative_path(audio_qa_path)
        },
        "metadata": {
            "next_agent": "video_assembly"
        }
    }


def dry_run(
    voice_generation_data: dict,
    audio_qa_data: dict
) -> None:
    ensure_audio_qa_approved(audio_qa_data)

    sections = get_ordered_audio_sections(voice_generation_data)
    validate_audio_files(sections)

    ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()

    print("Audio Assembly Agent dry-run completed.")
    print(f"FFmpeg: {ffmpeg_path}")
    print(f"Sections to assemble: {len(sections)}")
    print(f"Output filename: {OUTPUT_FILENAME}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Assemble narration section MP3 files into one narration track."
    )

    parser.add_argument(
        "--channel",
        default=DEFAULT_CHANNEL,
        help="Channel name. Default: hiddenova"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate inputs without assembling audio."
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    load_dotenv(PROJECT_ROOT / ".env")

    voice_generation_path = get_voice_generation_latest_path(args.channel)
    audio_qa_path = get_audio_qa_latest_path(args.channel)

    voice_generation_data = load_json(voice_generation_path)
    audio_qa_data = load_json(audio_qa_path)

    if args.dry_run:
        dry_run(
            voice_generation_data=voice_generation_data,
            audio_qa_data=audio_qa_data
        )
        return

    ensure_audio_qa_approved(audio_qa_data)

    sections = get_ordered_audio_sections(voice_generation_data)
    validate_audio_files(sections)

    output_dir = get_assembly_output_dir(voice_generation_data["channel"])

    assembled_audio_path = assemble_audio_with_ffmpeg(
        sections=sections,
        output_dir=output_dir
    )

    final_output = build_output(
        voice_generation_data=voice_generation_data,
        audio_qa_data=audio_qa_data,
        voice_generation_path=voice_generation_path,
        audio_qa_path=audio_qa_path,
        assembled_audio_path=assembled_audio_path,
        sections=sections
    )

    schema = load_schema()
    validate(instance=final_output, schema=schema)

    latest_path = save_output(
        channel=final_output["channel"],
        data=final_output
    )

    print("Audio Assembly Agent completed successfully.")
    print(f"Assembled audio saved to: {assembled_audio_path}")
    print(f"Output saved to: {latest_path}")


if __name__ == "__main__":
    main()
