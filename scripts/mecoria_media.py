import argparse
import json
import os
import re
import subprocess
import sys
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONTEXT_ROOT = PROJECT_ROOT / "records" / "run_contexts"
ORCHESTRATOR_PATH = (
    PROJECT_ROOT
    / "agents"
    / "media_video_orchestrator"
    / "run.py"
)
STORYBLOCKS_BRIDGE_PATH = (
    PROJECT_ROOT
    / "agents"
    / "storyblocks_bridge"
    / "run.py"
)
RUNNER_VERSION = "1.1"

VIDEO_ID_PATTERN = re.compile(r"^video_(\d{3,})$")
CHANNEL_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")

COMPLETED_STATES = {
    "public",
    "published",
}

FOUNDER_REVIEW_STATES = {
    "founder_review_required",
    "uploaded_for_founder_review",
}

TOPIC_APPROVAL_STATES = {
    "topic_approval_required",
}

STOCK_GATE_STATES = {
    "stock_source_required",
}


class RunnerError(RuntimeError):
    """Raised for safe, user-facing runner failures."""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_channel(channel: str) -> str:
    normalized = channel.strip().lower()

    if not CHANNEL_PATTERN.fullmatch(normalized):
        raise RunnerError(
            "Channel must contain only lowercase letters, "
            "numbers, hyphens, or underscores."
        )

    return normalized


def normalize_video_id(video_id: str) -> str:
    normalized = video_id.strip().lower()

    if not VIDEO_ID_PATTERN.fullmatch(normalized):
        raise RunnerError(
            "video_id must use format video_005."
        )

    return normalized


def video_number(video_id: str) -> int:
    match = VIDEO_ID_PATTERN.fullmatch(video_id)

    if not match:
        raise RunnerError(
            f"Invalid video_id in run context: {video_id}"
        )

    return int(match.group(1))


def get_context_dir(
    channel: str,
    project_root: Path = PROJECT_ROOT
) -> Path:
    return (
        project_root
        / "records"
        / "run_contexts"
        / normalize_channel(channel)
    )


def get_context_path(
    channel: str,
    video_id: str,
    project_root: Path = PROJECT_ROOT
) -> Path:
    return (
        get_context_dir(channel, project_root)
        / f"{normalize_video_id(video_id)}.json"
    )


def load_context_path(path: Path) -> dict:
    try:
        data = json.loads(
            path.read_text(encoding="utf-8-sig")
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise RunnerError(
            f"Unable to read run context: {path}"
        ) from exc

    required = {
        "channel",
        "video_id",
        "run_id",
        "status",
        "topic_title",
    }

    missing = sorted(required - set(data))

    if missing:
        raise RunnerError(
            "Run context is missing required fields: "
            + ", ".join(missing)
        )

    if path.stem != data["video_id"]:
        raise RunnerError(
            f"Run context filename identity mismatch: {path}"
        )

    return data


def list_contexts(
    channel: str,
    project_root: Path = PROJECT_ROOT
) -> list[dict]:
    context_dir = get_context_dir(
        channel=channel,
        project_root=project_root
    )

    if not context_dir.exists():
        return []

    contexts = [
        load_context_path(path)
        for path in context_dir.glob("video_*.json")
        if VIDEO_ID_PATTERN.fullmatch(path.stem)
    ]

    return sorted(
        contexts,
        key=lambda item: video_number(item["video_id"])
    )


def is_completed(context: dict) -> bool:
    return context.get("status") in COMPLETED_STATES


def active_contexts(contexts: list[dict]) -> list[dict]:
    return [
        context
        for context in contexts
        if not is_completed(context)
    ]


def next_video_id(contexts: list[dict]) -> str:
    highest = max(
        (
            video_number(context["video_id"])
            for context in contexts
        ),
        default=0
    )

    return f"video_{highest + 1:03d}"


def topic_is_approved(context: dict) -> bool:
    return (
        context.get("release", {}).get(
            "topic_approved"
        )
        is True
    )


def classify_context(context: dict) -> str:
    status = str(context.get("status", "")).strip()

    if status in COMPLETED_STATES:
        return "complete"

    if status in FOUNDER_REVIEW_STATES:
        return "wait_founder_video_review"

    if (
        status in TOPIC_APPROVAL_STATES
        or not topic_is_approved(context)
    ):
        return "wait_topic_approval"

    if status in STOCK_GATE_STATES:
        return "wait_stock_source"

    return "resume_existing"


def resolve_run_target(
    channel: str,
    requested_video_id: str | None,
    project_root: Path = PROJECT_ROOT
) -> tuple[str, dict | None]:
    contexts = list_contexts(
        channel=channel,
        project_root=project_root
    )

    if requested_video_id:
        video_id = normalize_video_id(
            requested_video_id
        )
        path = get_context_path(
            channel=channel,
            video_id=video_id,
            project_root=project_root
        )

        return (
            video_id,
            load_context_path(path)
            if path.exists()
            else None
        )

    active = active_contexts(contexts)

    if len(active) > 1:
        video_ids = ", ".join(
            item["video_id"]
            for item in active
        )
        raise RunnerError(
            "Multiple active video contexts found. "
            f"Choose one with --video-id: {video_ids}"
        )

    if len(active) == 1:
        context = active[0]
        return context["video_id"], context

    return next_video_id(contexts), None


def resolve_existing_target(
    channel: str,
    requested_video_id: str | None,
    project_root: Path = PROJECT_ROOT
) -> dict:
    contexts = list_contexts(
        channel=channel,
        project_root=project_root
    )

    if requested_video_id:
        path = get_context_path(
            channel=channel,
            video_id=requested_video_id,
            project_root=project_root
        )

        if not path.exists():
            raise RunnerError(
                "Requested video context does not exist: "
                + normalize_video_id(requested_video_id)
            )

        return load_context_path(path)

    active = active_contexts(contexts)

    if len(active) > 1:
        video_ids = ", ".join(
            item["video_id"]
            for item in active
        )
        raise RunnerError(
            "Multiple active video contexts found. "
            f"Choose one with --video-id: {video_ids}"
        )

    if len(active) == 1:
        return active[0]

    raise RunnerError(
        "No active video context was found."
    )


def resolve_status_target(
    channel: str,
    requested_video_id: str | None,
    project_root: Path = PROJECT_ROOT
) -> dict:
    if requested_video_id:
        return resolve_existing_target(
            channel=channel,
            requested_video_id=requested_video_id,
            project_root=project_root
        )

    contexts = list_contexts(
        channel=channel,
        project_root=project_root
    )

    active = active_contexts(contexts)

    if len(active) > 1:
        video_ids = ", ".join(
            item["video_id"]
            for item in active
        )
        raise RunnerError(
            "Multiple active video contexts found. "
            f"Choose one with --video-id: {video_ids}"
        )

    if len(active) == 1:
        return active[0]

    if contexts:
        return contexts[-1]

    raise RunnerError(
        "No video context was found for this channel."
    )


def build_orchestrator_command(
    channel: str,
    video_id: str,
    action: str,
    selected_index: int | None = None,
    stock_manifest: str | None = None,
    dry_run: bool = False,
    python_executable: str = sys.executable,
    project_root: Path = PROJECT_ROOT,
) -> list[str]:
    command = [
        python_executable,
        str(
            project_root
            / "agents"
            / "media_video_orchestrator"
            / "run.py"
        ),
        "--channel",
        normalize_channel(channel),
        "--video-id",
        normalize_video_id(video_id),
    ]

    if action == "create_new_video":
        if selected_index is not None:
            if selected_index < 0:
                raise RunnerError(
                    "selected_index cannot be negative."
                )

            command.extend([
                "--selected-index",
                str(selected_index),
            ])

    elif action == "resume_existing":
        command.append("--resume")

    elif action == "approve_topic":
        command.append("--approve-topic")

    else:
        raise RunnerError(
            f"Unsupported orchestrator action: {action}"
        )

    if stock_manifest:
        command.extend([
            "--stock-manifest",
            stock_manifest,
        ])

    if dry_run:
        command.append("--dry-run")

    return command


def build_storyblocks_bridge_command(
    channel: str,
    video_id: str,
    dry_run: bool = False,
    python_executable: str = sys.executable,
    project_root: Path = PROJECT_ROOT,
) -> list[str]:
    command = [
        python_executable,
        str(
            project_root
            / "agents"
            / "storyblocks_bridge"
            / "run.py"
        ),
        "--channel",
        normalize_channel(channel),
        "--video-id",
        normalize_video_id(video_id),
    ]

    if dry_run:
        command.extend([
            "--dry-run",
            "--no-open",
        ])

    return command


def command_display(command: list[str]) -> str:
    return " ".join(
        f'"{item}"' if " " in item else item
        for item in command
    )


def print_runner_header(
    command_name: str,
    channel: str,
    video_id: str | None = None
) -> None:
    print(f"MECORIA_MEDIA_RUNNER_VERSION: {RUNNER_VERSION}")
    print(f"RUNNER_COMMAND: {command_name}")
    print(f"CHANNEL: {channel}")

    if video_id:
        print(f"VIDEO_CONTEXT_ID: {video_id}")


def next_command(
    context: dict,
    action: str
) -> str:
    channel = context["channel"]
    video_id = context["video_id"]

    if action == "wait_topic_approval":
        return (
            "python scripts\\mecoria_media.py "
            f"approve-topic {channel} "
            f"--video-id {video_id}"
        )

    if action == "resume_existing":
        return (
            "python scripts\\mecoria_media.py "
            f"run {channel} --video-id {video_id}"
        )

    if action == "wait_stock_source":
        return (
            "python scripts\\mecoria_media.py "
            f"run {channel} --video-id {video_id}"
        )

    if action == "wait_founder_video_review":
        return "review_unlisted_video_and_approve_or_revise"

    if action == "complete":
        return (
            "python scripts\\mecoria_media.py "
            f"run {channel}"
        )

    return "none"


def print_context_summary(context: dict) -> None:
    action = classify_context(context)

    print(f"VIDEO_CONTEXT_ID: {context['video_id']}")
    print(f"RUN_ID: {context['run_id']}")
    print(f"TOPIC: {context['topic_title']}")
    print(f"CURRENT_STATUS: {context['status']}")
    print(
        "CURRENT_NEXT_AGENT: "
        f"{context.get('next_agent')}"
    )
    print(f"RUNNER_ACTION: {action}")

    founder_action = {
        "wait_topic_approval": "topic_approval",
        "wait_founder_video_review": "final_video_review",
        "wait_stock_source": "storyblocks_downloads_only",
        "resume_existing": "none",
        "complete": "none",
    }[action]

    print(f"FOUNDER_ACTION_REQUIRED: {founder_action}")
    print(
        "NEXT_COMMAND: "
        f"{next_command(context, action)}"
    )


def run_orchestrator(
    command: list[str],
    project_root: Path = PROJECT_ROOT
) -> None:
    print(
        "ORCHESTRATOR_COMMAND: "
        f"{command_display(command)}"
    )
    print("RUNNER_EXECUTION: started", flush=True)

    result = subprocess.run(
        command,
        cwd=project_root,
        check=False,
    )

    if result.returncode != 0:
        print("RUNNER_EXECUTION: failed")
        raise RunnerError(
            "Media orchestrator failed with exit code "
            f"{result.returncode}."
        )

    print("RUNNER_EXECUTION: completed")


def run_storyblocks_bridge(
    command: list[str],
    project_root: Path = PROJECT_ROOT
) -> None:
    print(
        "STORYBLOCKS_BRIDGE_COMMAND: "
        f"{command_display(command)}"
    )
    print(
        "STORYBLOCKS_BRIDGE_EXECUTION: started",
        flush=True,
    )

    result = subprocess.run(
        command,
        cwd=project_root,
        check=False,
    )

    if result.returncode != 0:
        print("STORYBLOCKS_BRIDGE_EXECUTION: failed")
        raise RunnerError(
            "Storyblocks Bridge failed with exit code "
            f"{result.returncode}."
        )

    print("STORYBLOCKS_BRIDGE_EXECUTION: completed")


def stock_manifest_attached(context: dict) -> bool:
    reference = context.get(
        "sources",
        {},
    ).get("stock_manifest")

    if not reference:
        return False

    path = Path(reference)

    if not path.is_absolute():
        path = PROJECT_ROOT / path

    return path.exists()


def lock_path(
    channel: str,
    project_root: Path = PROJECT_ROOT
) -> Path:
    return (
        project_root
        / ".git"
        / "mecoria_locks"
        / f"media_runner_{normalize_channel(channel)}.lock"
    )


@contextmanager
def runner_lock(
    channel: str,
    project_root: Path = PROJECT_ROOT,
    stale_after: timedelta = timedelta(hours=6),
) -> Iterator[None]:
    path = lock_path(
        channel=channel,
        project_root=project_root
    )
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists():
        try:
            payload = json.loads(
                path.read_text(encoding="utf-8")
            )
            created_at = datetime.fromisoformat(
                payload["created_at"]
            )
        except (
            OSError,
            KeyError,
            ValueError,
            json.JSONDecodeError,
        ):
            created_at = utc_now()

        if utc_now() - created_at <= stale_after:
            raise RunnerError(
                "Another Mecoria Media Runner process "
                "is already active for this channel."
            )

        path.unlink(missing_ok=True)

    payload = {
        "pid": os.getpid(),
        "channel": normalize_channel(channel),
        "created_at": utc_now().isoformat(),
    }

    try:
        path.write_text(
            json.dumps(
                payload,
                indent=2,
                ensure_ascii=True
            ),
            encoding="utf-8"
        )
        yield
    finally:
        path.unlink(missing_ok=True)


def execute_run(args: argparse.Namespace) -> None:
    channel = normalize_channel(args.channel)
    video_id, context = resolve_run_target(
        channel=channel,
        requested_video_id=args.video_id
    )

    print_runner_header(
        command_name="run",
        channel=channel,
        video_id=video_id
    )

    if context is None:
        if args.stock_manifest:
            raise RunnerError(
                "--stock-manifest requires an existing "
                "video context."
            )

        action = "create_new_video"
        print("RUNNER_ACTION: create_new_video")
        print("FOUNDER_ACTION_REQUIRED: none")

        command = build_orchestrator_command(
            channel=channel,
            video_id=video_id,
            action=action,
            selected_index=args.selected_index,
            dry_run=args.dry_run,
        )

        if args.dry_run:
            run_orchestrator(command)
            print("RUNNER_STATUS: dry_run_ready")
            return

        with runner_lock(channel):
            run_orchestrator(command)

        context = load_context_path(
            get_context_path(channel, video_id)
        )
        print_context_summary(context)
        print("RUNNER_STATUS: waiting_for_founder")
        return

    if args.selected_index is not None:
        raise RunnerError(
            "--selected-index is only valid when "
            "creating a new video."
        )

    action = classify_context(context)
    print_context_summary(context)

    if args.dry_run:
        if action == "wait_stock_source":
            bridge_command = (
                build_storyblocks_bridge_command(
                    channel=channel,
                    video_id=video_id,
                    dry_run=True,
                )
            )
            run_storyblocks_bridge(
                bridge_command
            )
        else:
            command = build_orchestrator_command(
                channel=channel,
                video_id=video_id,
                action="resume_existing",
                dry_run=True,
            )
            run_orchestrator(command)

        print("RUNNER_STATUS: dry_run_ready")
        return

    if (
        action == "wait_stock_source"
        and not args.stock_manifest
    ):
        bridge_command = (
            build_storyblocks_bridge_command(
                channel=channel,
                video_id=video_id,
            )
        )

        with runner_lock(channel):
            run_storyblocks_bridge(
                bridge_command
            )

            refreshed = load_context_path(
                get_context_path(
                    channel,
                    video_id,
                )
            )

            if not stock_manifest_attached(
                refreshed
            ):
                print_context_summary(
                    refreshed
                )
                print(
                    "RUNNER_STATUS: "
                    "waiting_for_storyblocks_downloads"
                )
                return

            command = build_orchestrator_command(
                channel=channel,
                video_id=video_id,
                action="resume_existing",
            )
            run_orchestrator(command)

        refreshed = load_context_path(
            get_context_path(
                channel,
                video_id,
            )
        )
        print_context_summary(refreshed)
        print(
            "RUNNER_STATUS: "
            "storyblocks_ingested_and_resumed"
        )
        return

    if action in {
        "wait_topic_approval",
        "wait_founder_video_review",
        "complete",
    } and not args.stock_manifest:
        print("RUNNER_EXECUTION: no_action")
        print("RUNNER_STATUS: waiting_for_required_gate")
        return

    command = build_orchestrator_command(
        channel=channel,
        video_id=video_id,
        action="resume_existing",
        stock_manifest=args.stock_manifest,
    )

    with runner_lock(channel):
        run_orchestrator(command)

    refreshed = load_context_path(
        get_context_path(channel, video_id)
    )
    print_context_summary(refreshed)
    print("RUNNER_STATUS: checkpoint_reached")


def execute_approve_topic(
    args: argparse.Namespace
) -> None:
    channel = normalize_channel(args.channel)
    context = resolve_existing_target(
        channel=channel,
        requested_video_id=args.video_id
    )
    video_id = context["video_id"]

    print_runner_header(
        command_name="approve-topic",
        channel=channel,
        video_id=video_id
    )
    print_context_summary(context)

    action = classify_context(context)

    if action != "wait_topic_approval":
        raise RunnerError(
            "This video is not waiting for topic approval."
        )

    command = build_orchestrator_command(
        channel=channel,
        video_id=video_id,
        action="approve_topic",
    )

    with runner_lock(channel):
        run_orchestrator(command)

    refreshed = load_context_path(
        get_context_path(channel, video_id)
    )
    print_context_summary(refreshed)
    print("RUNNER_STATUS: topic_approved_and_resumed")


def execute_status(args: argparse.Namespace) -> None:
    channel = normalize_channel(args.channel)
    context = resolve_status_target(
        channel=channel,
        requested_video_id=args.video_id
    )

    print_runner_header(
        command_name="status",
        channel=channel,
        video_id=context["video_id"]
    )
    print_context_summary(context)
    print("RUNNER_STATUS: status_ready")


def add_common_target_arguments(
    parser: argparse.ArgumentParser
) -> None:
    parser.add_argument(
        "channel",
        nargs="?",
        default="hiddenova",
    )
    parser.add_argument(
        "--video-id",
        default=None,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Start or resume Mecoria Media production "
            "with one founder-facing command."
        )
    )
    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    run_parser = subparsers.add_parser(
        "run",
        help=(
            "Start the next video or resume the only "
            "active video."
        ),
    )
    add_common_target_arguments(run_parser)
    run_parser.add_argument(
        "--selected-index",
        type=int,
        default=None,
    )
    run_parser.add_argument(
        "--stock-manifest",
        default=None,
    )
    run_parser.add_argument(
        "--dry-run",
        action="store_true",
    )
    run_parser.set_defaults(handler=execute_run)

    approval_parser = subparsers.add_parser(
        "approve-topic",
        help=(
            "Approve the selected topic and continue "
            "production automatically."
        ),
    )
    add_common_target_arguments(approval_parser)
    approval_parser.set_defaults(
        handler=execute_approve_topic
    )

    status_parser = subparsers.add_parser(
        "status",
        help=(
            "Show the active or requested video checkpoint."
        ),
    )
    add_common_target_arguments(status_parser)
    status_parser.set_defaults(handler=execute_status)

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    try:
        args.handler(args)
    except RunnerError as exc:
        print(f"MECORIA_MEDIA_RUNNER_ERROR: {exc}")
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
