import json
from pathlib import Path

from dotenv import load_dotenv
from jsonschema import validate
from openai import OpenAI

from output import save_output
from prompt import build_prompt


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent.parent

DEFAULT_CHANNEL = "hiddenova"


def load_json(file_path: Path) -> dict:
    if not file_path.exists():
        raise FileNotFoundError(f"Required file not found: {file_path}")

    return json.loads(file_path.read_text(encoding="utf-8"))


def load_schema() -> dict:
    return load_json(BASE_DIR / "schema.json")


def get_image_prompt_latest_path(channel: str) -> Path:
    return PROJECT_ROOT / "agents" / "image_prompt" / "output" / channel.lower() / "latest.json"


def get_image_generation_latest_path(channel: str) -> Path:
    return PROJECT_ROOT / "agents" / "image_generation" / "output" / channel.lower() / "latest.json"


def get_image_qa_latest_path(channel: str) -> Path:
    return PROJECT_ROOT / "agents" / "image_qa" / "output" / channel.lower() / "latest.json"


def ensure_image_qa_rejected(image_qa_data: dict) -> None:
    if image_qa_data.get("status") != "rejected":
        raise ValueError("Image QA status is not rejected. Image Revision Agent should not run.")


def extract_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}") + 1

        if start == -1 or end == 0:
            raise ValueError("OpenAI response does not contain valid JSON.")

        return json.loads(text[start:end])


def generate_revision(prompt: str) -> dict:
    client = OpenAI()

    response = client.chat.completions.create(
        model="gpt-5.5",
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ],
        max_completion_tokens=5000,
        response_format={
            "type": "json_object"
        }
    )

    content = response.choices[0].message.content

    if not content:
        raise ValueError("OpenAI returned an empty response.")

    return extract_json(content)


def normalize_output(image_qa_data: dict, revision_data: dict) -> dict:
    return {
        "agent": "image_revision",
        "version": "1.0",
        "channel": image_qa_data["channel"],
        "revision_reason": revision_data["revision_reason"],
        "providers": revision_data["providers"],
        "metadata": {
            "source_agents": [
                "image_prompt",
                "image_generation",
                "image_qa"
            ],
            "next_agent": "image_generation"
        }
    }


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")

    image_prompt_data = load_json(get_image_prompt_latest_path(DEFAULT_CHANNEL))
    image_generation_data = load_json(get_image_generation_latest_path(DEFAULT_CHANNEL))
    image_qa_data = load_json(get_image_qa_latest_path(DEFAULT_CHANNEL))

    ensure_image_qa_rejected(image_qa_data)

    prompt = build_prompt(
        image_prompt_data=image_prompt_data,
        image_generation_data=image_generation_data,
        image_qa_data=image_qa_data
    )

    raw_revision_data = generate_revision(prompt)

    final_output = normalize_output(
        image_qa_data=image_qa_data,
        revision_data=raw_revision_data
    )

    schema = load_schema()
    validate(instance=final_output, schema=schema)

    latest_path = save_output(
        channel=image_qa_data["channel"],
        data=final_output
    )

    print("Image Revision Agent completed successfully.")
    print(f"Output saved to: {latest_path}")


if __name__ == "__main__":
    main()