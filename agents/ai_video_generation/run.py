import argparse
import base64
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import imageio_ffmpeg
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.ai_video_standard import (
    DEFAULT_MODEL,
    DEFAULT_PROVIDER,
    load_json,
    validate_plan_identity,
)
from core.ai_video_integration import (
    assert_live_generation_allowed,
    load_ai_video_production_config,
)
from core.video_run_context import (
    load_context,
    register_output,
    resolve_output,
    save_context,
)


DEFAULT_CHANNEL = "hiddenova"
VALID_MODES = {"dry-run", "mock", "live"}


def relative_path(path: Path) -> str:
    return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def run_ffmpeg(command: list[str], label: str) -> None:
    result = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"{label} failed:\n{result.stderr[-4000:]}"
        )


def mock_video_command(
    image_path: Path,
    output_path: Path,
    duration_seconds: int
) -> list[str]:
    ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
    frames = max(1, int(duration_seconds * 24))

    return [
        ffmpeg_path,
        "-y",
        "-loop",
        "1",
        "-i",
        str(image_path),
        "-vf",
        (
            "scale=1280:720:force_original_aspect_ratio=increase,"
            "crop=1280:720,"
            "zoompan="
            "z='min(1.0+on*0.0006,1.055)':"
            "x='iw/2-(iw/zoom/2)':"
            "y='ih/2-(ih/zoom/2)':"
            f"d={frames}:s=1280x720:fps=24,"
            "setsar=1,format=yuv420p"
        ),
        "-frames:v",
        str(frames),
        "-an",
        "-r",
        "24",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-pix_fmt",
        "yuv420p",
        str(output_path)
    ]


def normalize_silent_video(
    raw_path: Path,
    output_path: Path
) -> None:
    ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()

    command = [
        ffmpeg_path,
        "-y",
        "-i",
        str(raw_path),
        "-map",
        "0:v:0",
        "-vf",
        (
            "scale=1280:720:force_original_aspect_ratio=increase,"
            "crop=1280:720,fps=24,setsar=1,format=yuv420p"
        ),
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-pix_fmt",
        "yuv420p",
        str(output_path)
    ]

    run_ffmpeg(command, "AI video normalization")


def generate_live_video(
    item: dict,
    model: str,
    raw_output_path: Path
) -> None:
    try:
        from google import genai
    except ImportError as exc:
        raise RuntimeError(
            "google-genai is not installed. Install the "
            "AI video requirements before live generation."
        ) from exc

    api_key = (
        os.environ.get("GEMINI_API_KEY")
        or os.environ.get("GOOGLE_API_KEY")
    )

    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY or GOOGLE_API_KEY is required "
            "for live AI video generation."
        )

    image_path = PROJECT_ROOT / item["reference_image_path"]
    image_bytes = base64.b64encode(
        image_path.read_bytes()
    ).decode("ascii")

    client = genai.Client(api_key=api_key)
    interaction = client.interactions.create(
        model=model,
        input=[
            {
                "type": "image",
                "data": image_bytes,
                "mime_type": "image/png"
            },
            {
                "type": "text",
                "text": item["prompt"]
            }
        ],
        response_format={
            "type": "video",
            "aspect_ratio": "16:9"
        },
        generation_config={
            "video_config": {
                "task": "image_to_video"
            }
        }
    )

    output_video = getattr(
        interaction,
        "output_video",
        None
    )

    if not output_video or not getattr(output_video, "data", None):
        raise RuntimeError(
            "Gemini Omni Flash returned no inline video data."
        )

    raw_output_path.write_bytes(
        base64.b64decode(output_video.data)
    )


def get_plan_path(
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
        key="ai_video_insert_plan"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate provider-neutral AI video inserts. "
            "Dry-run is the default and makes no API calls."
        )
    )
    parser.add_argument("--channel", default=DEFAULT_CHANNEL)
    parser.add_argument("--video-id", required=True)
    parser.add_argument(
        "--mode",
        choices=sorted(VALID_MODES),
        default="dry-run"
    )
    parser.add_argument("--plan-path", default=None)
    parser.add_argument("--provider", default=DEFAULT_PROVIDER)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument(
        "--max-items",
        type=int,
        default=None
    )
    parser.add_argument(
        "--attach-context",
        action="store_true",
        help="Attach live production output to the video context."
    )
    parser.add_argument(
        "--confirm-live-cost",
        action="store_true",
        help=(
            "Required for live generation in addition to "
            "the config and environment safety switches."
        )
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    channel = args.channel.lower()
    video_id = args.video_id.lower()

    if args.mode != "live" and args.attach_context:
        raise ValueError(
            "Only live generation may be attached to production context."
        )

    load_dotenv(PROJECT_ROOT / ".env")

    if args.mode == "live":
        assert_live_generation_allowed(
            config=load_ai_video_production_config(),
            confirmed=args.confirm_live_cost
        )

    context = load_context(
        channel=channel,
        video_id=video_id
    )
    plan_path = get_plan_path(
        context=context,
        explicit_path=args.plan_path
    )
    plan = load_json(plan_path)
    validate_plan_identity(plan=plan, context=context)

    items = list(plan["items"])

    if args.max_items is not None:
        if args.max_items < 1:
            raise ValueError("--max-items must be positive.")
        items = items[:args.max_items]

    print(f"VIDEO_CONTEXT_ID: {video_id}")
    print(f"RUN_ID: {context['run_id']}")
    print(f"MODE: {args.mode}")
    print(f"PROVIDER: {args.provider}")
    print(f"MODEL: {args.model}")
    print(f"ITEM_COUNT: {len(items)}")

    if args.mode == "dry-run":
        for item in items:
            image_path = PROJECT_ROOT / item["reference_image_path"]

            if not image_path.exists():
                raise FileNotFoundError(
                    f"Reference image not found: {image_path}"
                )

            print(
                f"- {item['insert_id']} | "
                f"{item['reference_image_path']} | ready"
            )

        print("PRODUCTION_API_CALLED: false")
        print("STATUS: ai_video_generation_dry_run_ready")
        return

    output_dir = (
        BASE_DIR
        / "output"
        / channel
        / video_id
        / context["run_id"]
        / args.mode
    )
    raw_dir = output_dir / "raw"
    silent_dir = output_dir / "silent"
    raw_dir.mkdir(parents=True, exist_ok=True)
    silent_dir.mkdir(parents=True, exist_ok=True)

    generated = []

    for item in items:
        insert_id = item["insert_id"]
        reference_path = (
            PROJECT_ROOT / item["reference_image_path"]
        )

        if not reference_path.exists():
            raise FileNotFoundError(
                f"Reference image not found: {reference_path}"
            )

        raw_path = raw_dir / f"{insert_id.lower()}_raw.mp4"
        silent_path = silent_dir / f"{insert_id.lower()}.mp4"

        print(
            f"Generating {insert_id} in {args.mode} mode.",
            flush=True
        )

        if args.mode == "mock":
            run_ffmpeg(
                mock_video_command(
                    image_path=reference_path,
                    output_path=silent_path,
                    duration_seconds=int(
                        item["target_duration_seconds"]
                    )
                ),
                "Mock AI video generation"
            )
            raw_reference = None
        else:
            generate_live_video(
                item=item,
                model=args.model,
                raw_output_path=raw_path
            )
            normalize_silent_video(
                raw_path=raw_path,
                output_path=silent_path
            )
            raw_reference = relative_path(raw_path)

        if not silent_path.exists() or silent_path.stat().st_size <= 0:
            raise RuntimeError(
                f"AI video output was not created: {silent_path}"
            )

        generated.append({
            "insert_id": insert_id,
            "sequence": item["sequence"],
            "section_hint": item["section_hint"],
            "visual_role": item["visual_role"],
            "source_ai_image_insert_id": (
                item["source_ai_image_insert_id"]
            ),
            "reference_image_path": item["reference_image_path"],
            "prompt": item["prompt"],
            "provider": args.provider,
            "model": args.model,
            "generation_mode": args.mode,
            "raw_relative_path": raw_reference,
            "relative_path": relative_path(silent_path),
            "sha256": sha256(silent_path),
            "target_duration_seconds": (
                item["target_duration_seconds"]
            ),
            "audio_stripped": True,
            "status": "generated_pending_qa"
        })

    output = {
        "agent": "ai_video_generation",
        "version": "1.0",
        "channel": channel,
        "video_id": video_id,
        "run_id": context["run_id"],
        "status": "videos_ready",
        "generation_mode": args.mode,
        "provider": {
            "provider_id": args.provider,
            "model": args.model
        },
        "summary": {
            "generated_video_count": len(generated),
            "production_ready": args.mode == "live",
            "production_api_called": args.mode == "live",
            "audio_stripped_count": len(generated)
        },
        "generated_videos": generated,
        "source": {
            "plan_reference": relative_path(plan_path)
        },
        "readiness": {
            "technical_qa_ready": True,
            "production_context_attachable": args.mode == "live"
        }
    }

    output_path = output_dir / "ai_video_generation.json"
    output_path.write_text(
        json.dumps(output, indent=2, ensure_ascii=True),
        encoding="utf-8"
    )

    if args.attach_context:
        context = register_output(
            context=context,
            agent="ai_video_generation",
            reference=relative_path(output_path),
            status="videos_ready"
        )
        save_context(context)

    print("STATUS: ai_video_generation_ready")
    print(f"OUTPUT: {relative_path(output_path)}")
    print(f"PRODUCTION_API_CALLED: {str(args.mode == 'live').lower()}")


if __name__ == "__main__":
    main()
