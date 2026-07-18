import json
import os
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dotenv import load_dotenv
from jsonschema import validate

from output import save_json


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent.parent

OUTPUT_PATH = BASE_DIR / "output" / "system" / "latest.json"
RECORD_PATH = PROJECT_ROOT / "records" / "system" / "notion_write_test_latest.json"
SCHEMA_PATH = BASE_DIR / "schema.json"
CONNECTION_TEST_RECORD = PROJECT_ROOT / "records" / "system" / "notion_connection_test_latest.json"

TARGET_KEY = "ai_agents"
TARGET_ENV_KEY = "NOTION_AI_AGENTS_DB_ID"
TEST_PAGE_TITLE = "Mecoria OS Sync Test"


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


def get_title_property_name() -> str:
    if not CONNECTION_TEST_RECORD.exists():
        return "Name"

    record = load_json(CONNECTION_TEST_RECORD)

    for target in record.get("targets", []):
        if target.get("key") != TARGET_KEY:
            continue

        title_properties = target.get("title_property_names") or []

        if title_properties:
            return title_properties[0]

    return "Name"


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env", override=True)

    token = os.getenv("NOTION_API_KEY")
    database_id = os.getenv(TARGET_ENV_KEY)
    title_property_name = get_title_property_name()

    if not token:
        raise RuntimeError("NOTION_API_KEY missing from .env")

    if not database_id:
        raise RuntimeError(f"{TARGET_ENV_KEY} missing from .env")

    create_payload = {
        "parent": {
            "database_id": database_id
        },
        "properties": {
            title_property_name: {
                "title": [
                    {
                        "type": "text",
                        "text": {
                            "content": TEST_PAGE_TITLE
                        }
                    }
                ]
            }
        }
    }

    create_response = notion_request(
        method="POST",
        path="/pages",
        token=token,
        body=create_payload
    )

    write_success = bool(create_response.get("ok"))

    if write_success:
        page = create_response["data"]

        status = "write_test_passed"
        target = {
            "key": TARGET_KEY,
            "env_key": TARGET_ENV_KEY,
            "database_id_available": True,
            "database_id": database_id,
            "title_property_name": title_property_name,
            "operation": "create_single_test_page",
            "created_page_id": page.get("id"),
            "created_page_url": page.get("url"),
            "created_page_title": TEST_PAGE_TITLE
        }
        next_step = "build_ai_agents_sync_agent_with_dry_run_first"
        error = None

    else:
        status = "write_test_failed"
        target = {
            "key": TARGET_KEY,
            "env_key": TARGET_ENV_KEY,
            "database_id_available": True,
            "database_id": database_id,
            "title_property_name": title_property_name,
            "operation": "create_single_test_page",
            "status_code": create_response.get("status_code"),
            "error": create_response.get("error")
        }
        next_step = "fix_write_permissions_or_database_schema"
        error = create_response.get("error")

    record = {
        "record_type": "notion_write_test",
        "version": "1.0",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "status": status,
        "summary": {
            "target_database": TARGET_KEY,
            "write_operations_performed": write_success,
            "test_page_title": TEST_PAGE_TITLE,
            "next_step": next_step,
            "error": error
        },
        "target": target,
        "security": {
            "token_saved_to_output": False,
            "token_printed_to_terminal": False,
            "openai_key_saved_to_output": False,
            "write_scope": "single_test_page_only"
        }
    }

    validate(record, load_json(SCHEMA_PATH))

    save_json(record, OUTPUT_PATH)
    save_json(record, RECORD_PATH)

    print("Notion Write Test completed.")
    print(f"Status: {record['status']}")
    print(f"Target database: {TARGET_KEY}")
    print(f"Title property: {title_property_name}")
    print(f"Write operations performed: {write_success}")

    if write_success:
        print(f"Created test page title: {TEST_PAGE_TITLE}")
        print(f"Created page URL: {target.get('created_page_url')}")
    else:
        print(f"Status code: {target.get('status_code')}")
        print(f"Error: {target.get('error')}")

    print(f"Record path: {RECORD_PATH.relative_to(PROJECT_ROOT)}")
    print(f"Output saved to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
