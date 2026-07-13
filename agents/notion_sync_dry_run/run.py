import argparse
import json
import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from jsonschema import validate

from output import save_output


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent.parent

DEFAULT_CHANNEL = "hiddenova"

NOTION_MAPPING_PATH = PROJECT_ROOT / "config" / "integrations" / "notion_mapping.json"
AGENT_REGISTRY_PATH = PROJECT_ROOT / "records" / "system" / "agent_registry_latest.json"
NOTION_SYNC_PREVIEW_RECORD_PATH = PROJECT_ROOT / "records" / "system" / "notion_sync_preview_latest.json"


def load_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Required file not found: {path}")

    return json.loads(path.read_text(encoding="utf-8-sig"))


def load_json_optional(path: Path) -> dict | None:
    if not path.exists():
        return None

    return json.loads(path.read_text(encoding="utf-8-sig"))


def load_schema() -> dict:
    return load_json(BASE_DIR / "schema.json")


def get_relative_path(path: Path) -> str:
    return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")


def latest_file(folder: Path, pattern: str) -> Path | None:
    if not folder.exists():
        return None

    files = sorted(
        folder.glob(pattern),
        key=lambda path: path.stat().st_mtime,
        reverse=True
    )

    return files[0] if files else None


def env_status(env_key: str) -> dict:
    value = os.getenv(env_key)

    return {
        "env_key": env_key,
        "is_set": bool(value),
        "safe_preview": "***set***" if value else None
    }


def build_notion_targets(mapping_data: dict) -> dict:
    targets = {}

    for database_name, database_config in mapping_data["databases"].items():
        env_key = database_config["env_key"]
        status = env_status(env_key)

        targets[database_name] = {
            "env_key": env_key,
            "database_id_available": status["is_set"],
            "sync_status": database_config["sync_status"],
            "source": database_config["source"]
        }

    return targets


def build_ai_agent_rows(agent_registry_data: dict) -> list[dict]:
    rows = []

    for item in agent_registry_data.get("agents", []):
        rows.append({
            "database": "ai_agents",
            "operation": "upsert_preview",
            "key": item["agent_name"],
            "properties": {
                "agent_name": item["agent_name"],
                "category": item["category"],
                "implementation_status": item["implementation_status"],
                "output_status": item.get("output_status"),
                "next_agent": item.get("next_agent"),
                "has_latest_output": item.get("has_latest_output"),
                "latest_output_path": item.get("latest_output_path"),
                "run_py": item.get("source_paths", {}).get("run_py"),
                "schema_json": item.get("source_paths", {}).get("schema_json")
            }
        })

    return rows


def build_youtube_channel_rows(channel: str) -> list[dict]:
    channel_record_path = latest_file(
        PROJECT_ROOT / "records" / "channel" / channel,
        "*channel_launch_ready.json"
    )

    if not channel_record_path:
        return []

    channel_record = load_json(channel_record_path)

    return [
        {
            "database": "youtube_channels",
            "operation": "upsert_preview",
            "key": channel,
            "properties": {
                "channel": channel,
                "platform": "youtube",
                "launch_status": channel_record.get("status"),
                "public_video_url": channel_record.get("public_video_url"),
                "homepage_enabled": channel_record.get("checks", {}).get("homepage_enabled"),
                "public_video_visible": channel_record.get("checks", {}).get("public_video_visible"),
                "website_link_visible": channel_record.get("checks", {}).get("website_link_visible"),
                "next_step": channel_record.get("next_step"),
                "source_record": get_relative_path(channel_record_path)
            }
        }
    ]


def build_publishing_queue_rows(channel: str) -> list[dict]:
    rows = []

    latest_release_path = latest_file(
        PROJECT_ROOT / "records" / "releases" / channel,
        "*public_release.json"
    )

    latest_upload_path = latest_file(
        PROJECT_ROOT / "records" / "uploads" / channel,
        "*upload.json"
    )

    publisher_path = PROJECT_ROOT / "agents" / "publisher" / "output" / channel / "latest.json"

    release_record = load_json_optional(latest_release_path) if latest_release_path else None
    upload_record = load_json_optional(latest_upload_path) if latest_upload_path else None
    publisher_data = load_json_optional(publisher_path)

    if release_record:
        rows.append({
            "database": "publishing_queue",
            "operation": "upsert_preview",
            "key": release_record.get("youtube_video_id"),
            "properties": {
                "channel": channel,
                "title": release_record.get("title"),
                "status": "public_released",
                "release_version": release_record.get("release_version"),
                "public_url": release_record.get("youtube_url"),
                "visibility": release_record.get("visibility"),
                "first_public_video": release_record.get("first_public_hiddenova_video"),
                "next_step": release_record.get("next_step"),
                "source_record": get_relative_path(latest_release_path)
            }
        })

    if upload_record:
        rows.append({
            "database": "publishing_queue",
            "operation": "upsert_preview",
            "key": upload_record.get("youtube_video_id"),
            "properties": {
                "channel": channel,
                "title": upload_record.get("title"),
                "status": "unlisted_upload_record",
                "unlisted_url": upload_record.get("youtube_url"),
                "visibility": upload_record.get("visibility"),
                "public_status": upload_record.get("public_status"),
                "next_step": upload_record.get("next_step"),
                "source_record": get_relative_path(latest_upload_path)
            }
        })

    if publisher_data:
        package = publisher_data.get("publishing_package", {})
        metadata = package.get("video_metadata", {})
        assets = package.get("assets", {})
        readiness = package.get("readiness", {})

        rows.append({
            "database": "publishing_queue",
            "operation": "upsert_preview",
            "key": "publisher_latest",
            "properties": {
                "channel": channel,
                "title": metadata.get("title"),
                "status": publisher_data.get("status"),
                "upload_ready": readiness.get("upload_ready"),
                "video_file_path": assets.get("video_file_path"),
                "thumbnail_image_path": assets.get("thumbnail_image_path"),
                "source_record": get_relative_path(publisher_path)
            }
        })

    return rows


def build_sync_preview(channel: str, mapping_data: dict, agent_registry_data: dict) -> dict:
    ai_agent_rows = build_ai_agent_rows(agent_registry_data)
    youtube_channel_rows = build_youtube_channel_rows(channel)
    publishing_queue_rows = build_publishing_queue_rows(channel)

    first_scope = mapping_data.get("first_sync_scope", [])

    rows_by_database = {
        "ai_agents": ai_agent_rows,
        "youtube_channels": youtube_channel_rows,
        "publishing_queue": publishing_queue_rows
    }

    scoped_rows = {
        database: rows
        for database, rows in rows_by_database.items()
        if database in first_scope
    }

    return {
        "scope": first_scope,
        "rows_by_database": scoped_rows,
        "row_counts": {
            database: len(rows)
            for database, rows in scoped_rows.items()
        },
        "total_preview_rows": sum(len(rows) for rows in scoped_rows.values())
    }


def write_preview_record(final_output: dict) -> Path:
    NOTION_SYNC_PREVIEW_RECORD_PATH.parent.mkdir(parents=True, exist_ok=True)

    record = {
        "record_type": "notion_sync_preview",
        "version": "1.0",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "channel": final_output["channel"],
        "status": final_output["status"],
        "summary": final_output["summary"],
        "notion_targets": final_output["notion_targets"],
        "sync_preview": final_output["sync_preview"],
        "next_step": "connect_notion_credentials_then_test_one_database"
    }

    NOTION_SYNC_PREVIEW_RECORD_PATH.write_text(
        json.dumps(record, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    return NOTION_SYNC_PREVIEW_RECORD_PATH


def build_output(channel: str, mapping_data: dict, agent_registry_data: dict, record_path: Path | None) -> dict:
    notion_targets = build_notion_targets(mapping_data)
    sync_preview = build_sync_preview(
        channel=channel,
        mapping_data=mapping_data,
        agent_registry_data=agent_registry_data
    )

    missing_first_scope_env = [
        database
        for database in mapping_data.get("first_sync_scope", [])
        if not notion_targets.get(database, {}).get("database_id_available")
    ]

    return {
        "agent": "notion_sync_dry_run",
        "version": "1.0",
        "channel": channel,
        "status": "preview_ready",
        "summary": {
            "first_sync_scope": mapping_data.get("first_sync_scope", []),
            "total_preview_rows": sync_preview["total_preview_rows"],
            "missing_first_scope_database_ids": missing_first_scope_env,
            "notion_api_key_available": bool(os.getenv("NOTION_API_KEY")),
            "dry_run_only": True,
            "next_step": "connect_notion_credentials_then_test_one_database"
        },
        "notion_targets": notion_targets,
        "sync_preview": sync_preview,
        "record": {
            "record_written": record_path is not None,
            "record_path": get_relative_path(record_path) if record_path else None
        },
        "metadata": {
            "next_agent": "notion_sync_agent"
        }
    }


def print_summary(final_output: dict) -> None:
    print("Notion Sync Dry-Run Agent completed successfully.")
    print(f"Status: {final_output['status']}")
    print(f"Total preview rows: {final_output['summary']['total_preview_rows']}")
    print(f"Notion API key available: {final_output['summary']['notion_api_key_available']}")
    print(f"Missing DB IDs: {final_output['summary']['missing_first_scope_database_ids']}")
    print(f"Record path: {final_output['record']['record_path']}")
    print("")
    print("Row counts:")

    for database, count in final_output["sync_preview"]["row_counts"].items():
        print(f"- {database}: {count}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a Notion sync dry-run preview from Mecoria OS records."
    )

    parser.add_argument(
        "--channel",
        default=DEFAULT_CHANNEL,
        help="Channel name. Default: hiddenova"
    )

    parser.add_argument(
        "--no-record",
        action="store_true",
        help="Do not write records/system/notion_sync_preview_latest.json"
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    channel = args.channel.lower()

    load_dotenv(PROJECT_ROOT / ".env")

    mapping_data = load_json(NOTION_MAPPING_PATH)
    agent_registry_data = load_json(AGENT_REGISTRY_PATH)

    temp_output = build_output(
        channel=channel,
        mapping_data=mapping_data,
        agent_registry_data=agent_registry_data,
        record_path=None
    )

    record_path = None

    if not args.no_record:
        record_path = write_preview_record(temp_output)

    final_output = build_output(
        channel=channel,
        mapping_data=mapping_data,
        agent_registry_data=agent_registry_data,
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
