from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from jsonschema import validate

from output import save_output


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.notion_multichannel_preview import (
    build_channel_keys,
    build_publishing_queue_rows,
    build_youtube_channel_rows,
    normalize_channel_filter,
)


NOTION_MAPPING_PATH = (
    PROJECT_ROOT
    / "config"
    / "integrations"
    / "notion_mapping.json"
)
AGENT_REGISTRY_PATH = (
    PROJECT_ROOT
    / "records"
    / "system"
    / "agent_registry_latest.json"
)
NOTION_SYNC_PREVIEW_RECORD_PATH = (
    PROJECT_ROOT
    / "records"
    / "system"
    / "notion_sync_preview_latest.json"
)
SYSTEM_OUTPUT_CHANNEL = "system"


def load_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Required file not found: {path}")

    return json.loads(path.read_text(encoding="utf-8-sig"))


def load_schema() -> dict:
    return load_json(BASE_DIR / "schema.json")


def get_relative_path(path: Path) -> str:
    return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")


def env_status(env_key: str) -> dict:
    value = os.getenv(env_key)

    return {
        "env_key": env_key,
        "is_set": bool(value),
        "safe_preview": "***set***" if value else None,
    }


def build_notion_targets(mapping_data: dict) -> dict:
    targets = {}

    for database_name, database_config in (
        mapping_data["databases"].items()
    ):
        env_key = database_config["env_key"]
        status = env_status(env_key)

        targets[database_name] = {
            "env_key": env_key,
            "database_id_available": status["is_set"],
            "sync_status": database_config["sync_status"],
            "source": database_config["source"],
        }

    return targets


def build_ai_agent_rows(
    agent_registry_data: dict,
) -> list[dict]:
    rows = []

    for item in agent_registry_data.get("agents", []):
        rows.append(
            {
                "database": "ai_agents",
                "operation": "upsert_preview",
                "key": item["agent_name"],
                "properties": {
                    "agent_name": item["agent_name"],
                    "category": item["category"],
                    "implementation_status": item[
                        "implementation_status"
                    ],
                    "output_status": item.get("output_status"),
                    "next_agent": item.get("next_agent"),
                    "has_latest_output": item.get(
                        "has_latest_output"
                    ),
                    "latest_output_path": item.get(
                        "latest_output_path"
                    ),
                    "run_py": item.get(
                        "source_paths",
                        {},
                    ).get("run_py"),
                    "schema_json": item.get(
                        "source_paths",
                        {},
                    ).get("schema_json"),
                },
            }
        )

    return rows


def build_sync_preview(
    *,
    channel_filter: str | None,
    mapping_data: dict,
    agent_registry_data: dict,
) -> dict:
    ai_agent_rows = build_ai_agent_rows(
        agent_registry_data
    )
    youtube_channel_rows = build_youtube_channel_rows(
        project_root=PROJECT_ROOT,
        channel_filter=channel_filter,
    )
    publishing_queue_rows = build_publishing_queue_rows(
        project_root=PROJECT_ROOT,
        channel_filter=channel_filter,
    )

    first_scope = mapping_data.get("first_sync_scope", [])

    rows_by_database = {
        "ai_agents": ai_agent_rows,
        "youtube_channels": youtube_channel_rows,
        "publishing_queue": publishing_queue_rows,
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
        "total_preview_rows": sum(
            len(rows)
            for rows in scoped_rows.values()
        ),
    }


def write_preview_record(
    final_output: dict,
) -> Path:
    NOTION_SYNC_PREVIEW_RECORD_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    record = {
        "record_type": "notion_sync_preview",
        "version": "2.0",
        "created_at": datetime.now().isoformat(
            timespec="seconds"
        ),
        "channel": SYSTEM_OUTPUT_CHANNEL,
        "channels": final_output["summary"][
            "channel_keys"
        ],
        "status": final_output["status"],
        "summary": final_output["summary"],
        "notion_targets": final_output[
            "notion_targets"
        ],
        "sync_preview": final_output["sync_preview"],
        "next_step": (
            "review_multichannel_preview_then_run_apply"
        ),
    }

    NOTION_SYNC_PREVIEW_RECORD_PATH.write_text(
        json.dumps(
            record,
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    return NOTION_SYNC_PREVIEW_RECORD_PATH


def build_output(
    *,
    channel_filter: str | None,
    mapping_data: dict,
    agent_registry_data: dict,
    record_path: Path | None,
) -> dict:
    notion_targets = build_notion_targets(
        mapping_data
    )
    sync_preview = build_sync_preview(
        channel_filter=channel_filter,
        mapping_data=mapping_data,
        agent_registry_data=agent_registry_data,
    )
    channel_keys = build_channel_keys(
        project_root=PROJECT_ROOT,
        channel_filter=channel_filter,
    )

    missing_first_scope_env = [
        database
        for database in mapping_data.get(
            "first_sync_scope",
            [],
        )
        if not notion_targets.get(
            database,
            {},
        ).get("database_id_available")
    ]

    return {
        "agent": "notion_sync_dry_run",
        "version": "2.0",
        "channel": SYSTEM_OUTPUT_CHANNEL,
        "status": "preview_ready",
        "summary": {
            "first_sync_scope": mapping_data.get(
                "first_sync_scope",
                [],
            ),
            "channel_count": len(channel_keys),
            "channel_keys": channel_keys,
            "total_preview_rows": sync_preview[
                "total_preview_rows"
            ],
            "missing_first_scope_database_ids": (
                missing_first_scope_env
            ),
            "notion_api_key_available": bool(
                os.getenv("NOTION_API_KEY")
            ),
            "dry_run_only": True,
            "publishing_queue_source": (
                "records/run_contexts"
            ),
            "next_step": (
                "review_multichannel_preview_then_run_apply"
            ),
        },
        "notion_targets": notion_targets,
        "sync_preview": sync_preview,
        "record": {
            "record_written": record_path is not None,
            "record_path": (
                get_relative_path(record_path)
                if record_path
                else None
            ),
        },
        "metadata": {
            "next_agent": "notion_os_sync_runner",
        },
    }


def validate_multichannel_contract(
    final_output: dict,
) -> None:
    youtube_rows = (
        final_output
        .get("sync_preview", {})
        .get("rows_by_database", {})
        .get("youtube_channels", [])
    )
    queue_rows = (
        final_output
        .get("sync_preview", {})
        .get("rows_by_database", {})
        .get("publishing_queue", [])
    )
    expected_channels = set(
        final_output["summary"]["channel_keys"]
    )
    youtube_channels = {
        row.get("key")
        for row in youtube_rows
    }

    if youtube_channels != expected_channels:
        raise RuntimeError(
            "YouTube channel preview mismatch. "
            f"Expected {sorted(expected_channels)}, "
            f"got {sorted(youtube_channels)}."
        )

    for row in queue_rows:
        key = str(row.get("key", ""))
        source_record = str(
            row.get("properties", {}).get(
                "source_record",
                "",
            )
        )

        if key == "publisher_latest":
            raise RuntimeError(
                "publisher_latest is not allowed in "
                "Publishing Queue."
            )

        if ":" not in key:
            raise RuntimeError(
                "Publishing Queue key must be "
                "channel:video_id."
            )

        if not source_record.startswith(
            "records/run_contexts/"
        ):
            raise RuntimeError(
                "Publishing Queue must use run-context "
                "records as source of truth."
            )

        if source_record.endswith("latest.json"):
            raise RuntimeError(
                "latest.json is not allowed as a "
                "Publishing Queue source."
            )


def print_summary(
    final_output: dict,
    latest_path: Path,
) -> None:
    print(
        "Notion Sync Dry-Run Agent completed "
        "successfully."
    )
    print(f"Status: {final_output['status']}")
    print(
        "Channels: "
        + ", ".join(
            final_output["summary"]["channel_keys"]
        )
    )
    print(
        "Total preview rows: "
        f"{final_output['summary']['total_preview_rows']}"
    )
    print(
        "Notion API key available: "
        f"{final_output['summary']['notion_api_key_available']}"
    )
    print(
        "Missing DB IDs: "
        f"{final_output['summary']['missing_first_scope_database_ids']}"
    )
    print(
        "Publishing Queue source: "
        f"{final_output['summary']['publishing_queue_source']}"
    )
    print(
        "Record path: "
        f"{final_output['record']['record_path']}"
    )
    print("")
    print("Row counts:")

    for database, count in (
        final_output["sync_preview"][
            "row_counts"
        ].items()
    ):
        print(f"- {database}: {count}")

    print(f"Output saved to: {latest_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create a system-level multi-channel "
            "Notion sync preview."
        )
    )
    parser.add_argument(
        "--channel",
        default="all",
        help=(
            "Optional channel filter. Default: all."
        ),
    )
    parser.add_argument(
        "--no-record",
        action="store_true",
        help=(
            "Do not write "
            "records/system/notion_sync_preview_latest.json"
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    channel_filter = normalize_channel_filter(
        args.channel
    )

    load_dotenv(PROJECT_ROOT / ".env")

    mapping_data = load_json(
        NOTION_MAPPING_PATH
    )
    agent_registry_data = load_json(
        AGENT_REGISTRY_PATH
    )

    temp_output = build_output(
        channel_filter=channel_filter,
        mapping_data=mapping_data,
        agent_registry_data=agent_registry_data,
        record_path=None,
    )
    validate_multichannel_contract(temp_output)

    record_path = None

    if not args.no_record:
        record_path = write_preview_record(
            temp_output
        )

    final_output = build_output(
        channel_filter=channel_filter,
        mapping_data=mapping_data,
        agent_registry_data=agent_registry_data,
        record_path=record_path,
    )
    validate_multichannel_contract(final_output)

    validate(
        instance=final_output,
        schema=load_schema(),
    )

    latest_path = save_output(
        channel=SYSTEM_OUTPUT_CHANNEL,
        data=final_output,
    )

    print_summary(
        final_output=final_output,
        latest_path=latest_path,
    )


if __name__ == "__main__":
    main()
