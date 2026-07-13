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
DEFAULT_FORMAT = "mp3"

VOICE_INSTRUCTIONS = (
    "Speak as a clear, engaging YouTube documentary narrator. "
    "Use a smooth, fluent, listener-friendly pace with natural energy. "
    "Keep the tone serious and investigative, but not heavy, cold, or boring. "
    "Sound premium, curious, and easy to listen to, with a slightly lighter vocal feel. "
    "Avoid sounding like an advertisement, news anchor, dramatic trailer, or robotic narrator."
)


def load_json(file_path: Path) -> dict:
    if not file_path.exists():
        raise FileNotFoundError(f"Required file not found: {file_path}")

    return json.loads(file_path.read_text(encoding="utf-8-sig"))


def load_schema() -> dict:
    return load_json(BASE_DIR / "schema.json")


def get_intro_outro_plan_latest_path(channel: str) -> Path:
    return PROJECT_ROOT / "agents" / "intro_outro_plan" / "output" / channel.lower() / "latest.json"


def get_voice_profile_path(channel: str) -> Path:
    return PROJECT_ROOT / "config" / "voice_profiles" / f"{channel.lower()}.json"


def get_relative_path(path: Path) -> str:
    return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")


def get_audio_output_dir(channel: str) -> Path:
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    audio_dir = BASE_DIR / "output" / channel.lower() / "audio" / timestamp
    audio_dir.mkdir(parents=True, exist_ok=True)
    return audio_dir


def ensure_plan_ready(plan_data: dict) -> None:
    if plan_data.get("status") != "plan_ready":
        raise ValueError("Intro/outro plan is not plan_ready.")

    readiness = plan_data.get("readiness", {})

    if not readiness.get("ready_for_voice_generation"):
        raise ValueError("Intro/outro plan is not ready for voice generation.")


def create_audio(
    client: OpenAI,
    text: str,
    filename: str,
    audio_dir: Path,
    model: str,
    voice: str
) -> Path:
    audio_path = audio_dir / filename

    with client.audio.speech.with_streaming_response.create(
        model=model,
        voice=voice,
        input=text,
        instructions=VOICE_INSTRUCTIONS,
        response_format=DEFAULT_FORMAT
    ) as response:
        response.stream_to_file(audio_path)

    if not audio_path.exists() or audio_path.stat().st_size <= 0:
        raise ValueError(f"Audio file was not created correctly: {audio_path}")

    return audio_path


def build_audio_item(kind: str, text: str, audio_path: Path) -> dict:
    return {
        "kind": kind,
        "filename": audio_path.name,
        "relative_path": get_relative_path(audio_path),
        "format": DEFAULT_FORMAT,
        "word_count": len(text.split()),
        "text": text,
        "status": "generated"
    }


def generate_intro_outro_audio(channel: str, plan_data: dict, voice_profile: dict) -> list[dict]:
    client = OpenAI()
    audio_dir = get_audio_output_dir(channel)

    model = voice_profile["model"]
    voice = voice_profile["voice"]

    intro_text = plan_data["intro_outro"]["intro_text"]
    outro_text = plan_data["intro_outro"]["outro_text"]

    print(f"Generating intro audio with voice={voice}...", flush=True)
    intro_path = create_audio(
        client=client,
        text=intro_text,
        filename="intro.mp3",
        audio_dir=audio_dir,
        model=model,
        voice=voice
    )

    print(f"Generating outro audio with voice={voice}...", flush=True)
    outro_path = create_audio(
        client=client,
        text=outro_text,
        filename="outro.mp3",
        audio_dir=audio_dir,
        model=model,
        voice=voice
    )

    return [
        build_audio_item("intro", intro_text, intro_path),
        build_audio_item("outro", outro_text, outro_path)
    ]


def build_output(channel: str, plan_path: Path, voice_profile_path: Path, voice_profile: dict, plan_data: dict, audio_items: list[dict]) -> dict:
    return {
        "agent": "intro_outro_voice_generation",
        "version": "1.0",
        "channel": channel,
        "status": "audio_ready",
        "provider": voice_profile["provider"],
        "model": voice_profile["model"],
        "voice": voice_profile["voice"],
        "audio": {
            "format": DEFAULT_FORMAT,
            "items": audio_items,
            "intro_audio_path": next(item["relative_path"] for item in audio_items if item["kind"] == "intro"),
            "outro_audio_path": next(item["relative_path"] for item in audio_items if item["kind"] == "outro")
        },
        "readiness": {
            "intro_audio_ready": True,
            "outro_audio_ready": True,
            "audio_ready": True,
            "ready_for_extended_audio_assembly": True,
            "blocking_notes": []
        },
        "source": {
            "source_agent": "intro_outro_plan",
            "intro_outro_plan_reference": get_relative_path(plan_path),
            "voice_profile_reference": get_relative_path(voice_profile_path),
            "youtube_url": plan_data["source"].get("youtube_url")
        },
        "metadata": {
            "next_agent": "intro_outro_audio_assembly"
        }
    }


def dry_run(plan_data: dict, plan_path: Path, voice_profile: dict, voice_profile_path: Path) -> None:
    ensure_plan_ready(plan_data)

    print("Intro/Outro Voice Generation dry-run completed.")
    print(f"Plan source: {plan_path}")
    print(f"Voice profile: {voice_profile_path}")
    print(f"Provider: {voice_profile['provider']}")
    print(f"Model: {voice_profile['model']}")
    print(f"Voice: {voice_profile['voice']}")
    print(f"Format: {DEFAULT_FORMAT}")
    print(f"Intro words: {plan_data['intro_outro']['intro_word_count']}")
    print(f"Outro words: {plan_data['intro_outro']['outro_word_count']}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate intro and outro audio for Hiddenova videos."
    )

    parser.add_argument(
        "--channel",
        default=DEFAULT_CHANNEL,
        help="Channel name. Default: hiddenova"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate without generating audio."
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    channel = args.channel.lower()

    load_dotenv(PROJECT_ROOT / ".env")

    plan_path = get_intro_outro_plan_latest_path(channel)
    voice_profile_path = get_voice_profile_path(channel)

    plan_data = load_json(plan_path)
    voice_profile = load_json(voice_profile_path)

    ensure_plan_ready(plan_data)

    if args.dry_run:
        dry_run(
            plan_data=plan_data,
            plan_path=plan_path,
            voice_profile=voice_profile,
            voice_profile_path=voice_profile_path
        )
        return

    audio_items = generate_intro_outro_audio(
        channel=channel,
        plan_data=plan_data,
        voice_profile=voice_profile
    )

    final_output = build_output(
        channel=channel,
        plan_path=plan_path,
        voice_profile_path=voice_profile_path,
        voice_profile=voice_profile,
        plan_data=plan_data,
        audio_items=audio_items
    )

    schema = load_schema()
    validate(instance=final_output, schema=schema)

    latest_path = save_output(
        channel=final_output["channel"],
        data=final_output
    )

    print("Intro/Outro Voice Generation Agent completed successfully.")
    print(f"Generated audio files: {len(audio_items)}")
    print(f"Voice: {final_output['voice']}")
    print(f"Output saved to: {latest_path}")


if __name__ == "__main__":
    main()
