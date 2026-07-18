from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.channel_registry import (
    build_all_status,
    build_channel_status,
    list_channels,
    load_channel,
)


def print_status_row(item: dict[str, Any]) -> None:
    blockers = ",".join(item["blockers"]) if item["blockers"] else "none"

    print(
        f"{item['channel']} | "
        f"config={item['config_status']} | "
        f"production={str(item['production_enabled']).lower()} | "
        f"state={item['operational_state']} | "
        f"video={item['current_video_id'] or '-'} | "
        f"status={item['current_status'] or '-'} | "
        f"next={item['current_next_agent'] or '-'} | "
        f"blockers={blockers}"
    )


def command_status(channel: str, as_json: bool) -> int:
    if channel == "all":
        result = build_all_status()
    else:
        result = build_channel_status(load_channel(channel))

    if as_json:
        print(json.dumps(result, indent=2, ensure_ascii=True))
        return 0

    if channel == "all":
        print("MECORIA_MEDIA_OS_VERSION: 1.0")
        print(f"CHANNEL_COUNT: {result['channel_count']}")
        print(
            "NOTION_SYNC_RUNNER_READY: "
            f"{str(result['notion_sync_runner_ready']).lower()}"
        )
        print(
            "MEDIA_RUNNER_READY: "
            f"{str(result['media_runner_ready']).lower()}"
        )

        for item in result["channels"]:
            print_status_row(item)
    else:
        print_status_row(result)

    return 0


def media_runner_command(channel: str) -> list[str]:
    return [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "mecoria_media.py"),
        "run",
        channel,
    ]


def command_run(
    channel: str,
    execute: bool,
) -> int:
    configs = (
        list_channels()
        if channel == "all"
        else [load_channel(channel)]
    )

    executed = 0
    skipped = 0

    print("MECORIA_MEDIA_OS_RUN_MODE: " + (
        "execute" if execute else "plan_only"
    ))

    for config in configs:
        channel_key = config["channel"]
        blockers = list(config.get("blockers", []))
        pipeline = config["pipeline"]

        if not config["production_enabled"]:
            print(
                f"SKIP: {channel_key} | reason=production_disabled"
            )
            skipped += 1
            continue

        if not pipeline["auto_create_next_video"]:
            print(
                f"SKIP: {channel_key} | "
                "reason=auto_create_next_video_disabled"
            )
            skipped += 1
            continue

        command = media_runner_command(channel_key)
        print("PLAN: " + " ".join(command))

        if execute:
            result = subprocess.run(
                command,
                cwd=PROJECT_ROOT,
                check=False,
            )

            if result.returncode != 0:
                print(
                    f"FAILED: {channel_key} | "
                    f"exit_code={result.returncode}"
                )
                return result.returncode

            executed += 1

    print(f"EXECUTED_CHANNEL_COUNT: {executed}")
    print(f"SKIPPED_CHANNEL_COUNT: {skipped}")
    return 0


def command_notion(apply: bool) -> int:
    command = [
        sys.executable,
        str(
            PROJECT_ROOT
            / "agents"
            / "notion_os_sync_runner"
            / "run.py"
        ),
    ]

    if apply:
        command.append("--apply")

    print("NOTION_SYNC_MODE: " + ("apply" if apply else "dry_run"))
    print("NOTION_SYNC_COMMAND: " + " ".join(command))

    result = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        check=False,
    )
    return result.returncode


def command_bootstrap(channel: str) -> int:
    config = load_channel(channel)
    status = build_channel_status(config)

    print(f"CHANNEL: {channel}")
    print(f"CONFIG_STATUS: {config['status']}")
    print(
        "PRODUCTION_ENABLED: "
        f"{str(config['production_enabled']).lower()}"
    )
    print(
        "BLOCKERS: "
        + (
            ",".join(status["blockers"])
            if status["blockers"]
            else "none"
        )
    )
    print(
        "NEXT_ACTION: "
        f"{config['analytics']['next_action']}"
    )
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Mecoria Media OS multi-channel control plane."
        )
    )
    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("channel", default="all")
    status_parser.add_argument(
        "--json",
        action="store_true",
    )

    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("channel", default="all")
    run_parser.add_argument(
        "--execute",
        action="store_true",
        help=(
            "Execute eligible channel runners. "
            "Without this flag, only print the plan."
        ),
    )

    notion_parser = subparsers.add_parser("sync-notion")
    notion_parser.add_argument(
        "--apply",
        action="store_true",
    )

    bootstrap_parser = subparsers.add_parser("bootstrap")
    bootstrap_parser.add_argument("channel")

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.command == "status":
        return command_status(
            channel=args.channel.lower(),
            as_json=args.json,
        )

    if args.command == "run":
        return command_run(
            channel=args.channel.lower(),
            execute=args.execute,
        )

    if args.command == "sync-notion":
        return command_notion(apply=args.apply)

    if args.command == "bootstrap":
        return command_bootstrap(
            channel=args.channel.lower(),
        )

    raise ValueError(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
