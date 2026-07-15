import argparse
import json
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.video_run_context import save_context


def load_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Required file not found: {path}")

    return json.loads(path.read_text(encoding="utf-8-sig"))


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=True),
        encoding="utf-8"
    )


def relative_path(path: Path) -> str:
    return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")


def validate_video_id(video_id: str) -> str:
    normalized = video_id.lower()

    if not re.fullmatch(r"video_\d{3,}", normalized):
        raise ValueError(
            "video_id must use format video_003."
        )

    return normalized


def get_research_path(
    channel: str,
    video_id: str
) -> Path:
    return (
        PROJECT_ROOT
        / "records"
        / "run_contexts"
        / channel
        / video_id
        / "inputs"
        / "research.json"
    )


def get_selection_path(
    channel: str,
    video_id: str
) -> Path:
    return (
        PROJECT_ROOT
        / "records"
        / "run_contexts"
        / channel
        / video_id
        / "inputs"
        / "idea_selection.json"
    )


def validate_research_identity(
    data: dict,
    channel: str,
    video_id: str,
    run_id: str
) -> None:
    if data.get("agent") != "research":
        raise ValueError("Research source agent mismatch.")

    if data.get("channel") != channel:
        raise ValueError("Research channel mismatch.")

    if data.get("video_id") != video_id:
        raise ValueError("Research video_id mismatch.")

    if data.get("run_id") != run_id:
        raise ValueError("Research run_id mismatch.")

    if len(data.get("ideas", [])) != 10:
        raise ValueError("Research must contain exactly 10 ideas.")


def extract_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}") + 1

        if start < 0 or end <= 0:
            raise ValueError(
                "OpenAI response does not contain valid JSON."
            )

        return json.loads(text[start:end])


def select_with_ai(
    ideas: list[dict],
    model: str
) -> dict:
    client = OpenAI()

    prompt = f"""
You are the Head Content Agent for Hiddenova.

Select the single best idea for the next documentary.

Criteria:
- strong click potential
- international relevance
- visual production feasibility
- evergreen value
- advertiser safety
- documentary depth
- low repetition risk
- fit for a new YouTube channel

IDEAS:
{json.dumps(ideas, indent=2, ensure_ascii=True)}

Return only valid JSON:

{{
  "selected_index": 0,
  "score": 0,
  "reason": "string"
}}

selected_index must be zero-based.
score must be an integer from 0 to 100.
"""

    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ],
        max_completion_tokens=1500,
        response_format={
            "type": "json_object"
        }
    )

    content = response.choices[0].message.content

    if not content:
        raise ValueError("Idea Selector returned an empty response.")

    return extract_json(content)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Select one research idea and create an immutable "
            "video run context."
        )
    )

    parser.add_argument("--channel", default="hiddenova")
    parser.add_argument("--video-id", required=True)
    parser.add_argument("--research-path", default=None)
    parser.add_argument("--selected-index", type=int, default=None)
    parser.add_argument("--model", default="gpt-5.5")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    channel = args.channel.lower()
    video_id = validate_video_id(args.video_id)
    run_id = f"{channel}_{video_id}_v1"

    research_path = (
        PROJECT_ROOT / args.research_path
        if args.research_path
        else get_research_path(channel, video_id)
    )

    research_data = load_json(research_path)

    validate_research_identity(
        data=research_data,
        channel=channel,
        video_id=video_id,
        run_id=run_id
    )

    context_path = (
        PROJECT_ROOT
        / "records"
        / "run_contexts"
        / channel
        / f"{video_id}.json"
    )

    print(f"CHANNEL: {channel}")
    print(f"VIDEO_CONTEXT_ID: {video_id}")
    print(f"RUN_ID: {run_id}")
    print(f"RESEARCH_SOURCE: {relative_path(research_path)}")
    print(f"IDEA_COUNT: {len(research_data['ideas'])}")
    print("LATEST_JSON_INPUTS: blocked")

    if args.dry_run:
        print("STATUS: idea_selector_dry_run_ready")
        return

    if context_path.exists() and not args.force:
        raise FileExistsError(
            f"Run context already exists: {context_path}"
        )

    if args.selected_index is None:
        load_dotenv(PROJECT_ROOT / ".env")

        if not os.getenv("OPENAI_API_KEY"):
            raise ValueError("OpenAI API Key not found.")

        selection = select_with_ai(
            ideas=research_data["ideas"],
            model=args.model
        )
        selected_index = int(
            selection.get("selected_index", -1)
        )
    else:
        selected_index = args.selected_index
        selection = {
            "selected_index": selected_index,
            "score": 100,
            "reason": "Founder-selected idea index."
        }

    if not 0 <= selected_index < len(research_data["ideas"]):
        raise ValueError("Selected idea index is out of range.")

    selected_idea = research_data["ideas"][selected_index]
    selection_path = get_selection_path(channel, video_id)

    selection_output = {
        "agent": "content_idea_selector",
        "version": "1.0",
        "channel": channel,
        "video_id": video_id,
        "run_id": run_id,
        "status": "selected",
        "selected_index": selected_index,
        "selected_idea": selected_idea,
        "score": int(selection.get("score", 0)),
        "reason": str(selection.get("reason", "")).strip(),
        "source": {
            "parent_agent": "research",
            "parent_reference": relative_path(research_path)
        },
        "metadata": {
            "next_agent": "founder_topic_approval"
        }
    }

    save_json(selection_path, selection_output)

    context = {
        "schema_version": "1.0",
        "channel": channel,
        "video_id": video_id,
        "run_id": run_id,
        "status": "topic_approval_required",
        "topic_title": str(selected_idea["title"]).strip(),
        "sources": {
            "research": relative_path(research_path),
            "idea_selection": relative_path(selection_path)
        },
        "outputs": {},
        "quality_gates": {
            "no_latest_json_sources": True,
            "minimum_content_qa_score": 85,
            "target_script_word_count_min": 800,
            "target_script_word_count_max": 1300,
            "require_hiddenova_brand_intro": True,
            "require_standard_cta": True,
            "require_end_screen_area": True,
            "require_ai_visuals": True,
            "minimum_ai_insert_count": 8,
            "require_thumbnail": True,
            "thumbnail_text_min_words": 1,
            "thumbnail_text_max_words": 4,
            "thumbnail_two_color_text": True,
            "require_founder_review": True,
            "require_topic_approval": True
        },
        "next_agent": "founder_topic_approval",
        "release": {
            "topic_approved": False,
            "public_release_approved": False
        },
        "history": [
            {
                "agent": "content_idea_selector",
                "status": "selected",
                "output_reference": relative_path(selection_path)
            }
        ]
    }

    save_context(context)

    print("Content Idea Selector completed successfully.")
    print(f"SELECTED_INDEX: {selected_index}")
    print(f"SELECTED_TOPIC: {context['topic_title']}")
    print(f"CONTEXT_SAVED: {relative_path(context_path)}")


if __name__ == "__main__":
    main()
