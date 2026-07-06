import json
from pathlib import Path

from jsonschema import validate


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent.parent
STATE_DIR = BASE_DIR / "state"


def load_json(file_path: Path) -> dict:
    if not file_path.exists():
        raise FileNotFoundError(f"Required file not found: {file_path}")

    return json.loads(file_path.read_text(encoding="utf-8"))


def load_schema() -> dict:
    return load_json(BASE_DIR / "schema.json")


def get_context_path(channel: str, pipeline: str) -> Path:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    return STATE_DIR / f"{channel.lower()}_{pipeline.lower()}.json"


def create_context(channel: str, pipeline: str, max_attempts: int = 3) -> dict:
    return {
        "version": "1.0",
        "channel": channel,
        "pipeline": pipeline,
        "current_attempt": 1,
        "max_attempts": max_attempts,
        "status": "running",
        "history": [],
        "next_agent": "image_generation"
    }


def load_or_create_context(channel: str, pipeline: str, max_attempts: int = 3) -> dict:
    context_path = get_context_path(channel, pipeline)

    if context_path.exists():
        return load_json(context_path)

    context = create_context(
        channel=channel,
        pipeline=pipeline,
        max_attempts=max_attempts
    )

    save_context(context)

    return context


def save_context(context: dict) -> Path:
    schema = load_schema()
    validate(instance=context, schema=schema)

    context_path = get_context_path(
        channel=context["channel"],
        pipeline=context["pipeline"]
    )

    context_path.write_text(
        json.dumps(context, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    return context_path


def add_history(
    context: dict,
    agent: str,
    status: str,
    score: int | None,
    next_agent: str | None
) -> dict:
    context["history"].append(
        {
            "attempt": context["current_attempt"],
            "agent": agent,
            "status": status,
            "score": score,
            "next_agent": next_agent
        }
    )

    return context


def apply_image_qa_result(context: dict, image_qa_data: dict) -> dict:
    status = image_qa_data["status"]
    score = image_qa_data["overall_score"]

    if status == "approved":
        context["status"] = "approved"
        context["next_agent"] = "publisher"

        return add_history(
            context=context,
            agent="image_qa",
            status=status,
            score=score,
            next_agent="publisher"
        )

    if context["current_attempt"] >= context["max_attempts"]:
        context["status"] = "human_review"
        context["next_agent"] = None

        return add_history(
            context=context,
            agent="image_qa",
            status=status,
            score=score,
            next_agent=None
        )

    context["status"] = "running"
    context["current_attempt"] += 1
    context["next_agent"] = "image_revision"

    return add_history(
        context=context,
        agent="image_qa",
        status=status,
        score=score,
        next_agent="image_revision"
    )


def apply_image_revision_created(context: dict) -> dict:
    context["status"] = "running"
    context["next_agent"] = "image_generation"

    return add_history(
        context=context,
        agent="image_revision",
        status="created",
        score=None,
        next_agent="image_generation"
    )