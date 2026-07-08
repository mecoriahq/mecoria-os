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
DEFAULT_VOICE = "cedar"
DEFAULT_FORMAT = "mp3"
MAX_TTS_INPUT_CHARACTERS = 4096

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

    return json.loads(file_path.read_text(encoding="utf-8"))


def load_schema() -> dict:
    return load_json(BASE_DIR / "schema.json")


def get_voice_latest_path(channel: str) -> Path:
    return PROJECT_ROOT / "agents" / "voice" / "output" / channel.lower() / "latest.json"


def get_relative_path(path: Path) -> str:
    return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")


def ensure_voice_package_ready(voice_data: dict) -> None:
    if voice_data.get("status") != "narration_ready":
        raise ValueError("Voice package is not narration_ready.")

    readiness = voice_data["voice_package"]["readiness"]

    if not readiness.get("narration_ready"):
        raise ValueError("Voice package narration is not ready.")


def get_audio_output_dir(channel: str) -> Path:
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    audio_dir = (
        BASE_DIR
        / "output"
        / channel.lower()
        / "audio"
        / timestamp
    )

    audio_dir.mkdir(parents=True, exist_ok=True)
    return audio_dir


def get_sample_output_dir(channel: str) -> Path:
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    sample_dir = (
        BASE_DIR
        / "output"
        / channel.lower()
        / "samples"
        / timestamp
    )

    sample_dir.mkdir(parents=True, exist_ok=True)
    return sample_dir


def validate_sections_for_tts(sections: list[dict]) -> None:
    for section in sections:
        narration = section["narration"]

        if not narration.strip():
            raise ValueError(
                f"Section {section['sequence']} has empty narration."
            )

        if len(narration) > MAX_TTS_INPUT_CHARACTERS:
            raise ValueError(
                f"Section {section['sequence']} exceeds "
                f"{MAX_TTS_INPUT_CHARACTERS} characters."
            )


def get_section_by_sequence(sections: list[dict], sequence: int) -> dict:
    for section in sections:
        if section["sequence"] == sequence:
            return section

    raise ValueError(f"Section not found: {sequence}")


def create_section_audio(
    client: OpenAI,
    section: dict,
    audio_dir: Path
) -> dict:
    sequence = section["sequence"]
    filename = f"section_{sequence:02d}.mp3"
    audio_path = audio_dir / filename

    with client.audio.speech.with_streaming_response.create(
        model=DEFAULT_MODEL,
        voice=DEFAULT_VOICE,
        input=section["narration"],
        instructions=VOICE_INSTRUCTIONS,
        response_format=DEFAULT_FORMAT
    ) as response:
        response.stream_to_file(audio_path)

    return {
        "sequence": sequence,
        "section_type": section["section_type"],
        "title": section["title"],
        "word_count": section["word_count"],
        "filename": filename,
        "relative_path": get_relative_path(audio_path),
        "format": DEFAULT_FORMAT
    }


def generate_audio_sections(voice_data: dict) -> list[dict]:
    client = OpenAI()

    channel = voice_data["channel"]
    sections = voice_data["voice_package"]["narration"]["sections"]

    validate_sections_for_tts(sections)

    audio_dir = get_audio_output_dir(channel)
    audio_sections = []

    for section in sections:
        print(
            f"Generating audio section {section['sequence']}: {section['title']}",
            flush=True
        )

        audio_sections.append(
            create_section_audio(
                client=client,
                section=section,
                audio_dir=audio_dir
            )
        )

    return audio_sections


def generate_sample_section(voice_data: dict, sequence: int) -> Path:
    client = OpenAI()

    channel = voice_data["channel"]
    sections = voice_data["voice_package"]["narration"]["sections"]

    validate_sections_for_tts(sections)

    section = get_section_by_sequence(
        sections=sections,
        sequence=sequence
    )

    sample_dir = get_sample_output_dir(channel)

    print(
        f"Generating sample audio section {section['sequence']}: {section['title']}",
        flush=True
    )

    audio_metadata = create_section_audio(
        client=client,
        section=section,
        audio_dir=sample_dir
    )

    return PROJECT_ROOT / audio_metadata["relative_path"]


def build_output(
    voice_data: dict,
    voice_path: Path,
    audio_sections: list[dict]
) -> dict:
    return {
        "agent": "voice_generation",
        "version": "1.0",
        "channel": voice_data["channel"],
        "status": "audio_ready",
        "provider": DEFAULT_PROVIDER,
        "model": DEFAULT_MODEL,
        "voice": DEFAULT_VOICE,
        "audio": {
            "format": DEFAULT_FORMAT,
            "sections": audio_sections,
            "combined_audio_file_path": None
        },
        "readiness": {
            "sections_generated": len(audio_sections),
            "audio_ready": len(audio_sections) > 0,
            "combined_audio_ready": False,
            "blocking_notes": [
                "Combined audio file is not created yet."
            ]
        },
        "source": {
            "source_agents": [
                "voice"
            ],
            "voice_package_reference": get_relative_path(voice_path),
            "narration_title": voice_data["voice_package"]["narration"]["title"]
        },
        "metadata": {
            "next_agent": "audio_qa"
        }
    }


def dry_run(
    voice_data: dict,
    voice_path: Path,
    sample_section: int | None
) -> None:
    sections = voice_data["voice_package"]["narration"]["sections"]

    validate_sections_for_tts(sections)

    print("Voice Generation Agent dry-run completed.")
    print(f"Voice package source: {voice_path}")
    print(f"Provider: {DEFAULT_PROVIDER}")
    print(f"Model: {DEFAULT_MODEL}")
    print(f"Voice: {DEFAULT_VOICE}")

    if sample_section is not None:
        section = get_section_by_sequence(
            sections=sections,
            sequence=sample_section
        )
        print(f"Sample section: {section['sequence']} - {section['title']}")
    else:
        print(f"Sections to generate: {len(sections)}")

    print(f"Output format: {DEFAULT_FORMAT}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate narration audio from Voice Package output."
    )

    parser.add_argument(
        "--channel",
        default=DEFAULT_CHANNEL,
        help="Channel name. Default: hiddenova"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate inputs without generating audio."
    )

    parser.add_argument(
        "--sample-section",
        type=int,
        default=None,
        help="Generate only one sample section by sequence number."
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    load_dotenv(PROJECT_ROOT / ".env")

    voice_path = get_voice_latest_path(args.channel)
    voice_data = load_json(voice_path)

    ensure_voice_package_ready(voice_data)

    if args.dry_run:
        dry_run(
            voice_data=voice_data,
            voice_path=voice_path,
            sample_section=args.sample_section
        )
        return

    if args.sample_section is not None:
        sample_path = generate_sample_section(
            voice_data=voice_data,
            sequence=args.sample_section
        )

        print("Voice Generation sample completed successfully.")
        print(f"Sample saved to: {sample_path}")
        return

    audio_sections = generate_audio_sections(voice_data)

    final_output = build_output(
        voice_data=voice_data,
        voice_path=voice_path,
        audio_sections=audio_sections
    )

    schema = load_schema()
    validate(instance=final_output, schema=schema)

    latest_path = save_output(
        channel=final_output["channel"],
        data=final_output
    )

    print("Voice Generation Agent completed successfully.")
    print(f"Output saved to: {latest_path}")


if __name__ == "__main__":
    main()
