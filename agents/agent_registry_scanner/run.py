import argparse
import json
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from jsonschema import validate

from output import save_output


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent.parent

DEFAULT_CHANNEL = "hiddenova"
AGENTS_DIR = PROJECT_ROOT / "agents"
RECORD_PATH = PROJECT_ROOT / "records" / "system" / "agent_registry_latest.json"


def load_json_optional(file_path: Path) -> dict | None:
    if not file_path.exists():
        return None

    try:
        return json.loads(file_path.read_text(encoding="utf-8-sig"))
    except Exception as error:
        return {
            "_load_error": str(error)
        }


def load_schema() -> dict:
    schema_path = BASE_DIR / "schema.json"
    return json.loads(schema_path.read_text(encoding="utf-8-sig"))


def get_relative_path(path: Path) -> str:
    return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")


def get_latest_output_path(agent_dir: Path, channel: str) -> Path:
    return agent_dir / "output" / channel.lower() / "latest.json"


def classify_agent(agent_name: str) -> str:
    if "qa" in agent_name:
        return "qa"
    if "voice" in agent_name or "audio" in agent_name:
        return "audio"
    if "video" in agent_name:
        return "video"
    if "image" in agent_name or "visual" in agent_name or "thumbnail" in agent_name:
        return "visual"
    if "publisher" in agent_name or "upload" in agent_name:
        return "publishing"
    if "research" in agent_name or "script" in agent_name or "seo" in agent_name:
        return "content"
    if "registry" in agent_name or "sync" in agent_name or "ingest" in agent_name:
        return "system"
    return "general"


def get_file_modified_iso(path: Path | None) -> str | None:
    if path is None or not path.exists():
        return None

    return datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds")


def extract_output_summary(output_data: dict | None) -> dict:
    if output_data is None:
        return {
            "has_output": False,
            "output_load_error": None,
            "output_agent": None,
            "output_version": None,
            "output_status": None,
            "next_agent": None
        }

    if "_load_error" in output_data:
        return {
            "has_output": True,
            "output_load_error": output_data["_load_error"],
            "output_agent": None,
            "output_version": None,
            "output_status": "unreadable",
            "next_agent": None
        }

    metadata = output_data.get("metadata", {})

    return {
        "has_output": True,
        "output_load_error": None,
        "output_agent": output_data.get("agent"),
        "output_version": output_data.get("version"),
        "output_status": output_data.get("status"),
        "next_agent": metadata.get("next_agent")
    }


def scan_agent(agent_dir: Path, channel: str) -> dict:
    agent_name = agent_dir.name

    run_path = agent_dir / "run.py"
    schema_path = agent_dir / "schema.json"
    prompt_path = agent_dir / "prompt.py"
    output_path = agent_dir / "output.py"
    latest_output_path = get_latest_output_path(agent_dir, channel)

    latest_output_data = load_json_optional(latest_output_path)
    output_summary = extract_output_summary(latest_output_data)

    has_run_py = run_path.exists()
    has_schema_json = schema_path.exists()
    has_output_py = output_path.exists()

    if has_run_py and has_schema_json:
        implementation_status = "implemented"
    elif has_run_py or has_schema_json:
        implementation_status = "partial"
    else:
        implementation_status = "non_agent_or_support_folder"

    return {
        "agent_name": agent_name,
        "category": classify_agent(agent_name),
        "implementation_status": implementation_status,
        "has_run_py": has_run_py,
        "has_schema_json": has_schema_json,
        "has_output_py": has_output_py,
        "has_prompt_py": prompt_path.exists(),
        "has_latest_output": output_summary["has_output"],
        "latest_output_path": get_relative_path(latest_output_path) if latest_output_path.exists() else None,
        "latest_output_modified_at": get_file_modified_iso(latest_output_path),
        "output_load_error": output_summary["output_load_error"],
        "output_agent": output_summary["output_agent"],
        "output_version": output_summary["output_version"],
        "output_status": output_summary["output_status"],
        "next_agent": output_summary["next_agent"],
        "source_paths": {
            "run_py": get_relative_path(run_path) if run_path.exists() else None,
            "schema_json": get_relative_path(schema_path) if schema_path.exists() else None,
            "output_py": get_relative_path(output_path) if output_path.exists() else None,
            "prompt_py": get_relative_path(prompt_path) if prompt_path.exists() else None
        }
    }


def scan_agents(channel: str) -> list[dict]:
    if not AGENTS_DIR.exists():
        raise FileNotFoundError(f"Agents directory not found: {AGENTS_DIR}")

    agent_dirs = [
        path for path in AGENTS_DIR.iterdir()
        if path.is_dir() and not path.name.startswith(".")
    ]

    return [
        scan_agent(agent_dir=agent_dir, channel=channel)
        for agent_dir in sorted(agent_dirs, key=lambda path: path.name)
    ]


def build_summary(agent_records: list[dict]) -> dict:
    implemented = [
        item for item in agent_records
        if item["implementation_status"] == "implemented"
    ]

    with_outputs = [
        item for item in agent_records
        if item["has_latest_output"]
    ]

    unreadable_outputs = [
        item for item in agent_records
        if item["output_load_error"]
    ]

    categories = {}

    for item in agent_records:
        category = item["category"]
        categories[category] = categories.get(category, 0) + 1

    return {
        "total_agent_folders": len(agent_records),
        "implemented_agent_count": len(implemented),
        "agent_with_latest_output_count": len(with_outputs),
        "unreadable_output_count": len(unreadable_outputs),
        "category_counts": categories
    }


def write_record_file(final_output: dict) -> Path:
    RECORD_PATH.parent.mkdir(parents=True, exist_ok=True)

    record = {
        "record_type": "agent_registry_snapshot",
        "version": "1.0",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "channel": final_output["channel"],
        "summary": final_output["summary"],
        "agents": final_output["agents"],
        "source": {
            "scanner_agent": "agent_registry_scanner",
            "scanner_output_agent": final_output["agent"]
        },
        "next_step": "notion_sync_dry_run"
    }

    RECORD_PATH.write_text(
        json.dumps(record, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    return RECORD_PATH


def build_output(channel: str, agent_records: list[dict], record_path: Path | None) -> dict:
    summary = build_summary(agent_records)

    return {
        "agent": "agent_registry_scanner",
        "version": "1.0",
        "channel": channel,
        "status": "registry_ready",
        "summary": summary,
        "agents": agent_records,
        "record": {
            "record_written": record_path is not None,
            "record_path": get_relative_path(record_path) if record_path else None
        },
        "metadata": {
            "next_agent": "notion_sync_dry_run"
        }
    }


def print_summary(final_output: dict) -> None:
    print("Agent Registry Scanner completed successfully.")
    print(f"Status: {final_output['status']}")
    print(f"Total folders: {final_output['summary']['total_agent_folders']}")
    print(f"Implemented agents: {final_output['summary']['implemented_agent_count']}")
    print(f"Agents with latest output: {final_output['summary']['agent_with_latest_output_count']}")
    print(f"Record written: {final_output['record']['record_written']}")
    print(f"Record path: {final_output['record']['record_path']}")
    print("")
    print("Category counts:")

    for category, count in sorted(final_output["summary"]["category_counts"].items()):
        print(f"- {category}: {count}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scan Mecoria OS agents and produce an agent registry snapshot."
    )

    parser.add_argument(
        "--channel",
        default=DEFAULT_CHANNEL,
        help="Channel name. Default: hiddenova"
    )

    parser.add_argument(
        "--no-record",
        action="store_true",
        help="Do not write records/system/agent_registry_latest.json"
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    channel = args.channel.lower()

    load_dotenv(PROJECT_ROOT / ".env")

    agent_records = scan_agents(channel)

    temp_output = build_output(
        channel=channel,
        agent_records=agent_records,
        record_path=None
    )

    record_path = None

    if not args.no_record:
        record_path = write_record_file(temp_output)

    final_output = build_output(
        channel=channel,
        agent_records=agent_records,
        record_path=record_path
    )

    schema = load_schema()
    validate(instance=final_output, schema=schema)

    latest_path = save_output(
        channel=final_output["channel"],
        data=final_output
    )

    print_summary(final_output)
    print(f"Output saved to: {latest_path}")


if __name__ == "__main__":
    main()
