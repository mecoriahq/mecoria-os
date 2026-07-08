import argparse
import json
import subprocess
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
        "command": "python agents/image_generation/run.py --source prompt"
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
        "command": "python agents/image_generation/run.py --source revision"
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


SAFE_EXECUTE_STEPS = {
    "research",
    "script",
    "seo",
    "qa",
    "visual_brief",
    "image_prompt"
}


def load_json(file_path: Path) -> dict:
    if not file_path.exists():
        raise FileNotFoundError(f"Required file not found: {file_path}")

    return json.loads(file_path.read_text(encoding="utf-8"))


def load_schema() -> dict:
    return load_json(PROJECT_ROOT / "core" / "pipeline" / "schema.json")


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def create_step(step: dict) -> dict:
    return {
        "name": step["name"],
        "command": step["command"],
        "status": "pending",
        "started_at": None,
        "finished_at": None,
        "error": None
    }


def mark_skipped(step: dict, reason: str | None = None) -> dict:
    step["status"] = "skipped"
    step["started_at"] = None
    step["finished_at"] = None
    step["error"] = reason
    return step


def can_execute_step(
    step_name: str,
    include_image_generation: bool,
    include_image_qa: bool,
    include_publisher: bool
) -> bool:
    if step_name in SAFE_EXECUTE_STEPS:
        return True

    if step_name == "image_generation":
        return include_image_generation

    if step_name == "image_qa":
        return include_image_generation and include_image_qa

    if step_name == "publisher":
        return include_image_generation and include_image_qa and include_publisher

    return False


def get_skip_reason(
    step_name: str,
    include_image_generation: bool,
    include_image_qa: bool,
    include_publisher: bool
) -> str:
    if step_name == "image_generation":
        return "Skipped because --include-image-generation was not provided."

    if step_name == "image_qa":
        if not include_image_generation:
            return "Skipped because image generation was not enabled."
        if not include_image_qa:
            return "Skipped because --include-image-qa was not provided."

    if step_name == "publisher":
        if not include_image_generation:
            return "Skipped because image generation was not enabled."
        if not include_image_qa:
            return "Skipped because image QA was not enabled."
        if not include_publisher:
            return "Skipped because --include-publisher was not provided."

    return "Skipped by safe execute mode. This step is not enabled in this version."


def run_step(step: dict, timeout_seconds: int) -> dict:
    step["status"] = "running"
    step["started_at"] = now_iso()

    print(f"\n▶ Running step: {step['name']}", flush=True)
    print(f"  Command: {step['command']}", flush=True)

    try:
        result = subprocess.run(
            step["command"],
            cwd=PROJECT_ROOT,
            shell=True,
            timeout=timeout_seconds
        )
    except subprocess.TimeoutExpired:
        step["finished_at"] = now_iso()
        step["status"] = "failed"
        step["error"] = f"Step timed out after {timeout_seconds} seconds."
        print(f"✗ Failed: {step['name']} timed out.", flush=True)
        return step

    step["finished_at"] = now_iso()

    if result.returncode != 0:
        step["status"] = "failed"
        step["error"] = f"Step failed with exit code {result.returncode}."
        print(f"✗ Failed: {step['name']}", flush=True)
        return step

    step["status"] = "success"
    step["error"] = None
    print(f"✓ Completed: {step['name']}", flush=True)
    return step


def build_dry_run_output(channel: str) -> dict:
    started_at = now_iso()

    steps = [
        mark_skipped(
            create_step(step),
            reason="Dry-run mode. Step was not executed."
        )
        for step in PIPELINE_STEPS
    ]

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


def build_execute_output(
    channel: str,
    until_step: str,
    timeout_seconds: int,
    include_image_generation: bool,
    include_image_qa: bool,
    include_publisher: bool
) -> dict:
    started_at = now_iso()
    steps = [create_step(step) for step in PIPELINE_STEPS]

    pipeline_status = "success"
    final_agent = None
    failure_found = False
    stop_after_current = False

    for step in steps:
        if failure_found:
            mark_skipped(
                step,
                reason="Skipped because a previous step failed."
            )
            continue

        if stop_after_current:
            mark_skipped(
                step,
                reason=f"Skipped because --until {until_step} was reached."
            )
            continue

        if not can_execute_step(
            step_name=step["name"],
            include_image_generation=include_image_generation,
            include_image_qa=include_image_qa,
            include_publisher=include_publisher
        ):
            mark_skipped(
                step,
                reason=get_skip_reason(
                    step_name=step["name"],
                    include_image_generation=include_image_generation,
                    include_image_qa=include_image_qa,
                    include_publisher=include_publisher
                )
            )

            if step["name"] == until_step:
                stop_after_current = True

            continue

        run_step(
            step=step,
            timeout_seconds=timeout_seconds
        )

        if step["status"] == "failed":
            pipeline_status = "failed"
            failure_found = True
        elif step["status"] == "success":
            final_agent = step["name"]

        if step["name"] == until_step:
            stop_after_current = True

    finished_at = now_iso()

    successful_steps = sum(1 for step in steps if step["status"] == "success")
    failed_steps = sum(1 for step in steps if step["status"] == "failed")

    return {
        "pipeline": "media",
        "version": "1.0",
        "channel": channel,
        "status": pipeline_status,
        "started_at": started_at,
        "finished_at": finished_at,
        "steps": steps,
        "summary": {
            "total_steps": len(steps),
            "successful_steps": successful_steps,
            "failed_steps": failed_steps,
            "final_agent": final_agent
        }
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Mecoria Media pipeline."
    )

    parser.add_argument(
        "--channel",
        default="hiddenova",
        help="Channel name. Default: hiddenova"
    )

    parser.add_argument(
        "--execute",
        action="store_true",
        help="Run safe pipeline steps. By default, only dry-run is executed."
    )

    parser.add_argument(
        "--until",
        default="image_prompt",
        choices=[step["name"] for step in PIPELINE_STEPS],
        help="Stop execution after this step. Default: image_prompt"
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=600,
        help="Timeout per step in seconds. Default: 600"
    )

    parser.add_argument(
        "--include-image-generation",
        action="store_true",
        help="Allow the orchestrator to run the image_generation step."
    )

    parser.add_argument(
        "--include-image-qa",
        action="store_true",
        help="Allow the orchestrator to run the image_qa step."
    )

    parser.add_argument(
        "--include-publisher",
        action="store_true",
        help="Allow the orchestrator to run the publisher packaging step."
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    channel = args.channel

    if args.execute:
        pipeline_output = build_execute_output(
            channel=channel,
            until_step=args.until,
            timeout_seconds=args.timeout,
            include_image_generation=args.include_image_generation,
            include_image_qa=args.include_image_qa,
            include_publisher=args.include_publisher
        )
    else:
        pipeline_output = build_dry_run_output(channel=channel)

    schema = load_schema()
    validate(instance=pipeline_output, schema=schema)

    latest_path = save_output(
        channel=channel,
        data=pipeline_output
    )

    if args.execute:
        print("\nMedia Pipeline safe execute completed.")
    else:
        print("Media Pipeline dry-run completed successfully.")

    print(f"Output saved to: {latest_path}")


if __name__ == "__main__":
    main()