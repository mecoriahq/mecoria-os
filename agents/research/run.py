import argparse
import os
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
    return (BASE_DIR / filename).read_text(encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Mecoria Research Agent."
    )

    parser.add_argument(
        "--channel",
        default=DEFAULT_CHANNEL_NAME,
        help="Channel name. Default: hiddenova"
    )

    parser.add_argument(
        "--description",
        default=DEFAULT_CHANNEL_DESCRIPTION,
        help="Channel description."
    )

    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Ask for channel name and description in the terminal."
    )

    return parser.parse_args()


def resolve_channel_input(args: argparse.Namespace) -> tuple[str, str]:
    if args.interactive:
        channel_name = input("Channel Name: ")
        channel_description = input("Channel Description: ")
        return channel_name, channel_description

    return args.channel, args.description


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")

    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        raise ValueError("OpenAI API Key not found.")

    args = parse_args()
    channel_name, channel_description = resolve_channel_input(args)

    client = OpenAI(api_key=api_key)

    system_prompt = load_file("system.md")
    workflow = load_file("workflow.md")

    user_prompt = build_research_prompt(
        channel_name=channel_name,
        channel_description=channel_description,
    )

    response = client.responses.create(
        model="gpt-5.5",
        instructions=system_prompt + "\n\n" + workflow,
        input=user_prompt,
    )

    ideas = response.output_text

    result = build_output(
        channel_name=channel_name,
        response_text=ideas,
    )

    print(result)


if __name__ == "__main__":
    main()