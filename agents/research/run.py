import argparse
import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from prompt import build_research_prompt
from output import build_output


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent.parent

DEFAULT_CHANNEL_NAME = "hiddenova"
DEFAULT_CHANNEL_DESCRIPTION = (
    "Hiddenova is an English documentary-style YouTube channel about "
    "the hidden systems, unseen infrastructure, logistics, technology, "
    "business operations, and invisible networks that quietly keep modern life running."
)


def load_file(filename: str) -> str:
    return (BASE_DIR / filename).read_text(encoding="utf-8-sig")


def validate_video_id(video_id: str) -> str:
    normalized = video_id.lower()

    if not re.fullmatch(r"video_\d{3,}", normalized):
        raise ValueError(
            "video_id must use format video_003."
        )

    return normalized


def get_context_research_path(
    channel: str,
    video_id: str
) -> Path:
    return (
        PROJECT_ROOT
        / "records"
        / "run_contexts"
        / channel.lower()
        / video_id
        / "inputs"
        / "research.json"
    )


def resolve_output_path(
    channel: str,
    video_id: str,
    output_path: str | None
) -> Path:
    if output_path:
        path = Path(output_path)

        if not path.is_absolute():
            path = PROJECT_ROOT / path

        return path

    return get_context_research_path(
        channel=channel,
        video_id=video_id
    )


def parse_research_output(
    channel: str,
    video_id: str,
    response_text: str
) -> dict:
    raw = json.loads(response_text)
    ideas = raw.get("ideas", [])

    if len(ideas) != 10:
        raise ValueError(
            f"Research must return exactly 10 ideas. Got {len(ideas)}."
        )

    required_fields = {
        "id",
        "title",
        "summary",
        "target_audience",
        "potential",
        "difficulty"
    }

    titles = []

    for index, idea in enumerate(ideas, start=1):
        missing = required_fields - set(idea)

        if missing:
            raise ValueError(
                f"Research idea {index} is missing fields: "
                f"{sorted(missing)}"
            )

        title = str(idea["title"]).strip()

        if not title:
            raise ValueError(
                f"Research idea {index} has an empty title."
            )

        titles.append(title.lower())

    if len(set(titles)) != len(titles):
        raise ValueError("Research returned duplicate idea titles.")

    return {
        "agent": "research",
        "version": "2.0",
        "channel": channel,
        "video_id": video_id,
        "run_id": f"{channel}_{video_id}_v1",
        "status": "research_ready",
        "ideas": ideas,
        "metadata": {
            "next_agent": "content_idea_selector"
        }
    }


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=True),
        encoding="utf-8"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Mecoria Research Agent."
    )

    parser.add_argument(
        "--channel",
        default=DEFAULT_CHANNEL_NAME
    )
    parser.add_argument(
        "--description",
        default=DEFAULT_CHANNEL_DESCRIPTION
    )
    parser.add_argument(
        "--video-id",
        default=None
    )
    parser.add_argument(
        "--output-path",
        default=None
    )
    parser.add_argument(
        "--interactive",
        action="store_true"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true"
    )

    return parser.parse_args()


def resolve_channel_input(
    args: argparse.Namespace
) -> tuple[str, str]:
    if args.interactive:
        return (
            input("Channel Name: "),
            input("Channel Description: ")
        )

    return args.channel, args.description


def main() -> None:
    args = parse_args()
    channel_name, channel_description = resolve_channel_input(
        args
    )
    channel_name = channel_name.lower()

    video_id = (
        validate_video_id(args.video_id)
        if args.video_id
        else None
    )

    output_path = (
        resolve_output_path(
            channel=channel_name,
            video_id=video_id,
            output_path=args.output_path
        )
        if video_id
        else None
    )

    print(f"CHANNEL: {channel_name}")
    print(f"VIDEO_CONTEXT_ID: {video_id}")
    print(
        "OUTPUT_PATH: "
        f"{output_path.relative_to(PROJECT_ROOT) if output_path else 'legacy'}"
    )

    if args.dry_run:
        print("STATUS: research_dry_run_ready")
        return

    load_dotenv(PROJECT_ROOT / ".env")

    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        raise ValueError("OpenAI API Key not found.")

    client = OpenAI(api_key=api_key)
    system_prompt = load_file("system.md")
    workflow = load_file("workflow.md")

    user_prompt = build_research_prompt(
        channel_name=channel_name,
        channel_description=channel_description
    )

    response = client.responses.create(
        model="gpt-5.5",
        instructions=system_prompt + "\n\n" + workflow,
        input=user_prompt
    )

    if video_id:
        result = parse_research_output(
            channel=channel_name,
            video_id=video_id,
            response_text=response.output_text
        )
        save_json(output_path, result)

        print("Research Agent completed successfully.")
        print(f"Output saved to: {output_path}")
        return

    result = build_output(
        channel_name=channel_name,
        response_text=response.output_text
    )

    print(result)


if __name__ == "__main__":
    main()
