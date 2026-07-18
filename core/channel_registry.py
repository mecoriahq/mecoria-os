from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from jsonschema import validate


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CHANNEL_CONFIG_DIR = PROJECT_ROOT / "config" / "channels"
CHANNEL_SCHEMA_PATH = CHANNEL_CONFIG_DIR / "schema.json"
RUN_CONTEXT_ROOT = PROJECT_ROOT / "records" / "run_contexts"


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Required file not found: {path}")

    return json.loads(path.read_text(encoding="utf-8-sig"))


def load_schema() -> dict[str, Any]:
    return load_json(CHANNEL_SCHEMA_PATH)


def channel_config_path(channel: str) -> Path:
    normalized = normalize_channel(channel)
    return CHANNEL_CONFIG_DIR / f"{normalized}.json"


def normalize_channel(channel: str) -> str:
    normalized = str(channel).strip().lower()

    if not re.fullmatch(r"[a-z0-9_]+", normalized):
        raise ValueError(
            "Channel must contain only lowercase letters, numbers, and underscores."
        )

    return normalized


def load_channel(channel: str) -> dict[str, Any]:
    config = load_json(channel_config_path(channel))
    validate(instance=config, schema=load_schema())
    return config


def list_channels() -> list[dict[str, Any]]:
    schema = load_schema()
    channels: list[dict[str, Any]] = []

    for path in sorted(CHANNEL_CONFIG_DIR.glob("*.json")):
        if path.name == "schema.json":
            continue

        config = load_json(path)
        validate(instance=config, schema=schema)
        channels.append(config)

    return channels


def context_sort_key(path: Path) -> int:
    match = re.fullmatch(r"video_(\d+)\.json", path.name)

    if not match:
        return -1

    return int(match.group(1))


def channel_contexts(channel: str) -> list[dict[str, Any]]:
    normalized = normalize_channel(channel)
    folder = RUN_CONTEXT_ROOT / normalized

    if not folder.exists():
        return []

    contexts: list[dict[str, Any]] = []

    for path in sorted(
        folder.glob("video_*.json"),
        key=context_sort_key,
    ):
        try:
            contexts.append(load_json(path))
        except (json.JSONDecodeError, OSError):
            continue

    return contexts


def latest_context(channel: str) -> dict[str, Any] | None:
    contexts = channel_contexts(channel)
    return contexts[-1] if contexts else None


def active_context(channel: str) -> dict[str, Any] | None:
    contexts = channel_contexts(channel)

    terminal_statuses = {
        "public",
        "archived",
        "cancelled",
    }

    active = [
        context
        for context in contexts
        if str(context.get("status", "")).lower()
        not in terminal_statuses
    ]

    return active[-1] if active else None


def build_channel_status(config: dict[str, Any]) -> dict[str, Any]:
    channel = config["channel"]
    latest = latest_context(channel)
    active = active_context(channel)

    if active:
        operational_state = "active_production"
        current_video_id = active.get("video_id")
        current_status = active.get("status")
        current_next_agent = active.get("next_agent")
    elif latest:
        operational_state = "idle"
        current_video_id = latest.get("video_id")
        current_status = latest.get("status")
        current_next_agent = latest.get("next_agent")
    else:
        operational_state = "not_started"
        current_video_id = None
        current_status = None
        current_next_agent = config["analytics"]["next_action"]

    blockers = list(config.get("blockers", []))

    if not config["production_enabled"]:
        blockers.append("production_disabled")

    return {
        "channel": channel,
        "display_name": config["display_name"],
        "config_status": config["status"],
        "production_enabled": config["production_enabled"],
        "operational_state": operational_state,
        "current_video_id": current_video_id,
        "current_status": current_status,
        "current_next_agent": current_next_agent,
        "public_video_count": config["youtube"]["public_video_count"],
        "notion_sync_enabled": config["integrations"]["notion_sync"],
        "analytics_enabled": config["integrations"]["youtube_analytics"],
        "auto_create_next_video": config["pipeline"]["auto_create_next_video"],
        "blockers": sorted(set(blockers)),
    }


def build_all_status() -> dict[str, Any]:
    statuses = [
        build_channel_status(config)
        for config in list_channels()
    ]

    return {
        "system": "mecoria_media_os",
        "version": "1.0",
        "channel_count": len(statuses),
        "active_channel_count": sum(
            1 for item in statuses
            if item["config_status"] == "active"
        ),
        "production_enabled_count": sum(
            1 for item in statuses
            if item["production_enabled"]
        ),
        "notion_sync_runner_ready": (
            PROJECT_ROOT
            / "agents"
            / "notion_os_sync_runner"
            / "run.py"
        ).exists(),
        "media_runner_ready": (
            PROJECT_ROOT
            / "scripts"
            / "mecoria_media.py"
        ).exists(),
        "channels": statuses,
    }
