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
OUTPUT_FILENAME = "video_draft.mp4"
VIDEO_MODE = "animated_thumbnail_with_narration"
VIDEO_WIDTH = 1920
VIDEO_HEIGHT = 1080
FPS = 30


def load_json(file_path: Path) -> dict:
    if not file_path.exists():
        raise FileNotFoundError(f"Required file not found: {file_path}")

    return json.loads(file_path.read_text(encoding="utf-8"))


def load_schema() -> dict:
    return load_json(BASE_DIR / "schema.json")


def get_audio_assembly_latest_path(channel: str) -> Path:
    return PROJECT_ROOT / "agents" / "audio_assembly" / "output" / channel.lower() / "latest.json"


def get_publisher_latest_path(channel: str) -> Path:
    return PROJECT_ROOT / "agents" / "publisher" / "output" / channel.lower() / "latest.json"


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

    if publisher_data.get("status") != "metadata_ready":
        raise ValueError("Publisher package is not metadata_ready.")

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


def assemble_video(
    thumbnail_path: Path,
    audio_path: Path,
    output_dir: Path
) -> Path:
    ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
    output_path = output_dir / OUTPUT_FILENAME

    filter_complex = (
        "[0:v]split=2[base][fg];"
        f"[base]scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={VIDEO_WIDTH}:{VIDEO_HEIGHT},boxblur=20:1[bg];"
        f"[fg]scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:force_original_aspect_ratio=decrease[fg2];"
        "[bg][fg2]overlay=(W-w)/2:(H-h)/2,"
        "zoompan=z='min(1.0+on*0.00002,1.08)':"
        "x='iw/2-(iw/zoom/2)':"
        "y='ih/2-(ih/zoom/2)':"
        f"d=1:s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:fps={FPS},"
        "format=yuv420p[v]"
    )

    command = [
        ffmpeg_path,
        "-y",
        "-loop",
        "1",
        "-i",
        str(thumbnail_path),
        "-i",
        str(audio_path),
        "-filter_complex",
        filter_complex,
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

    result = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        raise RuntimeError(
            "ffmpeg video assembly failed:\n"
            + result.stderr[-4000:]
        )

    if not output_path.exists():
        raise FileNotFoundError(f"Video draft was not created: {output_path}")

    if output_path.stat().st_size <= 0:
        raise ValueError(f"Video draft is empty: {output_path}")

    return output_path


def build_output(
    audio_assembly_data: dict,
    publisher_data: dict,
    audio_assembly_path: Path,
    publisher_path: Path,
    thumbnail_path: Path,
    audio_path: Path,
    video_path: Path
) -> dict:
    return {
        "agent": "video_assembly",
        "version": "1.0",
        "channel": audio_assembly_data["channel"],
        "status": "draft_ready",
        "video": {
            "filename": video_path.name,
            "relative_path": get_relative_path(video_path),
            "format": "mp4",
            "size_bytes": video_path.stat().st_size,
            "resolution": f"{VIDEO_WIDTH}x{VIDEO_HEIGHT}",
            "fps": FPS,
            "mode": VIDEO_MODE,
            "thumbnail_image_path": get_relative_path(thumbnail_path),
            "audio_track_path": get_relative_path(audio_path)
        },
        "readiness": {
            "thumbnail_ready": True,
            "audio_ready": True,
            "video_ready": True,
            "upload_ready": False,
            "blocking_notes": [
                "Video QA has not been completed yet."
            ]
        },
        "source": {
            "source_agents": [
                "audio_assembly",
                "publisher"
            ],
            "audio_assembly_reference": get_relative_path(audio_assembly_path),
            "publisher_reference": get_relative_path(publisher_path),
            "title": publisher_data["publishing_package"]["video_metadata"]["title"]
        },
        "metadata": {
            "next_agent": "video_qa"
        }
    }


def dry_run(audio_assembly_data: dict, publisher_data: dict) -> None:
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
    print(f"Mode: {VIDEO_MODE}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Assemble a YouTube video draft from thumbnail and narration audio."
    )

    parser.add_argument(
        "--channel",
        default=DEFAULT_CHANNEL,
        help="Channel name. Default: hiddenova"
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

    audio_assembly_data = load_json(audio_assembly_path)
    publisher_data = load_json(publisher_path)

    if args.dry_run:
        dry_run(
            audio_assembly_data=audio_assembly_data,
            publisher_data=publisher_data
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

    video_path = assemble_video(
        thumbnail_path=thumbnail_path,
        audio_path=audio_path,
        output_dir=output_dir
    )

    final_output = build_output(
        audio_assembly_data=audio_assembly_data,
        publisher_data=publisher_data,
        audio_assembly_path=audio_assembly_path,
        publisher_path=publisher_path,
        thumbnail_path=thumbnail_path,
        audio_path=audio_path,
        video_path=video_path
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
