import json
import sys
from pathlib import Path

from dotenv import load_dotenv
from jsonschema import validate

from output import save_output


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent.parent

sys.path.insert(0, str(PROJECT_ROOT))

from core.execution.manager import ExecutionManager


DEFAULT_CHANNEL = "hiddenova"
DEFAULT_PLATFORM = "youtube"


def load_json(file_path: Path) -> dict:
    if not file_path.exists():
        raise FileNotFoundError(f"Required file not found: {file_path}")

    return json.loads(file_path.read_text(encoding="utf-8"))


def load_schema() -> dict:
    return load_json(BASE_DIR / "schema.json")


def get_script_latest_path(channel: str) -> Path:
    return PROJECT_ROOT / "agents" / "script" / "output" / channel.lower() / "latest.json"


def get_seo_latest_path(channel: str) -> Path:
    return PROJECT_ROOT / "agents" / "seo" / "output" / channel.lower() / "latest.json"


def get_image_generation_latest_path(channel: str) -> Path:
    return PROJECT_ROOT / "agents" / "image_generation" / "output" / channel.lower() / "latest.json"


def get_image_qa_latest_path(channel: str) -> Path:
    return PROJECT_ROOT / "agents" / "image_qa" / "output" / channel.lower() / "latest.json"


def get_relative_path(path: Path) -> str:
    return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")


def get_execution_context(channel: str) -> dict:
    manager = ExecutionManager(
        channel=channel,
        pipeline="image"
    )

    return manager.load()


def build_blocked_output(
    channel: str,
    reason: str,
    execution_context: dict | None = None
) -> dict:
    context_status = execution_context["status"] if execution_context else "missing"
    context_next_agent = execution_context["next_agent"] if execution_context else None

    return {
        "agent": "publisher",
        "version": "1.0",
        "channel": channel,
        "platform": DEFAULT_PLATFORM,
        "status": "blocked",
        "publishing_package": {
            "video_metadata": {
                "title": "",
                "description": "",
                "tags": [],
                "hashtags": [],
                "chapters": []
            },
            "assets": {
                "script_reference": "",
                "seo_reference": "",
                "thumbnail_image_path": "",
                "video_file_path": None
            },
            "readiness": {
                "metadata_ready": False,
                "thumbnail_ready": False,
                "video_ready": False,
                "upload_ready": False,
                "blocking_notes": [
                    reason
                ]
            }
        },
        "source": {
            "source_agents": [],
            "execution_context_status": context_status,
            "execution_context_next_agent": context_next_agent
        },
        "metadata": {
            "next_agent": None
        }
    }


def build_publishing_package(
    script_data: dict,
    seo_data: dict,
    image_generation_data: dict,
    image_qa_data: dict,
    execution_context: dict,
    script_path: Path,
    seo_path: Path
) -> dict:
    seo = seo_data["seo"]

    image_approved = image_qa_data["status"] == "approved"
    context_ready = execution_context["next_agent"] == "publisher"

    blocking_notes = []

    if not image_approved:
        blocking_notes.append("Image QA is not approved.")

    if not context_ready:
        blocking_notes.append("Execution Context next_agent is not publisher.")

    thumbnail_image_path = image_generation_data["image"]["relative_path"]

    metadata_ready = bool(
        seo.get("video_title")
        and seo.get("description")
        and seo.get("tags")
    )

    thumbnail_ready = image_approved and bool(thumbnail_image_path)
    video_ready = False
    upload_ready = metadata_ready and thumbnail_ready and video_ready

    if not video_ready:
        blocking_notes.append("Video file is not available yet.")

    status = "metadata_ready" if metadata_ready and thumbnail_ready else "blocked"

    return {
        "agent": "publisher",
        "version": "1.0",
        "channel": script_data["channel"],
        "platform": DEFAULT_PLATFORM,
        "status": status,
        "publishing_package": {
            "video_metadata": {
                "title": seo["video_title"],
                "description": seo["description"],
                "tags": seo["tags"],
                "hashtags": seo["hashtags"],
                "chapters": seo.get("chapters", [])
            },
            "assets": {
                "script_reference": get_relative_path(script_path),
                "seo_reference": get_relative_path(seo_path),
                "thumbnail_image_path": thumbnail_image_path,
                "video_file_path": None
            },
            "readiness": {
                "metadata_ready": metadata_ready,
                "thumbnail_ready": thumbnail_ready,
                "video_ready": video_ready,
                "upload_ready": upload_ready,
                "blocking_notes": blocking_notes
            }
        },
        "source": {
            "source_agents": [
                "script",
                "seo",
                "image_generation",
                "image_qa",
                "execution_context"
            ],
            "execution_context_status": execution_context["status"],
            "execution_context_next_agent": execution_context["next_agent"]
        },
        "metadata": {
            "next_agent": None
        }
    }


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")

    script_path = get_script_latest_path(DEFAULT_CHANNEL)
    seo_path = get_seo_latest_path(DEFAULT_CHANNEL)
    image_generation_path = get_image_generation_latest_path(DEFAULT_CHANNEL)
    image_qa_path = get_image_qa_latest_path(DEFAULT_CHANNEL)

    script_data = load_json(script_path)
    seo_data = load_json(seo_path)
    image_generation_data = load_json(image_generation_path)
    image_qa_data = load_json(image_qa_path)

    execution_context = get_execution_context(DEFAULT_CHANNEL)

    if image_qa_data["status"] != "approved":
        final_output = build_blocked_output(
            channel=image_qa_data["channel"],
            reason="Image QA is not approved.",
            execution_context=execution_context
        )
    elif execution_context["next_agent"] != "publisher":
        final_output = build_blocked_output(
            channel=image_qa_data["channel"],
            reason="Execution Context next_agent is not publisher.",
            execution_context=execution_context
        )
    else:
        final_output = build_publishing_package(
            script_data=script_data,
            seo_data=seo_data,
            image_generation_data=image_generation_data,
            image_qa_data=image_qa_data,
            execution_context=execution_context,
            script_path=script_path,
            seo_path=seo_path
        )

    schema = load_schema()
    validate(instance=final_output, schema=schema)

    latest_path = save_output(
        channel=final_output["channel"],
        data=final_output
    )

    print("Publisher Agent completed successfully.")
    print(f"Output saved to: {latest_path}")


if __name__ == "__main__":
    main()