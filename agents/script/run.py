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
DEFAULT_IDEA_INDEX = 0


def load_json(file_path: Path) -> dict:
    if not file_path.exists():
        raise FileNotFoundError(f"Required file not found: {file_path}")

    return json.loads(file_path.read_text(encoding="utf-8"))


def load_schema() -> dict:
    return load_json(BASE_DIR / "schema.json")


def get_research_latest_path(channel: str) -> Path:
    return PROJECT_ROOT / "agents" / "research" / "output" / channel.lower() / "latest.json"


def select_idea(research_data: dict, idea_index: int = DEFAULT_IDEA_INDEX) -> dict:
    ideas = research_data.get("ideas", [])

    if not ideas:
        raise ValueError("Research output does not contain any ideas.")

    if idea_index >= len(ideas):
        raise IndexError(f"Idea index {idea_index} is out of range.")

    return ideas[idea_index]


def extract_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}") + 1

        if start == -1 or end == 0:
            raise ValueError("OpenAI response does not contain valid JSON.")

        return json.loads(text[start:end])


def generate_script(prompt: str) -> dict:
    client = OpenAI()

    response = client.chat.completions.create(
        model="gpt-5.5",
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ],
        max_completion_tokens=8000,
        response_format={
            "type": "json_object"
        }
    )

    content = response.choices[0].message.content

    if not content:
        raise ValueError("OpenAI returned an empty response.")

    return extract_json(content)


def to_text(value) -> str:
    if value is None:
        return ""

    if isinstance(value, str):
        return value

    if isinstance(value, list):
        return "\n\n".join(str(item) for item in value)

    if isinstance(value, dict):
        if "narration" in value:
            return to_text(value["narration"])
        if "content" in value:
            return to_text(value["content"])
        if "text" in value:
            return to_text(value["text"])

    return str(value)


def get_narration(value) -> dict:
    return {
        "narration": to_text(value)
    }


def normalize_sections(script: dict) -> list:
    raw_sections = script.get("main_sections") or script.get("sections") or []
    normalized_sections = []

    for index, section in enumerate(raw_sections, start=1):
        title = section.get("title") or section.get("heading") or f"Section {index}"
        narration = section.get("narration") or section.get("content") or ""
        visual_direction = section.get("visual_direction") or section.get("visuals") or ""

        normalized_sections.append(
            {
                "title": to_text(title),
                "narration": to_text(narration),
                "visual_direction": to_text(visual_direction)
            }
        )

    return normalized_sections


def normalize_script(script_data: dict) -> dict:
    script = script_data.get("script", script_data)

    return {
        "title": to_text(script.get("title", "Untitled Script")),
        "format": to_text(script.get("format", "Long-form YouTube documentary")),
        "estimated_duration": to_text(
            script.get("estimated_duration")
            or script.get("estimated_runtime")
            or "12-16 minutes"
        ),
        "hook": get_narration(script.get("hook")),
        "introduction": get_narration(script.get("introduction") or script.get("intro")),
        "main_sections": normalize_sections(script),
        "conclusion": get_narration(script.get("conclusion")),
        "call_to_action": get_narration(script.get("call_to_action"))
    }


def normalize_output(research_data: dict, selected_idea: dict, script_data: dict) -> dict:
    return {
        "agent": "script",
        "version": "1.0",
        "channel": research_data["channel"],
        "source": {
            "agent": research_data["agent"],
            "version": research_data["version"],
            "idea_title": selected_idea["title"]
        },
        "script": normalize_script(script_data)
    }


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")

    research_path = get_research_latest_path(DEFAULT_CHANNEL)
    research_data = load_json(research_path)

    selected_idea = select_idea(research_data)

    prompt = build_prompt(
        research_data=research_data,
        selected_idea=selected_idea
    )

    raw_script_data = generate_script(prompt)

    final_output = normalize_output(
        research_data=research_data,
        selected_idea=selected_idea,
        script_data=raw_script_data
    )

    schema = load_schema()
    validate(instance=final_output, schema=schema)

    latest_path = save_output(
        channel=research_data["channel"],
        data=final_output
    )

    print("Script Agent completed successfully.")
    print(f"Output saved to: {latest_path}")


if __name__ == "__main__":
    main()