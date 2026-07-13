import argparse
import json
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from jsonschema import validate
from openai import OpenAI

from output import save_output


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent.parent

DEFAULT_CHANNEL = "hiddenova"
DEFAULT_PROVIDER = "openai"
DEFAULT_MODEL = "gpt-4o-mini-tts"
DEFAULT_FORMAT = "mp3"

VOICE_CANDIDATES = [
    "cedar",
    "onyx",
    "ash",
    "sage",
    "verse",
    "alloy",
    "nova"
]

SAMPLE_TEXT = (
    "Every returned package looks simple. "
    "But behind it is a hidden system of warehouses, scanners, resale markets, and decisions most customers never see. "
    "This is Hiddenova, where we uncover the invisible machines behind everyday life."
)

VOICE_INSTRUCTIONS = (
    "Speak as a premium YouTube documentary narrator. "
    "The tone should be serious, curious, intelligent, and smooth. "
    "Avoid dramatic trailer energy, news anchor delivery, robotic pacing, or advertisement style. "
    "The voice should feel trustworthy, global, cinematic, and easy to listen to for a 10-minute documentary."
)

EVALUATION_CRITERIA = [
    "premium documentary feeling",
    "clarity",
    "natural flow",
    "authority",
    "curiosity",
    "listener comfort",
    "low boredom risk",
    "Hiddenova brand fit"
]


def load_json(file_path: Path) -> dict:
    if not file_path.exists():
        raise FileNotFoundError(f"Required file not found: {file_path}")

    return json.loads(file_path.read_text(encoding="utf-8-sig"))


def load_schema() -> dict:
    return load_json(BASE_DIR / "schema.json")


def get_relative_path(path: Path) -> str:
    return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")


def get_sample_output_dir(channel: str) -> Path:
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    sample_dir = BASE_DIR / "output" / channel.lower() / "samples" / timestamp
    sample_dir.mkdir(parents=True, exist_ok=True)
    return sample_dir


def get_standard_path() -> Path:
    return PROJECT_ROOT / "docs" / "standards" / "hiddenova-voice-casting.md"


def generate_voice_sample(client: OpenAI, voice: str, sample_dir: Path) -> dict:
    filename = f"hiddenova_voice_sample_{voice}.mp3"
    audio_path = sample_dir / filename

    with client.audio.speech.with_streaming_response.create(
        model=DEFAULT_MODEL,
        voice=voice,
        input=SAMPLE_TEXT,
        instructions=VOICE_INSTRUCTIONS,
        response_format=DEFAULT_FORMAT
    ) as response:
        response.stream_to_file(audio_path)

    if not audio_path.exists() or audio_path.stat().st_size <= 0:
        raise ValueError(f"Voice sample was not created correctly: {audio_path}")

    return {
        "voice": voice,
        "filename": filename,
        "relative_path": get_relative_path(audio_path),
        "format": DEFAULT_FORMAT,
        "sample_text": SAMPLE_TEXT,
        "instructions": VOICE_INSTRUCTIONS,
        "status": "generated_pending_founder_review"
    }


def generate_samples(channel: str, voices: list[str]) -> tuple[list[dict], list[dict], Path]:
    client = OpenAI()
    sample_dir = get_sample_output_dir(channel)

    samples = []
    failed_samples = []

    for voice in voices:
        print(f"Generating voice sample: {voice}", flush=True)

        try:
            samples.append(
                generate_voice_sample(
                    client=client,
                    voice=voice,
                    sample_dir=sample_dir
                )
            )
        except Exception as error:
            failed_samples.append({
                "voice": voice,
                "status": "failed",
                "error": str(error)
            })
            print(f"Voice sample failed: {voice} | {error}", flush=True)

    return samples, failed_samples, sample_dir


def build_output(
    channel: str,
    mode: str,
    voices: list[str],
    samples: list[dict],
    failed_samples: list[dict],
    sample_dir: Path | None
) -> dict:
    status = "dry_run_ready" if mode == "dry_run" else ("samples_ready" if samples else "blocked")

    return {
        "agent": "voice_casting",
        "version": "1.0",
        "channel": channel,
        "status": status,
        "provider": DEFAULT_PROVIDER,
        "model": DEFAULT_MODEL,
        "summary": {
            "candidate_voice_count": len(voices),
            "generated_sample_count": len(samples),
            "failed_sample_count": len(failed_samples),
            "sample_output_dir": get_relative_path(sample_dir) if sample_dir else None,
            "baseline_voice": "cedar",
            "voice_locked": False,
            "next_step": "founder_voice_review"
        },
        "samples": samples,
        "failed_samples": failed_samples,
        "evaluation_criteria": EVALUATION_CRITERIA,
        "source": {
            "standard_reference": get_relative_path(get_standard_path()),
            "sample_text": SAMPLE_TEXT,
            "note": "Cedar is the current test voice, not the final locked Hiddenova voice."
        },
        "metadata": {
            "next_agent": "founder_voice_review"
        }
    }


def print_summary(output: dict) -> None:
    print("Voice Casting Agent completed.")
    print(f"Status: {output['status']}")
    print(f"Candidate voices: {output['summary']['candidate_voice_count']}")
    print(f"Generated samples: {output['summary']['generated_sample_count']}")
    print(f"Failed samples: {output['summary']['failed_sample_count']}")
    print(f"Output dir: {output['summary']['sample_output_dir']}")

    if output["samples"]:
        print("Generated:")
        for sample in output["samples"]:
            print(f"- {sample['voice']} | {sample['relative_path']}")

    if output["failed_samples"]:
        print("Failed:")
        for failed in output["failed_samples"]:
            print(f"- {failed['voice']} | {failed['error']}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate Hiddenova voice casting samples."
    )

    parser.add_argument(
        "--channel",
        default=DEFAULT_CHANNEL,
        help="Channel name. Default: hiddenova"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate without generating voice samples."
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    channel = args.channel.lower()

    load_dotenv(PROJECT_ROOT / ".env")

    if args.dry_run:
        final_output = build_output(
            channel=channel,
            mode="dry_run",
            voices=VOICE_CANDIDATES,
            samples=[],
            failed_samples=[],
            sample_dir=None
        )

        schema = load_schema()
        validate(instance=final_output, schema=schema)

        print_summary(final_output)
        return

    samples, failed_samples, sample_dir = generate_samples(
        channel=channel,
        voices=VOICE_CANDIDATES
    )

    final_output = build_output(
        channel=channel,
        mode="generate",
        voices=VOICE_CANDIDATES,
        samples=samples,
        failed_samples=failed_samples,
        sample_dir=sample_dir
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
