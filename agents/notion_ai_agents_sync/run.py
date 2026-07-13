import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from dotenv import load_dotenv
from jsonschema import validate

from output import save_json


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent.parent

OUTPUT_PATH = BASE_DIR / "output" / "hiddenova" / "latest.json"
RECORD_PATH = PROJECT_ROOT / "records" / "system" / "notion_ai_agents_sync_latest.json"
SCHEMA_PATH = BASE_DIR / "schema.json"
SOURCE_PREVIEW_PATH = PROJECT_ROOT / "records" / "system" / "notion_sync_preview_latest.json"

TARGET_ENV_KEY = "NOTION_AI_AGENTS_DB_ID"
TARGET_KEY = "ai_agents"

FIELD_CANDIDATES = {
    "category": ["Category", "Agent Category", "Type"],
    "implementation_status": ["Implementation Status", "Build Status", "Status"],
    "output_status": ["Output Status", "Latest Output Status", "Latest Status"],
    "next_agent": ["Next Agent", "Next Step", "Next"],
    "has_latest_output": ["Has Latest Output", "Output Exists", "Latest Output?"],
    "latest_output_path": ["Latest Output Path", "Output Path", "Latest Output"],
    "run_py": ["Run Path", "Run PY", "Run Script", "run_py"],
    "schema_json": ["Schema Path", "Schema JSON", "Schema", "schema_json"]
}

SAFE_WRITE_TYPES = {
    "rich_text",
    "checkbox",
    "url",
    "number"
}

CAUTIOUS_WRITE_TYPES = {
    "select",
    "status"
}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def safe_error(error_payload) -> dict:
    if isinstance(error_payload, dict):
        return {
            "object": error_payload.get("object"),
            "status": error_payload.get("status"),
            "code": error_payload.get("code"),
            "message": error_payload.get("message")
        }

    return {"message": str(error_payload)}


def notion_request(method: str, path: str, token: str, body: dict | None = None) -> dict:
    url = f"https://api.notion.com/v1{path}"

    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")

    request = Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json"
        },
        method=method
    )

    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
            payload = json.loads(raw) if raw else {}

            return {
                "ok": True,
                "status_code": response.status,
                "data": payload
            }

    except HTTPError as error:
        raw = error.read().decode("utf-8", errors="replace")

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"message": raw[:1000]}

        return {
            "ok": False,
            "status_code": error.code,
            "error": safe_error(payload)
        }

    except URLError as error:
        return {
            "ok": False,
            "status_code": None,
            "error": {"message": str(error.reason)}
        }

    except Exception as error:
        return {
            "ok": False,
            "status_code": None,
            "error": {"message": str(error)}
        }


def get_title(notion_object: dict) -> str | None:
    title = notion_object.get("title")

    if isinstance(title, list):
        plain = "".join(
            part.get("plain_text", "")
            for part in title
            if isinstance(part, dict)
        ).strip()

        if plain:
            return plain

    return None


def get_database_schema(token: str, database_id: str) -> dict:
    response = notion_request(
        method="GET",
        path=f"/databases/{quote(database_id)}",
        token=token
    )

    if not response.get("ok"):
        raise RuntimeError(f"Could not retrieve Notion database schema: {response}")

    return response["data"]


def get_title_property_name(properties: dict) -> str:
    for property_name, config in properties.items():
        if isinstance(config, dict) and config.get("type") == "title":
            return property_name

    return "Name"


def normalize_property_name(name: str) -> str:
    return name.strip().lower()


def find_property(properties: dict, candidates: list[str]) -> dict | None:
    normalized_lookup = {
        normalize_property_name(name): name
        for name in properties.keys()
    }

    for candidate in candidates:
        normalized = normalize_property_name(candidate)

        if normalized in normalized_lookup:
            property_name = normalized_lookup[normalized]
            config = properties[property_name]

            return {
                "notion_property_name": property_name,
                "notion_property_type": config.get("type", "unknown")
            }

    return None


def build_field_mapping(properties: dict) -> dict:
    title_property_name = get_title_property_name(properties)

    mapped = {
        "agent_name": {
            "source_field": "agent_name",
            "notion_property_name": title_property_name,
            "notion_property_type": "title",
            "write_policy": "required_title",
            "write_supported": True
        }
    }

    unmapped = []

    for source_field, candidates in FIELD_CANDIDATES.items():
        match = find_property(properties, candidates)

        if match:
            notion_type = match["notion_property_type"]

            if notion_type in SAFE_WRITE_TYPES:
                write_policy = "safe_write"
                write_supported = True
            elif notion_type in CAUTIOUS_WRITE_TYPES:
                write_policy = "cautious_write_later"
                write_supported = False
            else:
                write_policy = "unsupported_type"
                write_supported = False

            mapped[source_field] = {
                "source_field": source_field,
                "notion_property_name": match["notion_property_name"],
                "notion_property_type": notion_type,
                "write_policy": write_policy,
                "write_supported": write_supported
            }

        else:
            unmapped.append({
                "source_field": source_field,
                "candidate_names": candidates
            })

    return {
        "mapped": mapped,
        "unmapped": unmapped,
        "mapped_field_count": len(mapped),
        "unmapped_field_count": len(unmapped)
    }


def load_source_rows() -> list[dict]:
    if not SOURCE_PREVIEW_PATH.exists():
        raise RuntimeError(f"Source preview missing: {SOURCE_PREVIEW_PATH}")

    preview = load_json(SOURCE_PREVIEW_PATH)

    rows = (
        preview
        .get("sync_preview", {})
        .get("rows_by_database", {})
        .get("ai_agents", [])
    )

    if not rows:
        raise RuntimeError("No ai_agents rows found in notion sync preview.")

    normalized_rows = []

    for row in rows:
        props = row.get("properties", {})
        agent_name = props.get("agent_name") or row.get("key")

        normalized_rows.append({
            "key": row.get("key") or agent_name,
            "agent_name": agent_name,
            "category": props.get("category"),
            "implementation_status": props.get("implementation_status"),
            "output_status": props.get("output_status"),
            "next_agent": props.get("next_agent"),
            "has_latest_output": props.get("has_latest_output"),
            "latest_output_path": props.get("latest_output_path"),
            "run_py": props.get("run_py"),
            "schema_json": props.get("schema_json")
        })

    return normalized_rows


def is_syncable_agent(row: dict) -> bool:
    agent_name = row.get("agent_name") or ""
    implementation_status = row.get("implementation_status")

    if agent_name.startswith("_"):
        return False

    if implementation_status == "non_agent_or_support_folder":
        return False

    return True


def notion_rich_text(value) -> dict:
    if value is None:
        value = ""

    text = str(value)

    return {
        "rich_text": [
            {
                "type": "text",
                "text": {
                    "content": text[:2000]
                }
            }
        ]
    }


def notion_title(value) -> dict:
    return {
        "title": [
            {
                "type": "text",
                "text": {
                    "content": str(value)[:2000]
                }
            }
        ]
    }


def notion_checkbox(value) -> dict:
    return {
        "checkbox": bool(value)
    }


def build_properties_payload(row: dict, field_mapping: dict) -> dict:
    mapped = field_mapping["mapped"]
    payload = {}

    title_mapping = mapped["agent_name"]
    title_property_name = title_mapping["notion_property_name"]
    payload[title_property_name] = notion_title(row.get("agent_name"))

    for source_field, mapping in mapped.items():
        if source_field == "agent_name":
            continue

        if not mapping.get("write_supported"):
            continue

        notion_property_name = mapping["notion_property_name"]
        notion_property_type = mapping["notion_property_type"]
        value = row.get(source_field)

        if notion_property_type == "rich_text":
            payload[notion_property_name] = notion_rich_text(value)
        elif notion_property_type == "checkbox":
            payload[notion_property_name] = notion_checkbox(value)
        elif notion_property_type == "number":
            try:
                payload[notion_property_name] = {"number": float(value)}
            except (TypeError, ValueError):
                continue
        elif notion_property_type == "url":
            text = str(value or "")
            if text.startswith("http://") or text.startswith("https://"):
                payload[notion_property_name] = {"url": text}

    return payload


def build_planned_operations(rows: list[dict], field_mapping: dict) -> list[dict]:
    operations = []

    for row in rows:
        properties_payload = build_properties_payload(row, field_mapping)

        operations.append({
            "key": row["key"],
            "agent_name": row["agent_name"],
            "operation": "upsert_preview",
            "write_payload_property_names": list(properties_payload.keys()),
            "mapped_source_values": row,
            "write_payload_field_count": len(properties_payload)
        })

    return operations


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    load_dotenv(PROJECT_ROOT / ".env", override=True)

    token = os.getenv("NOTION_API_KEY")
    database_id = os.getenv(TARGET_ENV_KEY)

    if not token:
        raise RuntimeError("NOTION_API_KEY missing from .env")

    if not database_id:
        raise RuntimeError(f"{TARGET_ENV_KEY} missing from .env")

    database = get_database_schema(token, database_id)
    database_title = get_title(database)
    properties = database.get("properties", {})
    title_property_name = get_title_property_name(properties)

    source_rows = load_source_rows()
    excluded_rows = [
        row
        for row in source_rows
        if not is_syncable_agent(row)
    ]
    syncable_rows = [
        row
        for row in source_rows
        if is_syncable_agent(row)
    ]

    if args.limit is not None:
        selected_rows = syncable_rows[:args.limit]
    else:
        selected_rows = syncable_rows

    field_mapping = build_field_mapping(properties)
    planned_operations = build_planned_operations(selected_rows, field_mapping)

    record = {
        "record_type": "notion_ai_agents_sync",
        "version": "1.0",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "status": "dry_run_ready",
        "summary": {
            "target_database": TARGET_KEY,
            "database_title": database_title,
            "source_row_count": len(source_rows),
            "syncable_row_count": len(syncable_rows),
            "selected_row_count": len(selected_rows),
            "excluded_row_count": len(excluded_rows),
            "excluded_keys": [row["key"] for row in excluded_rows],
            "write_operations_performed": False,
            "mapped_field_count": field_mapping["mapped_field_count"],
            "unmapped_field_count": field_mapping["unmapped_field_count"],
            "next_step": "review_mapping_then_run_limited_apply_test"
        },
        "target": {
            "env_key": TARGET_ENV_KEY,
            "database_id_available": True,
            "database_title": database_title,
            "title_property_name": title_property_name,
            "notion_property_count": len(properties),
            "notion_properties": [
                {
                    "name": name,
                    "type": config.get("type", "unknown")
                }
                for name, config in sorted(properties.items())
            ]
        },
        "field_mapping": field_mapping,
        "planned_operations": planned_operations,
        "security": {
            "token_saved_to_output": False,
            "token_printed_to_terminal": False,
            "openai_key_saved_to_output": False,
            "write_operations_performed": False,
            "mode": "dry_run_only"
        }
    }

    validate(record, load_json(SCHEMA_PATH))

    save_json(record, OUTPUT_PATH)
    save_json(record, RECORD_PATH)

    print("Notion AI Agents Sync Dry-Run completed.")
    print(f"Status: {record['status']}")
    print(f"Database title: {database_title}")
    print(f"Source rows: {len(source_rows)}")
    print(f"Syncable rows: {len(syncable_rows)}")
    print(f"Selected rows: {len(selected_rows)}")
    print(f"Excluded rows: {len(excluded_rows)}")
    print(f"Write operations performed: False")
    print("")
    print("Field mapping:")

    for source_field, mapping in field_mapping["mapped"].items():
        print(
            f"- {source_field} -> "
            f"{mapping['notion_property_name']} "
            f"({mapping['notion_property_type']}) "
            f"[{mapping['write_policy']}]"
        )

    if field_mapping["unmapped"]:
        print("")
        print("Unmapped fields:")

        for item in field_mapping["unmapped"]:
            print(f"- {item['source_field']}")

    print("")
    print(f"Record path: {RECORD_PATH.relative_to(PROJECT_ROOT)}")
    print(f"Output saved to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
