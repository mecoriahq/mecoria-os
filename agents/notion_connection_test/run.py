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

OUTPUT_PATH = BASE_DIR / "output" / "system" / "latest.json"
RECORD_PATH = PROJECT_ROOT / "records" / "system" / "notion_connection_test_latest.json"
SCHEMA_PATH = BASE_DIR / "schema.json"

TARGETS = [
    {
        "key": "ai_agents",
        "env_key": "NOTION_AI_AGENTS_DB_ID",
        "expected_purpose": "technical AI agent registry"
    },
    {
        "key": "youtube_channels",
        "env_key": "NOTION_YOUTUBE_CHANNELS_DB_ID",
        "expected_purpose": "YouTube channel dashboard"
    },
    {
        "key": "publishing_queue",
        "env_key": "NOTION_PUBLISHING_QUEUE_DB_ID",
        "expected_purpose": "publishing queue / release tracker"
    }
]


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

    return {
        "message": str(error_payload)
    }


def notion_get(path: str, token: str, notion_version: str) -> dict:
    url = f"https://api.notion.com/v1{path}"

    request = Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Notion-Version": notion_version,
            "Content-Type": "application/json"
        },
        method="GET"
    )

    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
            data = json.loads(raw) if raw else {}

            return {
                "ok": True,
                "status_code": response.status,
                "data": data
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
            "error": {
                "message": str(error.reason)
            }
        }

    except Exception as error:
        return {
            "ok": False,
            "status_code": None,
            "error": {
                "message": str(error)
            }
        }


def get_title(notion_object: dict) -> str | None:
    title = notion_object.get("title")

    if isinstance(title, list):
        plain = "".join(part.get("plain_text", "") for part in title if isinstance(part, dict)).strip()
        if plain:
            return plain

    if isinstance(title, str) and title.strip():
        return title.strip()

    name = notion_object.get("name")
    if isinstance(name, str) and name.strip():
        return name.strip()

    return None


def summarize_properties(properties: dict) -> list[dict]:
    if not isinstance(properties, dict):
        return []

    rows = []

    for name, value in sorted(properties.items()):
        if isinstance(value, dict):
            property_type = value.get("type", "unknown")
        else:
            property_type = "unknown"

        rows.append({
            "name": name,
            "type": property_type
        })

    return rows


def summarize_accessible_target(
    *,
    key: str,
    env_key: str,
    database_id: str,
    api_mode: str,
    api_version: str,
    notion_object: dict,
    data_source_id: str | None = None
) -> dict:
    properties = summarize_properties(notion_object.get("properties", {}))
    title = get_title(notion_object)

    title_property_names = [
        item["name"]
        for item in properties
        if item["type"] == "title"
    ]

    return {
        "key": key,
        "env_key": env_key,
        "database_id_available": True,
        "database_id": database_id,
        "connection_status": "accessible",
        "api_mode": api_mode,
        "api_version": api_version,
        "title": title,
        "data_source_id": data_source_id,
        "property_count": len(properties),
        "title_property_names": title_property_names,
        "properties": properties
    }


def try_legacy_database(key: str, env_key: str, database_id: str, token: str) -> dict:
    response = notion_get(
        f"/databases/{quote(database_id)}",
        token,
        "2022-06-28"
    )

    if response["ok"]:
        return summarize_accessible_target(
            key=key,
            env_key=env_key,
            database_id=database_id,
            api_mode="legacy_database",
            api_version="2022-06-28",
            notion_object=response["data"]
        )

    return {
        "connection_status": "failed",
        "api_mode": "legacy_database",
        "api_version": "2022-06-28",
        "status_code": response.get("status_code"),
        "error": response.get("error")
    }


def try_current_database_then_data_source(key: str, env_key: str, database_id: str, token: str) -> dict:
    database_response = notion_get(
        f"/databases/{quote(database_id)}",
        token,
        "2025-09-03"
    )

    if not database_response["ok"]:
        return {
            "connection_status": "failed",
            "api_mode": "current_database",
            "api_version": "2025-09-03",
            "status_code": database_response.get("status_code"),
            "error": database_response.get("error")
        }

    database_payload = database_response["data"]
    data_sources = database_payload.get("data_sources", [])

    if not data_sources:
        return {
            "connection_status": "database_accessible_but_no_data_sources_found",
            "api_mode": "current_database",
            "api_version": "2025-09-03",
            "database_title": get_title(database_payload),
            "data_sources": []
        }

    data_source_id = data_sources[0].get("id")

    if not data_source_id:
        return {
            "connection_status": "database_accessible_but_data_source_id_missing",
            "api_mode": "current_database",
            "api_version": "2025-09-03",
            "database_title": get_title(database_payload),
            "data_sources": data_sources
        }

    data_source_response = notion_get(
        f"/data_sources/{quote(data_source_id)}",
        token,
        "2025-09-03"
    )

    if not data_source_response["ok"]:
        return {
            "connection_status": "database_accessible_but_data_source_failed",
            "api_mode": "current_data_source",
            "api_version": "2025-09-03",
            "database_title": get_title(database_payload),
            "data_source_id": data_source_id,
            "status_code": data_source_response.get("status_code"),
            "error": data_source_response.get("error")
        }

    return summarize_accessible_target(
        key=key,
        env_key=env_key,
        database_id=database_id,
        api_mode="current_data_source",
        api_version="2025-09-03",
        notion_object=data_source_response["data"],
        data_source_id=data_source_id
    )


def try_direct_data_source(key: str, env_key: str, database_id: str, token: str) -> dict:
    response = notion_get(
        f"/data_sources/{quote(database_id)}",
        token,
        "2025-09-03"
    )

    if response["ok"]:
        return summarize_accessible_target(
            key=key,
            env_key=env_key,
            database_id=database_id,
            api_mode="direct_data_source",
            api_version="2025-09-03",
            notion_object=response["data"],
            data_source_id=database_id
        )

    return {
        "connection_status": "failed",
        "api_mode": "direct_data_source",
        "api_version": "2025-09-03",
        "status_code": response.get("status_code"),
        "error": response.get("error")
    }


def check_target(target: dict, token: str | None) -> dict:
    key = target["key"]
    env_key = target["env_key"]
    database_id = os.getenv(env_key)

    if not database_id:
        return {
            "key": key,
            "env_key": env_key,
            "database_id_available": False,
            "connection_status": "missing_database_id",
            "expected_purpose": target["expected_purpose"]
        }

    if not token:
        return {
            "key": key,
            "env_key": env_key,
            "database_id_available": True,
            "connection_status": "missing_notion_api_key",
            "expected_purpose": target["expected_purpose"]
        }

    attempts = []

    legacy_attempt = try_legacy_database(key, env_key, database_id, token)
    attempts.append(legacy_attempt)

    if legacy_attempt.get("connection_status") == "accessible":
        legacy_attempt["expected_purpose"] = target["expected_purpose"]
        legacy_attempt["attempts_used"] = ["legacy_database"]
        return legacy_attempt

    current_attempt = try_current_database_then_data_source(key, env_key, database_id, token)
    attempts.append(current_attempt)

    if current_attempt.get("connection_status") == "accessible":
        current_attempt["expected_purpose"] = target["expected_purpose"]
        current_attempt["attempts_used"] = ["legacy_database", "current_database_then_data_source"]
        current_attempt["legacy_error"] = legacy_attempt.get("error")
        return current_attempt

    direct_data_source_attempt = try_direct_data_source(key, env_key, database_id, token)
    attempts.append(direct_data_source_attempt)

    if direct_data_source_attempt.get("connection_status") == "accessible":
        direct_data_source_attempt["expected_purpose"] = target["expected_purpose"]
        direct_data_source_attempt["attempts_used"] = ["legacy_database", "current_database_then_data_source", "direct_data_source"]
        direct_data_source_attempt["legacy_error"] = legacy_attempt.get("error")
        return direct_data_source_attempt

    return {
        "key": key,
        "env_key": env_key,
        "database_id_available": True,
        "database_id": database_id,
        "connection_status": "failed",
        "expected_purpose": target["expected_purpose"],
        "attempts": attempts
    }


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")

    token = os.getenv("NOTION_API_KEY")
    notion_api_key_available = bool(token)

    checked_targets = [
        check_target(target, token)
        for target in TARGETS
    ]

    accessible_targets = [
        target["key"]
        for target in checked_targets
        if target.get("connection_status") == "accessible"
    ]

    failed_targets = [
        target["key"]
        for target in checked_targets
        if target.get("connection_status") != "accessible"
    ]

    if not notion_api_key_available:
        status = "missing_credentials"
        next_step = "add_notion_api_key_to_env"
    elif len(accessible_targets) == len(TARGETS):
        status = "connection_ready"
        next_step = "build_one_database_write_test_for_ai_agents"
    elif accessible_targets:
        status = "connection_partial"
        next_step = "fix_failed_database_access_or_share_original_database"
    else:
        status = "connection_failed"
        next_step = "check_token_database_ids_and_connection_sharing"

    record = {
        "record_type": "notion_connection_test",
        "version": "1.0",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "status": status,
        "summary": {
            "total_targets": len(TARGETS),
            "accessible_target_count": len(accessible_targets),
            "failed_target_count": len(failed_targets),
            "accessible_targets": accessible_targets,
            "failed_targets": failed_targets,
            "notion_api_key_available": notion_api_key_available,
            "write_operations_performed": False,
            "next_step": next_step
        },
        "targets": checked_targets,
        "security": {
            "token_saved_to_output": False,
            "token_printed_to_terminal": False,
            "write_operations_performed": False
        }
    }

    validate(record, load_json(SCHEMA_PATH))

    save_json(record, OUTPUT_PATH)
    save_json(record, RECORD_PATH)

    print("Notion Connection Test completed.")
    print(f"Status: {record['status']}")
    print(f"Accessible targets: {len(accessible_targets)} / {len(TARGETS)}")
    print(f"Failed targets: {failed_targets}")
    print(f"Write operations performed: False")
    print(f"Record path: {RECORD_PATH.relative_to(PROJECT_ROOT)}")
    print("")

    for target in checked_targets:
        print(f"- {target['key']}: {target.get('connection_status')}")
        print(f"  api_mode: {target.get('api_mode')}")
        print(f"  title: {target.get('title')}")
        print(f"  property_count: {target.get('property_count')}")
        print(f"  title_properties: {target.get('title_property_names')}")
        print("")

    print(f"Output saved to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
