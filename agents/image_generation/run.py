import argparse
import json
from pathlib import Path

from dotenv import load_dotenv
from jsonschema import validate

from output import save_image, save_output
from provider import generate_openai_image


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent.parent

DEFAULT_CHANNEL = "hiddenova"
DEFAULT_PROVIDER = "openai"
DEFAULT_SOURCE = "prompt"


def load_json(file_path: Path) -> dict:
    if not file_path.exists():
        raise FileNotFoundError(f"Required file not found: {file_path}")

    return json.loads(file_path.read_text(encoding="utf-8"))


def load_schema() -> dict:
    return load_json(BASE_DIR / "schema.json")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Mecoria Image Generation Agent."
    )

    parser.add_argument(
        "--channel",
        default=DEFAULT_CHANNEL,
        help="Channel name. Default: hiddenova"
    )

    parser.add_argument(
        "--provider",
        default=DEFAULT_PROVIDER,
        choices=["openai"],
        help="Image generation provider. Default: openai"
    )

    parser.add_argument(
        "--source",
        default=DEFAULT_SOURCE,
        choices=["prompt", "revision"],
        help="Prompt source. Use 'prompt' for Image Prompt output or 'revision' for Image Revision output."
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate source selection without generating an image."
    )

    return parser.parse_args()


def get_image_prompt_latest_path(channel: str) -> Path:
    return PROJECT_ROOT / "agents" / "image_prompt" / "output" / channel.lower() / "latest.json"


def get_image_revision_latest_path(channel: str) -> Path:
    return PROJECT_ROOT / "agents" / "image_revision" / "output" / channel.lower() / "latest.json"


def get_prompt_source_path(channel: str, source: str) -> Path:
    if source == "prompt":
        return get_image_prompt_latest_path(channel)

    if source == "revision":
        return get_image_revision_latest_path(channel)

    raise ValueError(f"Unsupported prompt source: {source}")


def get_expected_source_agent(source: str) -> str:
    if source == "prompt":
        return "image_prompt"

    if source == "revision":
        return "image_revision"

    raise ValueError(f"Unsupported prompt source: {source}")


def validate_prompt_source(prompt_source_data: dict, source: str) -> None:
    expected_agent = get_expected_source_agent(source)
    actual_agent = prompt_source_data.get("agent")

    if actual_agent != expected_agent:
        raise ValueError(
            f"Invalid prompt source. Expected agent '{expected_agent}', got '{actual_agent}'."
        )


def get_prompt_source_type(prompt_source_data: dict) -> str:
    return prompt_source_data["agent"]


def normalize_output(prompt_source_data: dict, image_path: Path, provider: str) -> dict:
    prompt_data = prompt_source_data["providers"][provider]
    relative_path = image_path.relative_to(PROJECT_ROOT)

    return {
        "agent": "image_generation",
        "version": "1.0",
        "channel": prompt_source_data["channel"],
        "provider": provider,
        "model": prompt_data["model"],
        "image": {
            "filename": image_path.name,
            "relative_path": str(relative_path).replace("\\", "/"),
            "format": "png",
            "size": prompt_data["size"]
        },
        "source": {
            "agent": get_prompt_source_type(prompt_source_data),
            "provider": provider
        },
        "metadata": {
            "source_agents": [
                get_prompt_source_type(prompt_source_data)
            ],
            "next_agent": "publisher"
        }
    }


def print_dry_run_summary(prompt_source_path: Path, prompt_source_data: dict, provider: str) -> None:
    prompt_data = prompt_source_data["providers"][provider]

    print("Image Generation Agent dry-run completed.")
    print(f"Prompt source: {prompt_source_path}")
    print(f"Source agent: {prompt_source_data['agent']}")
    print(f"Provider: {provider}")
    print(f"Model: {prompt_data['model']}")
    print(f"Size: {prompt_data['size']}")


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")

    args = parse_args()

    prompt_source_path = get_prompt_source_path(
        channel=args.channel,
        source=args.source
    )

    prompt_source_data = load_json(prompt_source_path)

    validate_prompt_source(
        prompt_source_data=prompt_source_data,
        source=args.source
    )

    if args.dry_run:
        print_dry_run_summary(
            prompt_source_path=prompt_source_path,
            prompt_source_data=prompt_source_data,
            provider=args.provider
        )
        return

    prompt_data = prompt_source_data["providers"][args.provider]

    image_bytes = generate_openai_image(prompt_data)

    image_path = save_image(
        channel=prompt_source_data["channel"],
        image_bytes=image_bytes,
        extension="png"
    )

    final_output = normalize_output(
        prompt_source_data=prompt_source_data,
        image_path=image_path,
        provider=args.provider
    )

    schema = load_schema()
    validate(instance=final_output, schema=schema)

    latest_path = save_output(
        channel=prompt_source_data["channel"],
        data=final_output
    )

    print("Image Generation Agent completed successfully.")
    print(f"Prompt source: {prompt_source_path}")
    print(f"Image saved to: {image_path}")
    print(f"Metadata saved to: {latest_path}")


if __name__ == "__main__":
    main()