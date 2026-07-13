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

    return json.loads(file_path.read_text(encoding="utf-8-sig"))


def load_schema() -> dict:
    return load_json(BASE_DIR / "schema.json")


def get_visual_brief_latest_path(channel: str) -> Path:
    return PROJECT_ROOT / "agents" / "visual_brief" / "output" / channel.lower() / "latest.json"


def get_qa_latest_path(channel: str) -> Path:
    return PROJECT_ROOT / "agents" / "qa" / "output" / channel.lower() / "latest.json"


def get_thumbnail_rules_path(channel: str) -> Path:
    return PROJECT_ROOT / "config" / "thumbnail_rules" / f"{channel.lower()}.json"


def get_relative_path(path: Path) -> str:
    return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")


def ensure_qa_approved(qa_data: dict) -> None:
    if qa_data.get("status") != "approved":
        raise ValueError("QA status is not approved. Image Prompt Agent cannot continue.")


def extract_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}") + 1

        if start == -1 or end == 0:
            raise ValueError("OpenAI response does not contain valid JSON.")

        return json.loads(text[start:end])


def generate_image_prompts(prompt: str) -> dict:
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


def remove_old_no_text_language(text: str) -> str:
    replacements = [
        "but do not add any text",
        "do not add any text",
        "no text overlay",
        "without text",
        "text_absence"
    ]

    cleaned = text

    for phrase in replacements:
        cleaned = cleaned.replace(phrase, "")

    return cleaned.strip()


def build_thumbnail_text_instruction(thumbnail_rules_data: dict) -> str:
    standard = thumbnail_rules_data["thumbnail_standard"]
    text_rules = standard["text_rules"]
    approved_patterns = standard["approved_patterns"]

    pattern_text = ", ".join(approved_patterns)

    return (
        "THUMBNAIL TEXT OVERLAY REQUIREMENT: "
        "Include one short English thumbnail text hook directly inside the image. "
        f"Use {text_rules['min_words']} to {text_rules['max_words']} words, "
        f"prefer around {text_rules['preferred_word_count']} words. "
        "The text must be large, bold, high-contrast, cinematic, and readable on mobile. "
        "Place the text in clean negative space without covering the main subject. "
        "Keep text inside the 16:9 center-crop safe area; avoid top and bottom edges. "
        "The text should create curiosity and must not repeat the full title. "
        f"Suggested text hook patterns: {pattern_text}. "
        "Only the thumbnail hook text may be readable; do not include readable labels, logos, addresses, barcodes, UI, or private information."
    )


def apply_thumbnail_rules_to_provider_prompts(prompt_data: dict, thumbnail_rules_data: dict) -> dict:
    updated = json.loads(json.dumps(prompt_data))
    instruction = build_thumbnail_text_instruction(thumbnail_rules_data)

    if "openai" in updated:
        updated["openai"]["prompt"] = (
            remove_old_no_text_language(updated["openai"]["prompt"])
            + "\n\n"
            + instruction
        )

    if "flux" in updated:
        updated["flux"]["prompt"] = (
            remove_old_no_text_language(updated["flux"]["prompt"])
            + "\n\n"
            + instruction
        )

        if "negative_prompt" in updated["flux"]:
            negative_prompt = remove_old_no_text_language(updated["flux"]["negative_prompt"])
            updated["flux"]["negative_prompt"] = (
                negative_prompt
                + ", long text, tiny text, low contrast text, unreadable text, cluttered text, text covering subject"
            )

    if "midjourney" in updated:
        updated["midjourney"]["prompt"] = (
            remove_old_no_text_language(updated["midjourney"]["prompt"])
            + ", short bold high-contrast English thumbnail text hook, readable on mobile, placed in negative space, inside 16:9 safe area, no extra readable labels or logos"
        )

    return updated


def normalize_output(
    visual_brief_data: dict,
    prompt_data: dict,
    thumbnail_rules_data: dict,
    thumbnail_rules_path: Path
) -> dict:
    standard = thumbnail_rules_data["thumbnail_standard"]

    return {
        "agent": "image_prompt",
        "version": "1.1",
        "channel": visual_brief_data["channel"],
        "providers": prompt_data,
        "metadata": {
            "source_agents": [
                "visual_brief",
                "thumbnail_rules"
            ],
            "thumbnail_rules_reference": get_relative_path(thumbnail_rules_path),
            "thumbnail_text_overlay_required": standard["text_overlay_required"],
            "thumbnail_text_max_words": standard["text_rules"]["max_words"],
            "thumbnail_text_patterns": standard["approved_patterns"],
            "next_agent": "image_generation"
        }
    }


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")

    visual_brief_path = get_visual_brief_latest_path(DEFAULT_CHANNEL)
    qa_path = get_qa_latest_path(DEFAULT_CHANNEL)
    thumbnail_rules_path = get_thumbnail_rules_path(DEFAULT_CHANNEL)

    visual_brief_data = load_json(visual_brief_path)
    qa_data = load_json(qa_path)
    thumbnail_rules_data = load_json(thumbnail_rules_path)

    ensure_qa_approved(qa_data)

    prompt = build_prompt(
        visual_brief_data=visual_brief_data,
        qa_data=qa_data
    )

    raw_prompt_data = generate_image_prompts(prompt)

    prompt_data = apply_thumbnail_rules_to_provider_prompts(
        prompt_data=raw_prompt_data,
        thumbnail_rules_data=thumbnail_rules_data
    )

    final_output = normalize_output(
        visual_brief_data=visual_brief_data,
        prompt_data=prompt_data,
        thumbnail_rules_data=thumbnail_rules_data,
        thumbnail_rules_path=thumbnail_rules_path
    )

    schema = load_schema()
    validate(instance=final_output, schema=schema)

    latest_path = save_output(
        channel=visual_brief_data["channel"],
        data=final_output
    )

    print("Image Prompt Agent completed successfully.")
    print(f"Output saved to: {latest_path}")


if __name__ == "__main__":
    main()
