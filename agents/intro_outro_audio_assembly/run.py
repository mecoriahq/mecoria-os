import argparse
import json
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
OUTPUT_FILENAME = "extended_narration_track.mp3"


def load_json(file_path: Path) -> dict:
    if not file_path.exists():
        raise FileNotFoundError(f"Required file not found: {file_path}")

    return json.loads(file_path.read_text(encoding="utf-8-sig"))


def load_schema() -> dict:
    return load_json(BASE_DIR / "schema.json")


def get_intro_outro_voice_latest_path(channel: str) -> Path:
    return PROJECT_ROOT / "agents" / "intro_outro_voice_generation" / "output" / channel.lower() / "latest.json"


def get_audio_assembly_latest_path(channel: str) -> Path:
    return PROJECT_ROOT / "agents" / "audio_assembly" / "output" / channel.lower() / "latest.json"


def get_relative_path(path: Path) -> str:
    return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")


def get_output_dir(channel: str) -> Path:
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    output_dir = BASE_DIR / "output" / channel.lower() / "assembled" / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


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


def ensure_inputs_ready(intro_outro_data: dict, audio_assembly_data: dict) -> None:
    if intro_outro_data.get("status") != "audio_ready":
        raise ValueError("Intro/outro voice generation output is not audio_ready.")

    if not intro_outro_data.get("readiness", {}).get("ready_for_extended_audio_assembly"):
        raise ValueError("Intro/outro audio is not ready for extended audio assembly.")

    if audio_assembly_data.get("status") != "assembled":
        raise ValueError("Main audio assembly output is not assembled.")

    if not audio_assembly_data.get("readiness", {}).get("combined_audio_ready"):
        raise ValueError("Main combined narration audio is not ready.")


def get_input_audio_paths(intro_outro_data: dict, audio_assembly_data: dict) -> tuple[Path, Path, Path]:
    intro_path = PROJECT_ROOT / intro_outro_data["audio"]["intro_audio_path"]
    main_path = PROJECT_ROOT / audio_assembly_data["audio"]["combined_audio"]["relative_path"]
    outro_path = PROJECT_ROOT / intro_outro_data["audio"]["outro_audio_path"]

    for path in [intro_path, main_path, outro_path]:
        if not path.exists():
            raise FileNotFoundError(f"Required audio file not found: {path}")

    return intro_path, main_path, outro_path


def write_concat_list(audio_paths: list[Path], concat_list_path: Path) -> None:
    lines = []

    for audio_path in audio_paths:
        safe_path = audio_path.resolve().as_posix().replace("'", "\\'")
        lines.append(f"file '{safe_path}'")

    concat_list_path.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8"
    )


def assemble_extended_audio(intro_path: Path, main_path: Path, outro_path: Path, output_dir: Path) -> Path:
    ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
    output_path = output_dir / OUTPUT_FILENAME
    concat_list_path = output_dir / "intro_main_outro_concat.txt"

    write_concat_list(
        audio_paths=[intro_path, main_path, outro_path],
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
        "-c:a",
        "libmp3lame",
        "-b:a",
        "192k",
        str(output_path)
    ]

    result = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        raise RuntimeError("ffmpeg extended audio assembly failed:\n" + result.stderr[-4000:])

    if not output_path.exists() or output_path.stat().st_size <= 0:
        raise ValueError(f"Extended audio file was not created correctly: {output_path}")

    return output_path


def build_output(
    channel: str,
    intro_outro_voice_path: Path,
    audio_assembly_path: Path,
    intro_path: Path,
    main_path: Path,
    outro_path: Path,
    extended_path: Path
) -> dict:
    intro_duration = get_media_duration_seconds(intro_path)
    main_duration = get_media_duration_seconds(main_path)
    outro_duration = get_media_duration_seconds(outro_path)
    extended_duration = get_media_duration_seconds(extended_path)

    return {
        "agent": "intro_outro_audio_assembly",
        "version": "1.0",
        "channel": channel,
        "status": "assembled",
        "audio": {
            "format": "mp3",
            "intro_audio_path": get_relative_path(intro_path),
            "main_audio_path": get_relative_path(main_path),
            "outro_audio_path": get_relative_path(outro_path),
            "combined_audio": {
                "filename": extended_path.name,
                "relative_path": get_relative_path(extended_path),
                "format": "mp3",
                "size_bytes": extended_path.stat().st_size,
                "duration_seconds": round(extended_duration, 2)
            },
            "durations": {
                "intro_seconds": round(intro_duration, 2),
                "main_seconds": round(main_duration, 2),
                "outro_seconds": round(outro_duration, 2),
                "extended_total_seconds": round(extended_duration, 2)
            }
        },
        "readiness": {
            "intro_ready": True,
            "main_audio_ready": True,
            "outro_ready": True,
            "combined_audio_ready": True,
            "ready_for_hybrid_video_assembly": True,
            "blocking_notes": []
        },
        "source": {
            "source_agents": [
                "intro_outro_voice_generation",
                "audio_assembly"
            ],
            "intro_outro_voice_reference": get_relative_path(intro_outro_voice_path),
            "main_audio_assembly_reference": get_relative_path(audio_assembly_path)
        },
        "metadata": {
            "next_agent": "hybrid_video_assembly"
        }
    }


def print_summary(output: dict) -> None:
    print("Intro/Outro Audio Assembly Agent completed successfully.")
    print(f"Status: {output['status']}")
    print(f"Intro seconds: {output['audio']['durations']['intro_seconds']}")
    print(f"Main seconds: {output['audio']['durations']['main_seconds']}")
    print(f"Outro seconds: {output['audio']['durations']['outro_seconds']}")
    print(f"Extended total seconds: {output['audio']['durations']['extended_total_seconds']}")
    print(f"Extended audio: {output['audio']['combined_audio']['relative_path']}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Assemble intro + main narration + outro into one extended narration track."
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
    channel = args.channel.lower()

    load_dotenv(PROJECT_ROOT / ".env")

    intro_outro_voice_path = get_intro_outro_voice_latest_path(channel)
    audio_assembly_path = get_audio_assembly_latest_path(channel)

    intro_outro_data = load_json(intro_outro_voice_path)
    audio_assembly_data = load_json(audio_assembly_path)

    ensure_inputs_ready(
        intro_outro_data=intro_outro_data,
        audio_assembly_data=audio_assembly_data
    )

    intro_path, main_path, outro_path = get_input_audio_paths(
        intro_outro_data=intro_outro_data,
        audio_assembly_data=audio_assembly_data
    )

    if args.dry_run:
        print("Intro/Outro Audio Assembly dry-run completed.")
        print(f"Intro: {intro_path}")
        print(f"Main: {main_path}")
        print(f"Outro: {outro_path}")
        return

    output_dir = get_output_dir(channel)

    extended_path = assemble_extended_audio(
        intro_path=intro_path,
        main_path=main_path,
        outro_path=outro_path,
        output_dir=output_dir
    )

    final_output = build_output(
        channel=channel,
        intro_outro_voice_path=intro_outro_voice_path,
        audio_assembly_path=audio_assembly_path,
        intro_path=intro_path,
        main_path=main_path,
        outro_path=outro_path,
        extended_path=extended_path
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
