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

from core.channel_content_policy import (
    factual_pipeline_required,
    load_editorial_profile,
)
from core.video_run_context import (
    assert_topic_approved,
    load_context,
    register_output,
    resolve_output,
    resolve_source,
    save_context,
    set_status,
)


from core.content_quality import (
    DEFAULT_SCRIPT_WORD_MAX,
    DEFAULT_SCRIPT_WORD_MIN,
    assert_script_word_count,
    evaluate_script_word_count,
)
from core.script_revision import (
    build_word_count_revision_feedback,
)
from core.script_preflight import (
    assert_script_preflight,
    evaluate_script_preflight,
)

DEFAULT_CHANNEL = "hiddenova"
DEFAULT_IDEA_INDEX = 0
DEFAULT_WORD_COUNT_REVISION_ATTEMPTS = 2


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


def normalize_claim_ids(value) -> list[str]:
    if not isinstance(value, dict):
        return []

    raw = value.get("claim_ids", [])

    if not isinstance(raw, list):
        return []

    return list(dict.fromkeys(
        str(item).strip()
        for item in raw
        if str(item).strip()
    ))


def get_narration(
    value,
    require_claim_ids: bool = False
) -> dict:
    result = {
        "narration": to_text(value)
    }

    if require_claim_ids:
        result["claim_ids"] = normalize_claim_ids(value)

    return result


def normalize_sections(
    script: dict,
    require_claim_ids: bool = False
) -> list:
    raw_sections = (
        script.get("main_sections")
        or script.get("sections")
        or []
    )
    normalized_sections = []

    for index, section in enumerate(raw_sections, start=1):
        title = (
            section.get("title")
            or section.get("heading")
            or f"Section {index}"
        )
        narration = (
            section.get("narration")
            or section.get("content")
            or ""
        )
        visual_direction = (
            section.get("visual_direction")
            or section.get("visuals")
            or ""
        )
        normalized = {
            "title": to_text(title),
            "narration": to_text(narration),
            "visual_direction": to_text(visual_direction)
        }

        if require_claim_ids:
            normalized["claim_ids"] = normalize_claim_ids(
                section
            )

        normalized_sections.append(normalized)

    return normalized_sections


def normalize_script(
    script_data: dict,
    estimated_duration_label: str = "8-12 minutes",
    require_claim_ids: bool = False,
) -> dict:
    script = script_data.get("script", script_data)

    return {
        "title": to_text(script.get("title", "Untitled Script")),
        "format": to_text(
            script.get(
                "format",
                "Long-form YouTube documentary"
            )
        ),
        "estimated_duration": estimated_duration_label,
        "hook": get_narration(
            script.get("hook"),
            require_claim_ids=require_claim_ids,
        ),
        "introduction": get_narration(
            script.get("introduction")
            or script.get("intro"),
            require_claim_ids=require_claim_ids,
        ),
        "main_sections": normalize_sections(
            script,
            require_claim_ids=require_claim_ids,
        ),
        "conclusion": get_narration(
            script.get("conclusion"),
            require_claim_ids=require_claim_ids,
        ),
        "call_to_action": get_narration(
            script.get("call_to_action"),
            require_claim_ids=require_claim_ids,
        )
    }


def normalize_output(
    research_data: dict,
    selected_idea: dict,
    script_data: dict,
    editorial_profile: dict | None = None,
) -> dict:
    profile = editorial_profile or {
        "script": {
            "estimated_duration_label": "8-12 minutes"
        },
        "factuality": {
            "pipeline_required": False
        },
    }
    factual_required = factual_pipeline_required(profile)

    return {
        "agent": "script",
        "version": "1.0",
        "channel": research_data["channel"],
        "source": {
            "agent": research_data["agent"],
            "version": research_data["version"],
            "idea_title": selected_idea["title"]
        },
        "script": normalize_script(
            script_data,
            estimated_duration_label=(
                profile["script"][
                    "estimated_duration_label"
                ]
            ),
            require_claim_ids=factual_required,
        )
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


def load_revision_feedback(
    context: dict | None
) -> tuple[dict | None, Path | None]:
    if not context:
        return None, None

    reference = context.get(
        "sources",
        {}
    ).get("editorial_revision_brief")

    if not reference:
        return None, None

    path = resolve_source(
        context=context,
        key="editorial_revision_brief"
    )
    data = load_json(path)

    if data.get("video_id") != context["video_id"]:
        raise ValueError(
            "Editorial revision brief video_id mismatch."
        )

    if data.get("run_id") != context["run_id"]:
        raise ValueError(
            "Editorial revision brief run_id mismatch."
        )

    return data, path


def load_factual_inputs(
    context: dict | None,
    editorial_profile: dict,
) -> tuple[dict | None, dict | None, Path | None, Path | None]:
    if not context or not factual_pipeline_required(
        editorial_profile
    ):
        return None, None, None, None

    research_path = resolve_output(
        context=context,
        key="factual_research",
    )
    ledger_path = resolve_output(
        context=context,
        key="claims_ledger",
    )
    factual_research = load_json(research_path)
    claims_ledger = load_json(ledger_path)

    if factual_research.get("status") != "approved":
        raise ValueError(
            "Factual research must be approved before script."
        )

    if claims_ledger.get("status") != "approved":
        raise ValueError(
            "Claims ledger must be approved before script."
        )

    return (
        factual_research,
        claims_ledger,
        research_path,
        ledger_path,
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

    editorial_profile = load_editorial_profile(channel)
    (
        factual_research,
        claims_ledger,
        factual_research_path,
        claims_ledger_path,
    ) = load_factual_inputs(
        context=context,
        editorial_profile=editorial_profile,
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
    print(
        "EDITORIAL_STANDARD: "
        f"{editorial_profile['profile_name']}"
    )
    print(
        "FACTUAL_PIPELINE_REQUIRED: "
        f"{str(factual_pipeline_required(editorial_profile)).lower()}"
    )

    if factual_research_path:
        print(
            "FACTUAL_RESEARCH_SOURCE: "
            f"{get_relative_path(factual_research_path)}"
        )
        print(
            "CLAIMS_LEDGER_SOURCE: "
            f"{get_relative_path(claims_ledger_path)}"
        )

    if args.dry_run:
        print("STATUS: script_dry_run_ready")
        return

    target_word_min = int(
        context.get(
            "quality_gates",
            {}
        ).get(
            "target_script_word_count_min",
            DEFAULT_SCRIPT_WORD_MIN
        )
    ) if context else DEFAULT_SCRIPT_WORD_MIN

    target_word_max = int(
        context.get(
            "quality_gates",
            {}
        ).get(
            "target_script_word_count_max",
            DEFAULT_SCRIPT_WORD_MAX
        )
    ) if context else DEFAULT_SCRIPT_WORD_MAX

    script_policy = editorial_profile.get(
        "script",
        {},
    )
    max_word_count_revision_attempts = int(
        script_policy.get(
            "word_count_revision_attempts",
            DEFAULT_WORD_COUNT_REVISION_ATTEMPTS,
        )
    )
    pre_audio_word_floor = int(
        script_policy.get(
            "pre_audio_word_floor",
            1100,
        )
    )
    pre_audio_minimum_ratio = float(
        script_policy.get(
            "pre_audio_minimum_ratio",
            0.85,
        )
    )
    audio_duration_authoritative = bool(
        script_policy.get(
            "audio_duration_authoritative",
            False,
        )
    )

    if max_word_count_revision_attempts < 0:
        raise ValueError(
            "word_count_revision_attempts cannot be negative."
        )

    (
        revision_feedback,
        revision_feedback_path
    ) = load_revision_feedback(context)

    if revision_feedback_path:
        print(
            "EDITORIAL_REVISION_SOURCE: "
            f"{get_relative_path(revision_feedback_path)}"
        )
        print(
            "EDITORIAL_REVISION_ATTEMPT: "
            f"{revision_feedback.get('attempt')}"
        )

    active_revision_feedback = revision_feedback
    final_output = None
    word_gate = None
    preflight_gate = None
    word_count_revision_attempts = 0

    for generation_attempt in range(
        max_word_count_revision_attempts + 1
    ):
        prompt = build_prompt(
            research_data=research_data,
            selected_idea=selected_idea,
            target_word_count_min=target_word_min,
            target_word_count_max=target_word_max,
            revision_feedback=active_revision_feedback,
            editorial_profile=editorial_profile,
            factual_research=factual_research,
            claims_ledger=claims_ledger,
        )

        raw_script_data = generate_script(prompt)

        candidate_output = normalize_output(
            research_data=research_data,
            selected_idea=selected_idea,
            script_data=raw_script_data,
            editorial_profile=editorial_profile,
        )

        if context:
            candidate_output["version"] = "2.0"
            candidate_output["video_id"] = context["video_id"]
            candidate_output["run_id"] = context["run_id"]
            candidate_output["source"]["parent_agent"] = (
                "content_idea_selector"
            )
            candidate_output["source"]["parent_reference"] = (
                get_relative_path(selection_path)
            )

        candidate_gate = evaluate_script_word_count(
            script_data=candidate_output,
            minimum=target_word_min,
            maximum=target_word_max,
        )

        print(
            "SCRIPT_GENERATION_ATTEMPT: "
            f"{generation_attempt + 1}"
        )
        print(
            "SCRIPT_NARRATION_WORD_COUNT: "
            f"{candidate_gate['word_count']}"
        )

        final_output = candidate_output
        word_gate = candidate_gate

        if candidate_gate["approved"]:
            preflight_gate = evaluate_script_preflight(
                script_data=candidate_output,
                target_minimum=target_word_min,
                target_maximum=target_word_max,
                absolute_floor=pre_audio_word_floor,
                minimum_ratio=pre_audio_minimum_ratio,
                audio_duration_authoritative=(
                    audio_duration_authoritative
                ),
            )
            break

        if (
            generation_attempt
            >= max_word_count_revision_attempts
        ):
            preflight_gate = assert_script_preflight(
                script_data=candidate_output,
                target_minimum=target_word_min,
                target_maximum=target_word_max,
                absolute_floor=pre_audio_word_floor,
                minimum_ratio=pre_audio_minimum_ratio,
                audio_duration_authoritative=(
                    audio_duration_authoritative
                ),
            )
            break

        word_count_revision_attempts += 1
        active_revision_feedback = (
            build_word_count_revision_feedback(
                attempt=word_count_revision_attempts,
                word_gate=candidate_gate,
                previous_script=candidate_output["script"],
                prior_revision_feedback=revision_feedback,
                approved_claim_ids=[
                    item.get("claim_id")
                    for item in (
                        claims_ledger or {}
                    ).get("claims", [])
                    if (
                        item.get("verification_status")
                        == "approved"
                        and item.get("claim_id")
                    )
                ],
            )
        )

        print(
            "SCRIPT_WORD_COUNT_REVISION_REQUIRED: "
            f"attempt_{word_count_revision_attempts}"
        )
        print(
            "SCRIPT_WORD_COUNT_REVISION_DIRECTION: "
            f"{active_revision_feedback['direction']}"
        )
        print(
            "SCRIPT_WORD_COUNT_REVISION_TARGET: "
            f"{active_revision_feedback['target_word_count']}"
        )
        print(
            "SCRIPT_WORD_COUNT_REVISION_ISSUES_PRESERVED: "
            f"{active_revision_feedback['editorial_constraints']['issue_count']}"
        )

    if (
        final_output is None
        or word_gate is None
        or preflight_gate is None
    ):
        raise RuntimeError(
            "Script generation produced no candidate output."
        )

    final_output["quality"] = {
        "target_word_gate": word_gate,
        "pre_audio_gate": preflight_gate,
        "actual_audio_duration_pending": (
            preflight_gate["status"] == "provisional"
        ),
    }

    print(
        "SCRIPT_WORD_COUNT_REVISION_ATTEMPTS: "
        f"{word_count_revision_attempts}"
    )
    print(
        "SCRIPT_PREFLIGHT_GATE: "
        f"{preflight_gate['status']}"
    )
    print(
        "SCRIPT_PREFLIGHT_REASON: "
        f"{preflight_gate['reason']}"
    )
    print(
        "SCRIPT_PREFLIGHT_FLOOR: "
        f"{preflight_gate['provisional_floor']}"
    )
    print(
        "SCRIPT_WORD_GATE: "
        f"{'passed' if word_gate['approved'] else 'provisional'}"
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
