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
    load_context,
    register_output,
    resolve_output,
    save_context,
    set_status,
)


from core.content_quality import (
    evaluate_script_word_count,
)

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


def extract_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}") + 1

        if start == -1 or end == 0:
            raise ValueError("OpenAI response does not contain valid JSON.")

        return json.loads(text[start:end])


def generate_qa(prompt: str) -> dict:
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



def build_word_count_rejection(
    word_gate: dict
) -> dict:
    return {
        "status": "rejected",
        "overall_score": 0,
        "checks": {
            "script_quality": {
                "status": "fail",
                "score": 0
            },
            "seo_alignment": {
                "status": "warning",
                "score": 0
            },
            "title_quality": {
                "status": "warning",
                "score": 0
            },
            "description_quality": {
                "status": "warning",
                "score": 0
            },
            "tags_quality": {
                "status": "warning",
                "score": 0
            },
            "thumbnail_text_quality": {
                "status": "warning",
                "score": 0
            }
        },
        "issues": [
            {
                "field": "script.narration_word_count",
                "severity": "high",
                "message": (
                    "Script narration word count is outside "
                    "the approved range. "
                    f"Actual: {word_gate['word_count']}. "
                    f"Required: {word_gate['minimum']} to "
                    f"{word_gate['maximum']}."
                )
            }
        ],
        "recommendations": [
            {
                "field": "script",
                "suggestion": (
                    "Regenerate the script within the "
                    "required narration word range before "
                    "audio or visual production."
                )
            }
        ]
    }


def normalize_output(script_data: dict, qa_data: dict) -> dict:
    status = qa_data["status"]

    next_agent = "thumbnail" if status == "approved" else None

    return {
        "agent": "qa",
        "version": "1.0",
        "channel": script_data["channel"],
        "status": status,
        "overall_score": qa_data["overall_score"],
        "checks": qa_data["checks"],
        "issues": qa_data["issues"],
        "recommendations": qa_data["recommendations"],
        "metadata": {
            "source_agents": [
                "script",
                "seo"
            ],
            "next_agent": next_agent
        }
    }



def get_relative_path(path: Path) -> str:
    return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run QA for a locked video run context."
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
        "--dry-run",
        action="store_true"
    )

    return parser.parse_args()


def resolve_qa_inputs(
    channel: str,
    video_id: str | None
) -> tuple[dict | None, Path, dict, Path, dict]:
    if not video_id:
        script_path = get_script_latest_path(channel)
        seo_path = get_seo_latest_path(channel)

        return (
            None,
            script_path,
            load_json(script_path),
            seo_path,
            load_json(seo_path)
        )

    context = load_context(
        channel=channel,
        video_id=video_id
    )

    script_path = resolve_output(
        context=context,
        key="script"
    )
    seo_path = resolve_output(
        context=context,
        key="seo"
    )

    script_data = load_json(script_path)
    seo_data = load_json(seo_path)

    for name, data in (
        ("script", script_data),
        ("seo", seo_data)
    ):
        if data.get("video_id") != context["video_id"]:
            raise ValueError(f"{name} output video_id mismatch.")

        if data.get("run_id") != context["run_id"]:
            raise ValueError(f"{name} output run_id mismatch.")

    return (
        context,
        script_path,
        script_data,
        seo_path,
        seo_data
    )


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

    output_path = output_dir / "qa.json"
    output_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=True),
        encoding="utf-8"
    )

    context = register_output(
        context=context,
        agent="qa",
        reference=get_relative_path(output_path),
        status=data["status"]
    )

    if data["status"] == "approved":
        context = set_status(
            context=context,
            status="content_qa_ready",
            next_agent="media_video_orchestrator"
        )
    else:
        context = set_status(
            context=context,
            status="content_revision_required",
            next_agent=None
        )

    save_context(context)
    return output_path


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
        script_path,
        script_data,
        seo_path,
        seo_data
    ) = resolve_qa_inputs(
        channel=channel,
        video_id=video_id
    )

    print(f"CHANNEL: {channel}")
    print(f"VIDEO_CONTEXT_ID: {video_id}")
    print(
        "SCRIPT_SOURCE: "
        f"{get_relative_path(script_path)}"
    )
    print(
        "SEO_SOURCE: "
        f"{get_relative_path(seo_path)}"
    )
    print(
        "SCRIPT_TITLE: "
        f"{script_data['script']['title']}"
    )
    print(
        "SEO_TITLE: "
        f"{seo_data['seo']['video_title']}"
    )

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

    word_gate = evaluate_script_word_count(
        script_data=script_data,
        minimum=target_word_min,
        maximum=target_word_max
    )

    print(
        "SCRIPT_NARRATION_WORD_COUNT: "
        f"{word_gate['word_count']}"
    )
    print(
        "SCRIPT_WORD_GATE: "
        f"{word_gate['status']}"
    )

    if args.dry_run:
        print("STATUS: qa_dry_run_ready")
        return

    if not word_gate["approved"]:
        raw_qa_data = build_word_count_rejection(
            word_gate
        )
    else:
        prompt = build_prompt(
            script_data=script_data,
            seo_data=seo_data
        )

        raw_qa_data = generate_qa(prompt)

    final_output = normalize_output(
        script_data=script_data,
        qa_data=raw_qa_data
    )

    if context:
        final_output["version"] = "2.0"
        final_output["video_id"] = context["video_id"]
        final_output["run_id"] = context["run_id"]

    schema = load_schema()
    validate(instance=final_output, schema=schema)

    if context:
        output_path = save_video_specific_output(
            context=context,
            data=final_output
        )
    else:
        output_path = save_output(
            channel=script_data["channel"],
            data=final_output
        )

    print("QA Agent completed successfully.")
    print(f"Status: {final_output['status']}")
    print(f"Score: {final_output['overall_score']}")
    print(f"Output saved to: {output_path}")


if __name__ == "__main__":
    main()
