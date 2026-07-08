import json
import re
from pathlib import Path

from dotenv import load_dotenv
from jsonschema import validate

from output import save_output


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent.parent

DEFAULT_CHANNEL = "hiddenova"


def load_json(file_path: Path) -> dict:
    if not file_path.exists():
        raise FileNotFoundError(f"Required file not found: {file_path}")

    return json.loads(file_path.read_text(encoding="utf-8"))


def load_schema() -> dict:
    return load_json(BASE_DIR / "schema.json")


def get_script_latest_path(channel: str) -> Path:
    return PROJECT_ROOT / "agents" / "script" / "output" / channel.lower() / "latest.json"


def get_relative_path(path: Path) -> str:
    return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")


def count_words(text: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", text))


def estimate_duration_minutes(word_count: int, words_per_minute: int = 145) -> float:
    if word_count <= 0:
        return 0.0

    return round(word_count / words_per_minute, 2)


def create_section(
    sequence: int,
    section_type: str,
    title: str,
    narration: str,
    visual_direction: str | None = None
) -> dict:
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

    sections.append(
        create_section(
            sequence=1,
            section_type="hook",
            title="Hook",
            narration=script["hook"]["narration"]
        )
    )

    sections.append(
        create_section(
            sequence=2,
            section_type="introduction",
            title="Introduction",
            narration=script["introduction"]["narration"]
        )
    )

    sequence = 3

    for section in script["main_sections"]:
        sections.append(
            create_section(
                sequence=sequence,
                section_type="main_section",
                title=section["title"],
                narration=section["narration"],
                visual_direction=section["visual_direction"]
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


def build_voice_package(script_data: dict, script_path: Path) -> dict:
    script = script_data["script"]
    sections = build_sections(script_data)

    full_text = "\n\n".join(section["narration"] for section in sections)
    total_word_count = count_words(full_text)

    return {
        "agent": "voice",
        "version": "1.0",
        "channel": script_data["channel"],
        "status": "narration_ready",
        "voice_package": {
            "voice_profile": {
                "language": "en",
                "voice_style": "calm documentary narration",
                "tone": "serious, investigative, clear, premium",
                "pace": "medium",
                "target_platform": "youtube",
                "provider": None,
                "voice_id": None
            },
            "narration": {
                "title": script["title"],
                "estimated_script_duration": script["estimated_duration"],
                "estimated_voice_duration_minutes": estimate_duration_minutes(total_word_count),
                "word_count": total_word_count,
                "sections": sections,
                "full_text": full_text
            },
            "assets": {
                "script_reference": get_relative_path(script_path),
                "audio_file_path": None
            },
            "readiness": {
                "script_loaded": True,
                "narration_ready": True,
                "audio_ready": False,
                "blocking_notes": [
                    "Audio file is not generated yet."
                ]
            }
        },
        "source": {
            "source_agents": [
                "script"
            ],
            "script_title": script["title"],
            "idea_title": script_data["source"]["idea_title"]
        },
        "metadata": {
            "next_agent": "voice_generation"
        }
    }


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")

    script_path = get_script_latest_path(DEFAULT_CHANNEL)
    script_data = load_json(script_path)

    final_output = build_voice_package(
        script_data=script_data,
        script_path=script_path
    )

    schema = load_schema()
    validate(instance=final_output, schema=schema)

    latest_path = save_output(
        channel=final_output["channel"],
        data=final_output
    )

    print("Voice Package Agent completed successfully.")
    print(f"Output saved to: {latest_path}")


if __name__ == "__main__":
    main()
