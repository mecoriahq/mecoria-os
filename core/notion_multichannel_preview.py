from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


CHANNEL_CONFIG_RELATIVE_DIR = Path("config") / "channels"
RUN_CONTEXT_RELATIVE_DIR = Path("records") / "run_contexts"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def project_relative(project_root: Path, path: Path) -> str:
    return str(path.relative_to(project_root)).replace("\\", "/")


def normalize_channel_filter(channel_filter: str | None) -> str | None:
    if channel_filter is None:
        return None

    normalized = str(channel_filter).strip().lower()

    if normalized in {"", "all", "system"}:
        return None

    if not re.fullmatch(r"[a-z0-9_]+", normalized):
        raise ValueError(
            "Channel filter must contain only lowercase letters, "
            "numbers, and underscores."
        )

    return normalized


def load_channel_configs(
    project_root: Path,
    channel_filter: str | None = None,
) -> list[tuple[Path, dict[str, Any]]]:
    normalized_filter = normalize_channel_filter(channel_filter)
    config_dir = project_root / CHANNEL_CONFIG_RELATIVE_DIR
    rows: list[tuple[Path, dict[str, Any]]] = []

    for path in sorted(config_dir.glob("*.json")):
        if path.name == "schema.json":
            continue

        config = load_json(path)
        channel = str(config.get("channel", "")).strip().lower()

        if not channel:
            continue

        if normalized_filter and channel != normalized_filter:
            continue

        if not config.get("integrations", {}).get("notion_sync", False):
            continue

        rows.append((path, config))

    if normalized_filter and not rows:
        raise RuntimeError(
            f"No Notion-enabled channel config found: {normalized_filter}"
        )

    return rows


def youtube_url(video_id: Any) -> str | None:
    text = str(video_id or "").strip()
    return f"https://youtu.be/{text}" if text else None


def build_youtube_channel_rows(
    project_root: Path,
    channel_filter: str | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    for config_path, config in load_channel_configs(
        project_root=project_root,
        channel_filter=channel_filter,
    ):
        channel = config["channel"]
        brand = config.get("brand", {})
        youtube = config.get("youtube", {})
        analytics = config.get("analytics", {})
        latest_public_video_id = youtube.get("latest_public_video_id")

        rows.append(
            {
                "database": "youtube_channels",
                "operation": "upsert_preview",
                "key": channel,
                "properties": {
                    "channel": channel,
                    "display_name": config.get("display_name", channel),
                    "platform": "youtube",
                    "launch_status": config.get("status"),
                    "public_video_url": youtube_url(
                        latest_public_video_id
                    ),
                    "homepage_enabled": brand.get("youtube_ready"),
                    "public_video_visible": bool(
                        latest_public_video_id
                    ),
                    "website_link_visible": bool(
                        brand.get("domain")
                    ),
                    "next_step": analytics.get("next_action"),
                    "source_record": project_relative(
                        project_root,
                        config_path,
                    ),
                    "production_enabled": config.get(
                        "production_enabled"
                    ),
                    "youtube_handle": youtube.get("handle"),
                    "public_video_count": youtube.get(
                        "public_video_count",
                        0,
                    ),
                },
            }
        )

    return rows


def context_sort_key(path: Path) -> tuple[int, str]:
    match = re.fullmatch(r"video_(\d+)\.json", path.name)

    if not match:
        return (-1, path.name)

    return (int(match.group(1)), path.name)


def iter_nested_values(value: Any):
    if isinstance(value, dict):
        for key, child in value.items():
            yield str(key), child
            yield from iter_nested_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_nested_values(child)


def find_first(
    sources: list[Any],
    candidate_keys: tuple[str, ...],
) -> Any:
    normalized_keys = {
        key.strip().lower()
        for key in candidate_keys
    }

    for source in sources:
        for key, value in iter_nested_values(source):
            if key.strip().lower() in normalized_keys:
                if value not in (None, "", [], {}):
                    return value

    return None


def coerce_bool(value: Any) -> bool | None:
    if value is None:
        return None

    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float)):
        return bool(value)

    text = str(value).strip().lower()

    if text in {"true", "yes", "1", "ready", "approved", "pass"}:
        return True

    if text in {"false", "no", "0", "blocked", "rejected", "fail"}:
        return False

    return None


def normalize_url(value: Any) -> str | None:
    text = str(value or "").strip()

    if text.startswith("http://") or text.startswith("https://"):
        return text

    return None


def path_value(
    sources: list[Any],
    candidate_keys: tuple[str, ...],
) -> str | None:
    value = find_first(sources, candidate_keys)

    if value is None:
        return None

    text = str(value).strip()
    return text or None


def build_context_queue_row(
    *,
    project_root: Path,
    config: dict[str, Any],
    context_path: Path,
    context: dict[str, Any],
) -> dict[str, Any]:
    channel = str(context.get("channel") or config["channel"])
    video_id = str(context.get("video_id") or context_path.stem)
    run_id = context.get("run_id")
    status = str(context.get("status") or "unknown")
    release = context.get("release", {})
    outputs = context.get("outputs", {})
    quality_gates = context.get("quality_gates", {})
    sources = [release, outputs, quality_gates, context]

    public_url = normalize_url(
        find_first(
            sources,
            (
                "public_url",
                "youtube_url",
                "youtube_public_url",
            ),
        )
    )
    unlisted_url = normalize_url(
        find_first(
            sources,
            (
                "unlisted_url",
                "youtube_unlisted_url",
            ),
        )
    )
    visibility = find_first(
        sources,
        (
            "visibility",
            "youtube_visibility",
        ),
    )
    public_status = find_first(
        sources,
        (
            "public_status",
            "youtube_public_status",
        ),
    )

    if status.lower() == "public":
        public_status = public_status or "public"
        visibility = visibility or "public"

    upload_ready = coerce_bool(
        find_first(
            sources,
            (
                "upload_ready",
                "publisher_upload_ready",
            ),
        )
    )

    if upload_ready is None:
        upload_ready = status.lower() in {
            "upload_ready",
            "uploaded",
            "public",
        }

    first_public_video = coerce_bool(
        find_first(
            sources,
            (
                "first_public_video",
                "first_public_hiddenova_video",
            ),
        )
    )

    if first_public_video is None:
        first_public_video = (
            video_id == "video_001"
            and status.lower() == "public"
        )

    release_version = find_first(
        sources,
        (
            "release_version",
            "version",
        ),
    )
    final_title = find_first(
        [outputs, release],
        (
            "video_title",
            "title",
            "final_title",
        ),
    )
    title = final_title or context.get("topic_title")
    next_step = (
        context.get("next_agent")
        or config.get("analytics", {}).get("next_action")
    )
    video_file_path = path_value(
        [outputs, release],
        (
            "video_file_path",
            "final_video_path",
            "render_path",
        ),
    )
    thumbnail_image_path = path_value(
        [outputs, release],
        (
            "thumbnail_image_path",
            "thumbnail_path",
            "selected_thumbnail_path",
        ),
    )

    return {
        "database": "publishing_queue",
        "operation": "upsert_preview",
        "key": f"{channel}:{video_id}",
        "properties": {
            "channel": channel,
            "video_id": video_id,
            "run_id": run_id,
            "title": title,
            "status": status,
            "release_version": release_version,
            "public_url": public_url,
            "unlisted_url": unlisted_url,
            "visibility": visibility,
            "public_status": public_status,
            "upload_ready": upload_ready,
            "first_public_video": first_public_video,
            "next_step": next_step,
            "source_record": project_relative(
                project_root,
                context_path,
            ),
            "video_file_path": video_file_path,
            "thumbnail_image_path": thumbnail_image_path,
        },
    }


def build_publishing_queue_rows(
    project_root: Path,
    channel_filter: str | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    for _, config in load_channel_configs(
        project_root=project_root,
        channel_filter=channel_filter,
    ):
        channel = config["channel"]
        context_dir = (
            project_root
            / RUN_CONTEXT_RELATIVE_DIR
            / channel
        )

        if not context_dir.exists():
            continue

        for context_path in sorted(
            context_dir.glob("video_*.json"),
            key=context_sort_key,
        ):
            context = load_json(context_path)

            if str(context.get("channel", channel)) != channel:
                raise RuntimeError(
                    "Run context channel mismatch: "
                    f"{context_path}"
                )

            rows.append(
                build_context_queue_row(
                    project_root=project_root,
                    config=config,
                    context_path=context_path,
                    context=context,
                )
            )

    return rows


def build_channel_keys(
    project_root: Path,
    channel_filter: str | None = None,
) -> list[str]:
    return [
        config["channel"]
        for _, config in load_channel_configs(
            project_root=project_root,
            channel_filter=channel_filter,
        )
    ]
