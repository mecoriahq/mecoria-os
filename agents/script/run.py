import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv
from jsonschema import validate
from openai import OpenAI

from prompt import build_prompt
from output import save_output


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.video_run_context import (
    assert_topic_approved,
    load_context,
    register_output,
    resolve_source,
    save_context,
    set_status,
)


from core.content_quality import (
    assert_script_word_count,
)

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
        max_completion_tokens=5000,
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



def get_relative_path(path: Path) -> str:
    return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")


def save_video_specific_output(
    context: dict,
    data: dict
) -> Path:
    output_dir = (
        BASE_DIR
        / "output"
        / context["channel"]
        / context["video_id"]
        / context["run_id"]
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / "script.json"
    output_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=True),
        encoding="utf-8"
    )

    context = register_output(
        context=context,
        agent="script",
        reference=get_relative_path(output_path),
        status="script_ready"
    )
    context = set_status(
        context=context,
        status="script_ready",
        next_agent="seo"
    )
    save_context(context)

    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a script from a locked video run context."
    )

    parser.add_argument(
        "--channel",
        default=DEFAULT_CHANNEL
    )
    parser.add_argument(
        "--video-id",
        default=None
    )
    parser.add_argument(
        "--idea-index",
        type=int,
        default=DEFAULT_IDEA_INDEX
    )
    parser.add_argument(
        "--dry-run",
        action="store_true"
    )

    return parser.parse_args()


def resolve_script_inputs(
    channel: str,
    video_id: str | None,
    idea_index: int
) -> tuple[dict | None, Path, dict, Path | None, dict]:
    if not video_id:
        research_path = get_research_latest_path(channel)
        research_data = load_json(research_path)

        return (
            None,
            research_path,
            research_data,
            None,
            select_idea(research_data, idea_index)
        )

    context = load_context(
        channel=channel,
        video_id=video_id
    )

    assert_topic_approved(context)

    research_path = resolve_source(
        context=context,
        key="research"
    )
    selection_path = resolve_source(
        context=context,
        key="idea_selection"
    )

    research_data = load_json(research_path)
    selection_data = load_json(selection_path)

    for name, data in (
        ("research", research_data),
        ("idea_selection", selection_data)
    ):
        source_video_id = data.get("video_id")
        source_run_id = data.get("run_id")

        if source_video_id and source_video_id != context["video_id"]:
            raise ValueError(f"{name} video_id mismatch.")

        if source_run_id and source_run_id != context["run_id"]:
            raise ValueError(f"{name} run_id mismatch.")

    selected_idea = selection_data.get("selected_idea")

    if not isinstance(selected_idea, dict):
        raise ValueError(
            "Idea Selection output has no selected_idea."
        )

    return (
        context,
        research_path,
        research_data,
        selection_path,
        selected_idea
    )


def main() -> None:
    args = parse_args()
    channel = args.channel.lower()
    video_id = (
        args.video_id.lower()
        if args.video_id
        else None
    )

    load_dotenv(PROJECT_ROOT / ".env")

    (
        context,
        research_path,
        research_data,
        selection_path,
        selected_idea
    ) = resolve_script_inputs(
        channel=channel,
        video_id=video_id,
        idea_index=args.idea_index
    )

    print(f"CHANNEL: {channel}")
    print(f"VIDEO_CONTEXT_ID: {video_id}")
    print(
        "RESEARCH_SOURCE: "
        f"{get_relative_path(research_path)}"
    )
    print(
        "IDEA_SELECTION_SOURCE: "
        f"{get_relative_path(selection_path) if selection_path else 'legacy'}"
    )
    print(f"SELECTED_TOPIC: {selected_idea['title']}")

    if args.dry_run:
        print("STATUS: script_dry_run_ready")
        return

    target_word_min = int(
        context.get(
            "quality_gates",
            {}
        ).get(
            "target_script_word_count_min",
            800
        )
    ) if context else 800

    target_word_max = int(
        context.get(
            "quality_gates",
            {}
        ).get(
            "target_script_word_count_max",
            1300
        )
    ) if context else 1300

    prompt = build_prompt(
        research_data=research_data,
        selected_idea=selected_idea,
        target_word_count_min=target_word_min,
        target_word_count_max=target_word_max
    )

    raw_script_data = generate_script(prompt)

    final_output = normalize_output(
        research_data=research_data,
        selected_idea=selected_idea,
        script_data=raw_script_data
    )

    if context:
        final_output["version"] = "2.0"
        final_output["video_id"] = context["video_id"]
        final_output["run_id"] = context["run_id"]
        final_output["source"]["parent_agent"] = (
            "content_idea_selector"
        )
        final_output["source"]["parent_reference"] = (
            get_relative_path(selection_path)
        )

    word_gate = assert_script_word_count(
        script_data=final_output,
        minimum=target_word_min,
        maximum=target_word_max
    )

    print(
        "SCRIPT_NARRATION_WORD_COUNT: "
        f"{word_gate['word_count']}"
    )
    print(
        "SCRIPT_WORD_GATE: passed"
    )

    schema = load_schema()
    validate(instance=final_output, schema=schema)

    if context:
        output_path = save_video_specific_output(
            context=context,
            data=final_output
        )
    else:
        output_path = save_output(
            channel=research_data["channel"],
            data=final_output
        )

    print("Script Agent completed successfully.")
    print(f"Output saved to: {output_path}")


if __name__ == "__main__":
    main()
