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


def extract_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}") + 1

        if start == -1 or end == 0:
            raise ValueError("OpenAI response does not contain valid JSON.")

        return json.loads(text[start:end])


def generate_seo(prompt: str) -> dict:
    client = OpenAI()

    response = client.chat.completions.create(
        model="gpt-5.5",
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ],
        max_completion_tokens=4000,
        response_format={
            "type": "json_object"
        }
    )

    content = response.choices[0].message.content

    if not content:
        raise ValueError("OpenAI returned an empty response.")

    return extract_json(content)


def normalize_output(script_data: dict, seo_data: dict) -> dict:
    script = script_data["script"]

    return {
        "agent": "seo",
        "version": "1.0",
        "channel": script_data["channel"],
        "platform": "youtube",
        "source": {
            "agent": script_data["agent"],
            "version": script_data["version"],
            "script_title": script["title"]
        },
        "seo": seo_data
    }


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")

    script_path = get_script_latest_path(DEFAULT_CHANNEL)
    script_data = load_json(script_path)

    prompt = build_prompt(script_data=script_data)

    raw_seo_data = generate_seo(prompt)

    final_output = normalize_output(
        script_data=script_data,
        seo_data=raw_seo_data
    )

    schema = load_schema()
    validate(instance=final_output, schema=schema)

    latest_path = save_output(
        channel=script_data["channel"],
        data=final_output
    )

    print("SEO Agent completed successfully.")
    print(f"Output saved to: {latest_path}")


if __name__ == "__main__":
    main()