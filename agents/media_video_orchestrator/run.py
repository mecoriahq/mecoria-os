import argparse
import re
import subprocess
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent.parent


def resolve_video_id(
    channel: str,
    requested: str
) -> str:
    if requested.lower() != "auto":
        video_id = requested.lower()

        if not re.fullmatch(r"video_\d{3,}", video_id):
            raise ValueError(
                "video_id must use format video_003 or auto."
            )

        return video_id

    context_dir = (
        PROJECT_ROOT
        / "records"
        / "run_contexts"
        / channel
    )

    numbers = []

    if context_dir.exists():
        for path in context_dir.glob("video_*.json"):
            match = re.fullmatch(r"video_(\d+)", path.stem)

            if match:
                numbers.append(int(match.group(1)))

    return f"video_{max(numbers, default=0) + 1:03d}"


def build_commands(
    channel: str,
    video_id: str,
    selected_index: int | None
) -> list[tuple[str, list[str]]]:
    commands = [
        (
            "research",
            [
                sys.executable,
                "agents/research/run.py",
                "--channel",
                channel,
                "--video-id",
                video_id
            ]
        ),
        (
            "content_idea_selector",
            [
                sys.executable,
                "agents/content_idea_selector/run.py",
                "--channel",
                channel,
                "--video-id",
                video_id
            ]
        ),
        (
            "script",
            [
                sys.executable,
                "agents/script/run.py",
                "--channel",
                channel,
                "--video-id",
                video_id
            ]
        ),
        (
            "seo",
            [
                sys.executable,
                "agents/seo/run.py",
                "--channel",
                channel,
                "--video-id",
                video_id
            ]
        ),
        (
            "qa",
            [
                sys.executable,
                "agents/qa/run.py",
                "--channel",
                channel,
                "--video-id",
                video_id
            ]
        )
    ]

    if selected_index is not None:
        commands[1][1].extend([
            "--selected-index",
            str(selected_index)
        ])

    return commands


def run_step(name: str, command: list[str]) -> None:
    print(f"RUNNING_AGENT: {name}", flush=True)

    result = subprocess.run(
        command,
        cwd=PROJECT_ROOT
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Agent failed: {name} "
            f"(exit code {result.returncode})"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Orchestrate Research, Idea Selection, Script, SEO, "
            "and Content QA for one video."
        )
    )

    parser.add_argument("--channel", default="hiddenova")
    parser.add_argument("--video-id", default="auto")
    parser.add_argument("--selected-index", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    channel = args.channel.lower()
    video_id = resolve_video_id(
        channel=channel,
        requested=args.video_id
    )

    commands = build_commands(
        channel=channel,
        video_id=video_id,
        selected_index=args.selected_index
    )

    print(f"CHANNEL: {channel}")
    print(f"VIDEO_CONTEXT_ID: {video_id}")
    print(f"RUN_ID: {channel}_{video_id}_v1")
    print("LATEST_JSON_INPUTS: blocked")
    print("PIPELINE: research -> selector -> script -> seo -> qa")

    if args.dry_run:
        for name, command in commands:
            printable = " ".join(command[1:])
            print(f"PLAN: {name} -> {printable}")

        print("STATUS: orchestrator_dry_run_ready")
        return

    for name, command in commands:
        run_step(name=name, command=command)

    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

    from core.video_run_context import (
        load_context,
        resolve_output,
    )

    context = load_context(
        channel=channel,
        video_id=video_id
    )

    for key in ("script", "seo", "qa"):
        resolve_output(context, key)

    if context.get("status") != "content_qa_ready":
        raise RuntimeError(
            "Content pipeline did not reach content_qa_ready."
        )

    print("Media Video Orchestrator completed successfully.")
    print(f"TOPIC: {context['topic_title']}")
    print(f"STATUS: {context['status']}")
    print(f"NEXT_AGENT: {context['next_agent']}")


if __name__ == "__main__":
    main()
