import json
from datetime import datetime, timezone
from pathlib import Path

from jsonschema import validate


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = Path(__file__).resolve().with_name(
    "video_run_context_schema.json"
)
CONTEXT_ROOT = PROJECT_ROOT / "records" / "run_contexts"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Required file not found: {path}")

    return json.loads(path.read_text(encoding="utf-8-sig"))


def load_schema() -> dict:
    return load_json(SCHEMA_PATH)


def get_context_path(channel: str, video_id: str) -> Path:
    return (
        CONTEXT_ROOT
        / channel.lower()
        / f"{video_id.lower()}.json"
    )


def validate_context_data(context: dict) -> None:
    validate(instance=context, schema=load_schema())
    assert_no_latest_sources(context)


def assert_no_latest_sources(context: dict) -> None:
    for key, reference in context.get("sources", {}).items():
        if not isinstance(reference, str):
            raise TypeError(
                f"Context source must be a string: {key}"
            )

        normalized = reference.replace("\\", "/").lower()

        if normalized.endswith("/latest.json"):
            raise ValueError(
                f"Production source cannot use latest.json: {key}"
            )

        if Path(reference).is_absolute():
            raise ValueError(
                f"Context source must be repo-relative: {key}"
            )


def load_context(channel: str, video_id: str) -> dict:
    context = load_json(get_context_path(channel, video_id))
    validate_context_data(context)
    assert_identity(
        context=context,
        channel=channel,
        video_id=video_id
    )
    return context


def save_context(context: dict) -> Path:
    context.setdefault("history", [])
    context.setdefault("created_at", utc_now())
    context["updated_at"] = utc_now()

    validate_context_data(context)

    path = get_context_path(
        channel=context["channel"],
        video_id=context["video_id"]
    )
    path.parent.mkdir(parents=True, exist_ok=True)

    path.write_text(
        json.dumps(context, indent=2, ensure_ascii=True),
        encoding="utf-8"
    )

    return path


def assert_identity(
    context: dict,
    channel: str,
    video_id: str,
    run_id: str | None = None
) -> None:
    if context.get("channel") != channel.lower():
        raise ValueError("Run context channel mismatch.")

    if context.get("video_id") != video_id.lower():
        raise ValueError("Run context video_id mismatch.")

    if run_id and context.get("run_id") != run_id:
        raise ValueError("Run context run_id mismatch.")


def resolve_source(
    context: dict,
    key: str,
    must_exist: bool = True
) -> Path:
    if key not in context.get("sources", {}):
        raise KeyError(f"Context source is missing: {key}")

    reference = context["sources"][key]
    normalized = reference.replace("\\", "/").lower()

    if normalized.endswith("/latest.json"):
        raise ValueError(
            f"Production source cannot use latest.json: {key}"
        )

    path = PROJECT_ROOT / reference

    if must_exist and not path.exists():
        raise FileNotFoundError(
            f"Context source file not found: {path}"
        )

    return path


def register_output(
    context: dict,
    agent: str,
    reference: str,
    status: str
) -> dict:
    normalized_reference = reference.replace("\\", "/")

    if Path(normalized_reference).is_absolute():
        raise ValueError("Output reference must be repo-relative.")

    context.setdefault("outputs", {})[agent] = normalized_reference
    context.setdefault("history", []).append({
        "agent": agent,
        "status": status,
        "output_reference": normalized_reference,
        "recorded_at": utc_now()
    })
    context["updated_at"] = utc_now()

    return context


def set_status(
    context: dict,
    status: str,
    next_agent: str | None = None
) -> dict:
    context["status"] = status
    context["next_agent"] = next_agent
    context["updated_at"] = utc_now()
    return context


def assert_agent_identity(
    output_data: dict,
    context: dict
) -> None:
    if output_data.get("channel") != context["channel"]:
        raise ValueError("Agent output channel mismatch.")

    if output_data.get("video_id") != context["video_id"]:
        raise ValueError("Agent output video_id mismatch.")

    if output_data.get("run_id") != context["run_id"]:
        raise ValueError("Agent output run_id mismatch.")
