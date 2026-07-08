import json
from pathlib import Path

from dotenv import load_dotenv
from jsonschema import validate

from output import save_output


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent.parent

DEFAULT_CHANNEL = "hiddenova"
MIN_AUDIO_BYTES = 1024


def load_json(file_path: Path) -> dict:
    if not file_path.exists():
        raise FileNotFoundError(f"Required file not found: {file_path}")

    return json.loads(file_path.read_text(encoding="utf-8"))


def load_schema() -> dict:
    return load_json(BASE_DIR / "schema.json")


def get_voice_generation_latest_path(channel: str) -> Path:
    return PROJECT_ROOT / "agents" / "voice_generation" / "output" / channel.lower() / "latest.json"


def get_relative_path(path: Path) -> str:
    return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")


def check_audio_section(section: dict) -> dict:
    relative_path = section["relative_path"]
    audio_path = PROJECT_ROOT / relative_path

    file_exists = audio_path.exists()
    file_readable = False
    size_bytes = None

    if file_exists:
        try:
            size_bytes = audio_path.stat().st_size
            with audio_path.open("rb") as file:
                file.read(1)
            file_readable = True
        except OSError:
            file_readable = False

    format_valid = (
        section.get("format") == "mp3"
        and audio_path.suffix.lower() == ".mp3"
    )

    size_valid = size_bytes is not None and size_bytes >= MIN_AUDIO_BYTES

    passed_checks = sum([
        file_exists,
        file_readable,
        format_valid,
        size_valid
    ])

    score = round((passed_checks / 4) * 100)
    status = "pass" if score == 100 else "fail"

    return {
        "sequence": section["sequence"],
        "title": section["title"],
        "relative_path": relative_path,
        "file_exists": file_exists,
        "file_readable": file_readable,
        "format_valid": format_valid,
        "size_bytes": size_bytes,
        "size_valid": size_valid,
        "status": status,
        "score": score
    }


def build_issues(
    metadata_ready: bool,
    section_checks: list[dict]
) -> list[dict]:
    issues = []

    if not metadata_ready:
        issues.append({
            "field": "voice_generation",
            "severity": "high",
            "message": "Voice generation metadata is not audio_ready."
        })

    for check in section_checks:
        if check["status"] == "pass":
            continue

        issues.append({
            "field": f"section_{check['sequence']:02d}",
            "severity": "high",
            "message": (
                f"Audio section {check['sequence']} failed technical validation. "
                f"file_exists={check['file_exists']}, "
                f"file_readable={check['file_readable']}, "
                f"format_valid={check['format_valid']}, "
                f"size_valid={check['size_valid']}."
            )
        })

    return issues


def build_audio_qa_output(
    voice_generation_data: dict,
    voice_generation_path: Path
) -> dict:
    audio_sections = voice_generation_data["audio"]["sections"]

    section_checks = [
        check_audio_section(section)
        for section in audio_sections
    ]

    expected_sections = len(audio_sections)
    valid_sections = sum(
        1 for check in section_checks
        if check["status"] == "pass"
    )

    metadata_ready = (
        voice_generation_data.get("status") == "audio_ready"
        and voice_generation_data["readiness"].get("audio_ready") is True
    )

    all_sections_valid = expected_sections > 0 and valid_sections == expected_sections
    approved = metadata_ready and all_sections_valid

    overall_score = (
        round((valid_sections / expected_sections) * 100)
        if expected_sections
        else 0
    )

    issues = build_issues(
        metadata_ready=metadata_ready,
        section_checks=section_checks
    )

    recommendations = []

    if approved:
        recommendations.append({
            "field": "audio_assembly",
            "suggestion": "Proceed to audio assembly and combine section MP3 files into one narration track."
        })
    else:
        recommendations.append({
            "field": "voice_generation",
            "suggestion": "Regenerate missing or invalid audio sections before audio assembly."
        })

    return {
        "agent": "audio_qa",
        "version": "1.0",
        "channel": voice_generation_data["channel"],
        "status": "approved" if approved else "rejected",
        "overall_score": overall_score,
        "summary": {
            "expected_sections": expected_sections,
            "checked_sections": len(section_checks),
            "valid_sections": valid_sections,
            "missing_sections": [
                check["sequence"]
                for check in section_checks
                if not check["file_exists"]
            ],
            "audio_ready": voice_generation_data["readiness"]["audio_ready"],
            "combined_audio_ready": voice_generation_data["readiness"]["combined_audio_ready"]
        },
        "checks": {
            "voice_generation_status": voice_generation_data["status"],
            "audio_metadata_ready": metadata_ready,
            "audio_ready": voice_generation_data["readiness"]["audio_ready"],
            "combined_audio_ready": voice_generation_data["readiness"]["combined_audio_ready"]
        },
        "section_checks": section_checks,
        "issues": issues,
        "recommendations": recommendations,
        "source": {
            "source_agents": [
                "voice_generation"
            ],
            "voice_generation_reference": get_relative_path(voice_generation_path)
        },
        "metadata": {
            "next_agent": "audio_assembly" if approved else "voice_generation"
        }
    }


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")

    voice_generation_path = get_voice_generation_latest_path(DEFAULT_CHANNEL)
    voice_generation_data = load_json(voice_generation_path)

    final_output = build_audio_qa_output(
        voice_generation_data=voice_generation_data,
        voice_generation_path=voice_generation_path
    )

    schema = load_schema()
    validate(instance=final_output, schema=schema)

    latest_path = save_output(
        channel=final_output["channel"],
        data=final_output
    )

    print("Audio QA Agent completed successfully.")
    print(f"Output saved to: {latest_path}")


if __name__ == "__main__":
    main()
