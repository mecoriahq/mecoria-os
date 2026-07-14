import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from jsonschema import validate

from output import save_json


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent.parent

OUTPUT_PATH = BASE_DIR / "output" / "hiddenova" / "latest.json"
RECORD_PATH = PROJECT_ROOT / "records" / "system" / "notion_os_sync_runner_latest.json"
SCHEMA_PATH = BASE_DIR / "schema.json"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def command_to_string(command: list[str]) -> str:
    return " ".join(command)


def tail_text(text: str, max_lines: int = 60) -> str:
    lines = text.splitlines()
    return "\n".join(lines[-max_lines:])


def read_child_record(record_path: Path) -> dict | None:
    if not record_path.exists():
        return None

    try:
        return load_json(record_path)
    except Exception as error:
        return {
            "status": "record_read_failed",
            "error": str(error)
        }


def run_step(step: dict) -> dict:
    started_at = datetime.now().isoformat(timespec="seconds")

    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"

    completed = subprocess.run(
        step["command"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env
    )

    finished_at = datetime.now().isoformat(timespec="seconds")
    child_record_path = PROJECT_ROOT / step["child_record_path"]
    child_record = read_child_record(child_record_path)

    child_status = None
    child_summary = None

    if isinstance(child_record, dict):
        child_status = child_record.get("status")
        child_summary = child_record.get("summary")

    ok = (
        completed.returncode == 0
        and child_status in step["expected_statuses"]
    )

    return {
        "key": step["key"],
        "label": step["label"],
        "mode": step["mode"],
        "writes_to_notion": step["writes_to_notion"],
        "ok": ok,
        "returncode": completed.returncode,
        "expected_statuses": step["expected_statuses"],
        "child_status": child_status,
        "child_summary": child_summary,
        "child_record_path": step["child_record_path"],
        "command": command_to_string(step["command"]),
        "started_at": started_at,
        "finished_at": finished_at,
        "stdout_tail": tail_text(completed.stdout),
        "stderr_tail": tail_text(completed.stderr)
    }


def build_steps(apply: bool) -> list[dict]:
    python = sys.executable

    common_steps = [
        {
            "key": "notion_connection_test",
            "label": "Notion connection test",
            "mode": "preflight",
            "writes_to_notion": False,
            "command": [python, "agents/notion_connection_test/run.py"],
            "child_record_path": "records/system/notion_connection_test_latest.json",
            "expected_statuses": ["connection_ready"]
        },
        {
            "key": "notion_sync_preview",
            "label": "Notion sync preview refresh",
            "mode": "preflight",
            "writes_to_notion": False,
            "command": [python, "agents/notion_sync_dry_run/run.py"],
            "child_record_path": "records/system/notion_sync_preview_latest.json",
            "expected_statuses": ["preview_ready"]
        }
    ]

    if apply:
        sync_steps = [
            {
                "key": "ai_agents_sync",
                "label": "AI Agents full sync",
                "mode": "apply",
                "writes_to_notion": True,
                "command": [python, "agents/notion_ai_agents_sync/run.py", "--apply", "--allow-full-apply"],
                "child_record_path": "records/system/notion_ai_agents_sync_latest.json",
                "expected_statuses": ["full_sync_passed"]
            },
            {
                "key": "youtube_channels_sync",
                "label": "YouTube Channels sync",
                "mode": "apply",
                "writes_to_notion": True,
                "command": [python, "agents/notion_youtube_channels_sync/run.py", "--apply"],
                "child_record_path": "records/system/notion_youtube_channels_sync_latest.json",
                "expected_statuses": ["sync_passed"]
            },
            {
                "key": "publishing_queue_sync",
                "label": "Publishing Queue sync",
                "mode": "apply",
                "writes_to_notion": True,
                "command": [python, "agents/notion_publishing_queue_sync/run.py", "--apply"],
                "child_record_path": "records/system/notion_publishing_queue_sync_latest.json",
                "expected_statuses": ["sync_passed"]
            }
        ]

    else:
        sync_steps = [
            {
                "key": "ai_agents_sync_dry_run",
                "label": "AI Agents sync dry-run",
                "mode": "dry_run",
                "writes_to_notion": False,
                "command": [python, "agents/notion_ai_agents_sync/run.py"],
                "child_record_path": "records/system/notion_ai_agents_sync_latest.json",
                "expected_statuses": ["dry_run_ready"]
            },
            {
                "key": "youtube_channels_sync_dry_run",
                "label": "YouTube Channels sync dry-run",
                "mode": "dry_run",
                "writes_to_notion": False,
                "command": [python, "agents/notion_youtube_channels_sync/run.py"],
                "child_record_path": "records/system/notion_youtube_channels_sync_latest.json",
                "expected_statuses": ["dry_run_ready"]
            },
            {
                "key": "publishing_queue_sync_dry_run",
                "label": "Publishing Queue sync dry-run",
                "mode": "dry_run",
                "writes_to_notion": False,
                "command": [python, "agents/notion_publishing_queue_sync/run.py"],
                "child_record_path": "records/system/notion_publishing_queue_sync_latest.json",
                "expected_statuses": ["dry_run_ready"]
            }
        ]

    return common_steps + sync_steps


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    steps_to_run = build_steps(apply=args.apply)
    results = []

    for step in steps_to_run:
        result = run_step(step)
        results.append(result)

        if not result["ok"]:
            break

    failed_steps = [
        result
        for result in results
        if not result["ok"]
    ]

    passed_steps = [
        result
        for result in results
        if result["ok"]
    ]

    all_steps_completed = len(results) == len(steps_to_run)
    all_steps_passed = all_steps_completed and not failed_steps

    if args.apply and all_steps_passed:
        status = "os_sync_passed"
        next_step = "connect_os_sync_runner_to_n8n_or_schedule"
    elif not args.apply and all_steps_passed:
        status = "os_sync_dry_run_ready"
        next_step = "run_os_sync_runner_apply"
    else:
        status = "os_sync_failed"
        next_step = "inspect_failed_step_before_continuing"

    record = {
        "record_type": "notion_os_sync_runner",
        "version": "1.0",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "status": status,
        "summary": {
            "mode": "apply" if args.apply else "dry_run",
            "total_defined_steps": len(steps_to_run),
            "executed_step_count": len(results),
            "passed_step_count": len(passed_steps),
            "failed_step_count": len(failed_steps),
            "failed_step_keys": [step["key"] for step in failed_steps],
            "write_operations_performed": bool(args.apply),
            "notion_write_step_count": len([
                step
                for step in results
                if step.get("writes_to_notion")
            ]),
            "synced_targets": [
                step["key"]
                for step in results
                if step.get("writes_to_notion") and step.get("ok")
            ],
            "next_step": next_step
        },
        "steps": results,
        "security": {
            "token_saved_to_output": False,
            "token_printed_to_terminal": False,
            "openai_key_saved_to_output": False,
            "write_operations_performed": bool(args.apply),
            "mode": "apply" if args.apply else "dry_run_only"
        }
    }

    validate(record, load_json(SCHEMA_PATH))

    save_json(record, OUTPUT_PATH)
    save_json(record, RECORD_PATH)

    print("Mecoria OS Notion Sync Runner completed.")
    print(f"Status: {record['status']}")
    print(f"Mode: {record['summary']['mode']}")
    print(f"Executed steps: {record['summary']['executed_step_count']} / {record['summary']['total_defined_steps']}")
    print(f"Passed steps: {record['summary']['passed_step_count']}")
    print(f"Failed steps: {record['summary']['failed_step_keys']}")
    print(f"Write operations performed: {record['summary']['write_operations_performed']}")
    print("")

    for result in results:
        print(
            f"- {result['key']}: "
            f"ok={result['ok']} "
            f"child_status={result.get('child_status')} "
            f"writes_to_notion={result.get('writes_to_notion')}"
        )

    print("")
    print(f"Record path: {RECORD_PATH.relative_to(PROJECT_ROOT)}")
    print(f"Output saved to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
