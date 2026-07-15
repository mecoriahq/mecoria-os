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



def get_relative_path(path: Path) -> str:
    return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate SEO from a locked video run context."
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


def resolve_seo_input(
    channel: str,
    video_id: str | None
) -> tuple[dict | None, Path, dict]:
    if not video_id:
        script_path = get_script_latest_path(channel)
        return None, script_path, load_json(script_path)

    context = load_context(
        channel=channel,
        video_id=video_id
    )

    script_path = resolve_output(
        context=context,
        key="script"
    )
    script_data = load_json(script_path)

    if script_data.get("video_id") != context["video_id"]:
        raise ValueError("Script output video_id mismatch.")

    if script_data.get("run_id") != context["run_id"]:
        raise ValueError("Script output run_id mismatch.")

    return context, script_path, script_data


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

    output_path = output_dir / "seo.json"
    output_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=True),
        encoding="utf-8"
    )

    context = register_output(
        context=context,
        agent="seo",
        reference=get_relative_path(output_path),
        status="seo_ready"
    )
    context = set_status(
        context=context,
        status="seo_ready",
        next_agent="qa"
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

    context, script_path, script_data = resolve_seo_input(
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
        "SCRIPT_TITLE: "
        f"{script_data['script']['title']}"
    )

    if args.dry_run:
        print("STATUS: seo_dry_run_ready")
        return

    prompt = build_prompt(script_data=script_data)
    raw_seo_data = generate_seo(prompt)

    final_output = normalize_output(
        script_data=script_data,
        seo_data=raw_seo_data
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

    print("SEO Agent completed successfully.")
    print(f"Output saved to: {output_path}")


if __name__ == "__main__":
    main()
