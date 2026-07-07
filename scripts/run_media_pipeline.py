import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from jsonschema import validate


PROJECT_ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(PROJECT_ROOT))

from core.pipeline.output import save_output


PIPELINE_STEPS = [
    {
        "name": "research",
        "command": "python agents/research/run.py"
    },
    {
        "name": "script",
        "command": "python agents/script/run.py"
    },
    {
        "name": "seo",
        "command": "python agents/seo/run.py"
    },
    {
        "name": "qa",
        "command": "python agents/qa/run.py"
    },
    {
        "name": "visual_brief",
        "command": "python agents/visual_brief/run.py"
    },
    {
        "name": "image_prompt",
        "command": "python agents/image_prompt/run.py"
    },
    {
        "name": "image_generation",
        "command": "python agents/image_generation/run.py"
    },
    {
        "name": "image_qa",
        "command": "python agents/image_qa/run.py"
    },
    {
        "name": "image_revision_if_needed",
        "command": "python agents/image_revision/run.py"
    },
    {
        "name": "image_generation_after_revision",
        "command": "python agents/image_generation/run.py"
    },
    {
        "name": "image_qa_after_revision",
        "command": "python agents/image_qa/run.py"
    },
    {
        "name": "publisher",
        "command": "python agents/publisher/run.py"
    }
]


def load_json(file_path: Path) -> dict:
    if not file_path.exists():
        raise FileNotFoundError(f"Required file not found: {file_path}")

    return json.loads(file_path.read_text(encoding="utf-8"))


def load_schema() -> dict:
    return load_json(PROJECT_ROOT / "core" / "pipeline" / "schema.json")


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def build_dry_run_step(step: dict) -> dict:
    return {
        "name": step["name"],
        "command": step["command"],
        "status": "skipped",
        "started_at": None,
        "finished_at": None,
        "error": None
    }


def build_dry_run_output(channel: str) -> dict:
    started_at = now_iso()
    steps = [build_dry_run_step(step) for step in PIPELINE_STEPS]
    finished_at = now_iso()

    return {
        "pipeline": "media",
        "version": "1.0",
        "channel": channel,
        "status": "dry_run",
        "started_at": started_at,
        "finished_at": finished_at,
        "steps": steps,
        "summary": {
            "total_steps": len(steps),
            "successful_steps": 0,
            "failed_steps": 0,
            "final_agent": "publisher"
        }
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Mecoria Media pipeline dry-run."
    )

    parser.add_argument(
        "--channel",
        default="hiddenova",
        help="Channel name. Default: hiddenova"
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    channel = args.channel

    pipeline_output = build_dry_run_output(channel=channel)

    schema = load_schema()
    validate(instance=pipeline_output, schema=schema)

    latest_path = save_output(
        channel=channel,
        data=pipeline_output
    )

    print("Media Pipeline dry-run completed successfully.")
    print(f"Output saved to: {latest_path}")


if __name__ == "__main__":
    main()