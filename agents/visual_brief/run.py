import json
from pathlib import Path

from dotenv import load_dotenv
from jsonschema import validate
from openai import OpenAI

from prompt import build_prompt
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


def get_seo_latest_path(channel: str) -> Path:
    return PROJECT_ROOT / "agents" / "seo" / "output" / channel.lower() / "latest.json"


def get_qa_latest_path(channel: str) -> Path:
    return PROJECT_ROOT / "agents" / "qa" / "output" / channel.lower() / "latest.json"


def ensure_qa_approved(qa_data: dict) -> None:
    if qa_data.get("status") != "approved":
        raise ValueError("QA status is not approved. Visual Brief Agent cannot continue.")


def extract_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}") + 1

        if start == -1 or end == 0:
            raise ValueError("OpenAI response does not contain valid JSON.")

        return json.loads(text[start:end])


def generate_visual_brief(prompt: str) -> dict:
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


def normalize_output(script_data: dict, visual_brief_data: dict) -> dict:
    return {
        "agent": "visual_brief",
        "version": "1.0",
        "channel": script_data["channel"],
        "visual_brief": visual_brief_data,
        "metadata": {
            "source_agents": [
                "script",
                "seo",
                "qa"
            ],
            "next_agent": "image_prompt"
        }
    }


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")

    script_path = get_script_latest_path(DEFAULT_CHANNEL)
    seo_path = get_seo_latest_path(DEFAULT_CHANNEL)
    qa_path = get_qa_latest_path(DEFAULT_CHANNEL)

    script_data = load_json(script_path)
    seo_data = load_json(seo_path)
    qa_data = load_json(qa_path)

    ensure_qa_approved(qa_data)

    prompt = build_prompt(
        script_data=script_data,
        seo_data=seo_data,
        qa_data=qa_data
    )

    raw_visual_brief_data = generate_visual_brief(prompt)

    final_output = normalize_output(
        script_data=script_data,
        visual_brief_data=raw_visual_brief_data
    )

    schema = load_schema()
    validate(instance=final_output, schema=schema)

    latest_path = save_output(
        channel=script_data["channel"],
        data=final_output
    )

    print("Visual Brief Agent completed successfully.")
    print(f"Output saved to: {latest_path}")


if __name__ == "__main__":
    main()