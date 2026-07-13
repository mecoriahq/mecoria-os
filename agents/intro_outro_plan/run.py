import argparse
import json
from pathlib import Path

from dotenv import load_dotenv
from jsonschema import validate

from output import save_output


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent.parent

DEFAULT_CHANNEL = "hiddenova"


INTRO_TEXT = (
    "Every returned package looks simple. "
    "But behind it is a hidden system of warehouses, scanners, resale markets, and decisions most customers never see. "
    "Welcome to Hiddenova. "
    "In this video, we follow what really happens after you send something back, and why online returns have become one of the most overlooked machines in modern commerce."
)

OUTRO_TEXT = (
    "If you want more documentaries about the hidden systems behind everyday life, subscribe to Hiddenova. "
    "And tell us in the comments which system we should uncover next."
)


def load_json(file_path: Path) -> dict:
    if not file_path.exists():
        raise FileNotFoundError(f"Required file not found: {file_path}")

    return json.loads(file_path.read_text(encoding="utf-8-sig"))


def load_schema() -> dict:
    return load_json(BASE_DIR / "schema.json")


def get_latest_review_path(channel: str) -> Path:
    review_dir = PROJECT_ROOT / "records" / "reviews" / channel.lower()

    if not review_dir.exists():
        raise FileNotFoundError(f"Review directory not found: {review_dir}")

    files = sorted(
        review_dir.glob("*founder_final_review.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True
    )

    if not files:
        raise FileNotFoundError("No founder final review record found.")

    return files[0]


def get_standard_path() -> Path:
    return PROJECT_ROOT / "docs" / "standards" / "hiddenova-intro-outro.md"


def get_relative_path(path: Path) -> str:
    return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")


def build_output(channel: str, review_path: Path, review_data: dict, standard_path: Path) -> dict:
    return {
        "agent": "intro_outro_plan",
        "version": "1.0",
        "channel": channel,
        "status": "plan_ready",
        "intro_outro": {
            "opening_structure": [
                "cold_open",
                "hiddenova_context_line",
                "micro_summary"
            ],
            "intro_text": INTRO_TEXT,
            "outro_text": OUTRO_TEXT,
            "intro_word_count": len(INTRO_TEXT.split()),
            "outro_word_count": len(OUTRO_TEXT.split()),
            "voice_model": "gpt-4o-mini-tts",
            "voice": "cedar",
            "tone": "serious, premium, curious, documentary, not salesy",
            "placement": {
                "intro": "prepend_before_main_narration",
                "outro": "append_after_main_narration"
            }
        },
        "readiness": {
            "intro_ready": True,
            "outro_ready": True,
            "ready_for_voice_generation": True,
            "blocking_notes": []
        },
        "source": {
            "standard_reference": get_relative_path(standard_path),
            "founder_review_reference": get_relative_path(review_path),
            "founder_review_result": review_data.get("review_result"),
            "youtube_url": review_data.get("youtube_url")
        },
        "metadata": {
            "next_agent": "intro_outro_voice_generation"
        }
    }


def print_summary(output: dict) -> None:
    print("Intro Outro Plan Agent completed successfully.")
    print(f"Status: {output['status']}")
    print(f"Intro words: {output['intro_outro']['intro_word_count']}")
    print(f"Outro words: {output['intro_outro']['outro_word_count']}")
    print(f"Next agent: {output['metadata']['next_agent']}")
    print("")
    print("Intro text:")
    print(output["intro_outro"]["intro_text"])
    print("")
    print("Outro text:")
    print(output["intro_outro"]["outro_text"])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create reusable Hiddenova intro/outro plan from founder review."
    )

    parser.add_argument(
        "--channel",
        default=DEFAULT_CHANNEL,
        help="Channel name. Default: hiddenova"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate without saving output."
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    channel = args.channel.lower()

    load_dotenv(PROJECT_ROOT / ".env")

    review_path = get_latest_review_path(channel)
    review_data = load_json(review_path)
    standard_path = get_standard_path()

    final_output = build_output(
        channel=channel,
        review_path=review_path,
        review_data=review_data,
        standard_path=standard_path
    )

    schema = load_schema()
    validate(instance=final_output, schema=schema)

    if args.dry_run:
        print_summary(final_output)
        return

    latest_path = save_output(
        channel=final_output["channel"],
        data=final_output
    )

    print_summary(final_output)
    print(f"Output saved to: {latest_path}")


if __name__ == "__main__":
    main()
