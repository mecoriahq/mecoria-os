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

from core.channel_content_policy import (
    build_quality_gates,
    load_editorial_profile,
)
from core.topic_novelty import (
    load_historical_topics,
    resolve_selected_index,
    validate_novelty_analysis,
)
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
    historical_topics: list[dict],
    model: str,
    editorial_profile: dict,
) -> dict:
    client = OpenAI()

    topic_strategy = editorial_profile["topic_strategy"]

    prompt = f"""
You are the Topic Novelty Gate and Head Content Agent
for {editorial_profile["display_name"]}.

Evaluate every proposed idea before selecting the next
documentary topic.

CHANNEL PROMISE:
{topic_strategy["channel_promise"]}

ALLOWED PILLARS:
{json.dumps(topic_strategy["allowed_pillars"], indent=2)}

SELECTION RULES:
{json.dumps(topic_strategy["selection_rules"], indent=2)}

FORBIDDEN ANGLES:
{json.dumps(topic_strategy["forbidden_angles"], indent=2)}

A topic is a duplicate when it delivers substantially
the same subject, central question, turning point,
viewer promise, or narrative journey as an existing
video. Different wording is not enough.

EXISTING CHANNEL VIDEOS:
{json.dumps(historical_topics, indent=2, ensure_ascii=True)}

NEW RESEARCH IDEAS:
{json.dumps(ideas, indent=2, ensure_ascii=True)}

Evaluate all ideas. Reject thematic and semantic
duplicates. Select the strongest genuinely new idea
that matches the channel promise and source requirements.

Return only valid JSON with exactly this structure:

{{
  "evaluations": [
    {{
      "index": 0,
      "duplicate": false,
      "closest_video_id": null,
      "novelty_score": 0,
      "content_score": 0,
      "reason": "string"
    }}
  ],
  "selected_index": 0,
  "score": 0,
  "reason": "string"
}}

Rules:
- Include exactly one evaluation for every idea.
- index must be zero-based.
- duplicate must be a JSON boolean.
- novelty_score and content_score must be 0 to 100.
- selected_index must reference an idea where
  duplicate is false.
- Do not select a renamed, narrowed, broadened, or
  synonym-based version of an existing video.
- Prefer international relevance, click potential,
  evergreen value, visual feasibility, advertiser
  safety, documentary depth, and source feasibility.
- Reject unsupported conspiracy, private-life speculation,
  fictionalized stories, and low-evidence scandal angles.
"""

    response = client.chat.completions.create(
        model=model,
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
        raise ValueError(
            "Idea Selector returned an empty response."
        )

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

    load_dotenv(PROJECT_ROOT / ".env")

    if not os.getenv("OPENAI_API_KEY"):
        raise ValueError("OpenAI API Key not found.")

    editorial_profile = load_editorial_profile(channel)

    historical_topics = load_historical_topics(
        project_root=PROJECT_ROOT,
        channel=channel,
        exclude_video_id=video_id
    )

    raw_analysis = select_with_ai(
        ideas=research_data["ideas"],
        historical_topics=historical_topics,
        model=args.model,
        editorial_profile=editorial_profile,
    )

    novelty_analysis = validate_novelty_analysis(
        analysis=raw_analysis,
        idea_count=len(research_data["ideas"])
    )

    selected_index = resolve_selected_index(
        analysis=novelty_analysis,
        requested_index=args.selected_index,
        idea_count=len(research_data["ideas"])
    )

    selected_evaluation = next(
        item
        for item in novelty_analysis["evaluations"]
        if item["index"] == selected_index
    )

    duplicate_indices = [
        item["index"]
        for item in novelty_analysis["evaluations"]
        if item["duplicate"]
    ]

    selection = {
        "selected_index": selected_index,
        "score": (
            100
            if args.selected_index is not None
            else novelty_analysis["score"]
        ),
        "reason": (
            "Founder-selected idea passed the "
            "topic novelty gate. "
            + selected_evaluation["reason"]
            if args.selected_index is not None
            else novelty_analysis["reason"]
        ),
        "novelty_score": selected_evaluation[
            "novelty_score"
        ],
        "content_score": selected_evaluation[
            "content_score"
        ],
        "closest_video_id": selected_evaluation[
            "closest_video_id"
        ],
        "duplicate_indices": duplicate_indices,
        "historical_topic_count": len(
            historical_topics
        ),
        "novelty_evaluations": novelty_analysis[
            "evaluations"
        ]
    }

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
        "novelty_status": "approved",
        "novelty_score": selection["novelty_score"],
        "content_score": selection["content_score"],
        "closest_video_id": selection["closest_video_id"],
        "duplicate_indices": selection["duplicate_indices"],
        "historical_topic_count": selection[
            "historical_topic_count"
        ],
        "novelty_evaluations": selection[
            "novelty_evaluations"
        ],
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
            "minimum_content_qa_score": int(
                editorial_profile["qa"][
                    "minimum_overall_score"
                ]
            ),
            **build_quality_gates(editorial_profile),
            "require_actual_chapters": True,
            "chapter_timing_source": "actual_audio_sections",
            "max_audio_duration_revision_attempts": 2,
            "require_standard_cta": True,
            "require_end_screen_area": True,
            "require_ai_visuals": True,
            "minimum_ai_insert_count": 8,
            "require_thumbnail": True,
            "thumbnail_text_min_words": 2,
            "thumbnail_text_max_words": 4,
            "thumbnail_two_color_text": True,
            "require_founder_review": True,
            "require_topic_approval": True,
            "require_topic_novelty": True,
            "allow_topic_reuse": False
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
    print(
        "HISTORICAL_TOPIC_COUNT: "
        f"{selection['historical_topic_count']}"
    )
    print(
        "DUPLICATE_IDEA_INDEXES: "
        f"{selection['duplicate_indices']}"
    )
    print(f"SELECTED_INDEX: {selected_index}")
    print(f"SELECTED_TOPIC: {context['topic_title']}")
    print(
        "TOPIC_NOVELTY_SCORE: "
        f"{selection['novelty_score']}"
    )
    print(f"CONTEXT_SAVED: {relative_path(context_path)}")


if __name__ == "__main__":
    main()
