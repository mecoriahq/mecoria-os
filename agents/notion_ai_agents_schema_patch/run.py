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
RECORD_PATH = PROJECT_ROOT / "records" / "system" / "notion_ai_agents_schema_patch_latest.json"
SCHEMA_PATH = BASE_DIR / "schema.json"

TARGET_KEY = "ai_agents"
TARGET_ENV_KEY = "NOTION_AI_AGENTS_DB_ID"

DESIRED_PROPERTIES = {
    "Agent Category": {"rich_text": {}},
    "Implementation Status": {"rich_text": {}},
    "Output Status": {"rich_text": {}},
    "Next Agent": {"rich_text": {}},
    "Has Latest Output": {"checkbox": {}},
    "Latest Output Path": {"rich_text": {}},
    "Run Path": {"rich_text": {}},
    "Schema Path": {"rich_text": {}}
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


def get_database(token: str, database_id: str) -> dict:
    response = notion_request(
        method="GET",
        path=f"/databases/{quote(database_id)}",
        token=token
    )

    if not response.get("ok"):
        raise RuntimeError(f"Could not retrieve database: {response}")

    return response["data"]


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env", override=True)

    token = os.getenv("NOTION_API_KEY")
    database_id = os.getenv(TARGET_ENV_KEY)

    if not token:
        raise RuntimeError("NOTION_API_KEY missing from .env")

    if not database_id:
        raise RuntimeError(f"{TARGET_ENV_KEY} missing from .env")

    before_database = get_database(token, database_id)
    before_properties = before_database.get("properties", {})
    before_property_names = sorted(before_properties.keys())

    missing_properties = {
        name: config
        for name, config in DESIRED_PROPERTIES.items()
        if name not in before_properties
    }

    skipped_existing_properties = [
        name
        for name in DESIRED_PROPERTIES.keys()
        if name in before_properties
    ]

    if missing_properties:
        patch_response = notion_request(
            method="PATCH",
            path=f"/databases/{quote(database_id)}",
            token=token,
            body={
                "properties": missing_properties
            }
        )

        patch_success = bool(patch_response.get("ok"))
    else:
        patch_response = {
            "ok": True,
            "status_code": 200,
            "data": before_database
        }
        patch_success = True

    after_database = get_database(token, database_id) if patch_success else before_database
    after_properties = after_database.get("properties", {})
    after_property_names = sorted(after_properties.keys())

    added_properties = [
        name
        for name in missing_properties.keys()
        if name in after_properties
    ]

    if not patch_success:
        status = "schema_patch_failed"
        next_step = "fix_database_update_permission_or_patch_payload"
    elif missing_properties and len(added_properties) == len(missing_properties):
        status = "schema_patch_applied"
        next_step = "rerun_ai_agents_sync_dry_run"
    elif not missing_properties:
        status = "schema_patch_not_needed"
        next_step = "rerun_ai_agents_sync_dry_run"
    else:
        status = "schema_patch_partial"
        next_step = "inspect_missing_properties"

    record = {
        "record_type": "notion_ai_agents_schema_patch",
        "version": "1.0",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "status": status,
        "summary": {
            "target_database": TARGET_KEY,
            "database_title": get_title(after_database),
            "desired_property_count": len(DESIRED_PROPERTIES),
            "missing_property_count_before_patch": len(missing_properties),
            "added_property_count": len(added_properties),
            "skipped_existing_property_count": len(skipped_existing_properties),
            "write_operations_performed": bool(missing_properties),
            "next_step": next_step
        },
        "target": {
            "env_key": TARGET_ENV_KEY,
            "database_id_available": True,
            "database_id": database_id,
            "database_title": get_title(after_database)
        },
        "schema_patch": {
            "desired_properties": [
                {
                    "name": name,
                    "type": list(config.keys())[0]
                }
                for name, config in DESIRED_PROPERTIES.items()
            ],
            "missing_properties_before_patch": list(missing_properties.keys()),
            "added_properties": added_properties,
            "skipped_existing_properties": skipped_existing_properties,
            "before_property_names": before_property_names,
            "after_property_names": after_property_names,
            "patch_status_code": patch_response.get("status_code"),
            "patch_error": patch_response.get("error")
        },
        "security": {
            "token_saved_to_output": False,
            "token_printed_to_terminal": False,
            "openai_key_saved_to_output": False,
            "operation_scope": "add_missing_ai_agents_database_properties_only"
        }
    }

    validate(record, load_json(SCHEMA_PATH))

    save_json(record, OUTPUT_PATH)
    save_json(record, RECORD_PATH)

    print("Notion AI Agents Schema Patch completed.")
    print(f"Status: {record['status']}")
    print(f"Database title: {record['summary']['database_title']}")
    print(f"Missing before patch: {record['summary']['missing_property_count_before_patch']}")
    print(f"Added properties: {record['schema_patch']['added_properties']}")
    print(f"Skipped existing: {record['schema_patch']['skipped_existing_properties']}")
    print(f"Write operations performed: {record['summary']['write_operations_performed']}")

    if patch_response.get("error"):
        print(f"Patch error: {patch_response.get('error')}")

    print(f"Record path: {RECORD_PATH.relative_to(PROJECT_ROOT)}")
    print(f"Output saved to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
