import argparse
import json
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.ai_video_standard import (
    DEFAULT_INSERT_COUNT,
    DEFAULT_MODEL,
    DEFAULT_PROVIDER,
    build_plan,
    load_json,
)
from core.video_run_context import (
    load_context,
    register_output,
    resolve_output,
    save_context,
)


DEFAULT_CHANNEL = "hiddenova"


def relative_path(path: Path) -> str:
    return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")


def get_output_path(
    context: dict,
    explicit_path: str | None = None
) -> Path:
    if explicit_path:
        path = Path(explicit_path)

        if not path.is_absolute():
            path = PROJECT_ROOT / path

        return path

    return (
        BASE_DIR
        / "output"
        / context["channel"]
        / context["video_id"]
        / context["run_id"]
        / "ai_video_insert_plan.json"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a video-specific AI video insert plan "
            "from approved AI documentary images."
        )
    )
    parser.add_argument("--channel", default=DEFAULT_CHANNEL)
    parser.add_argument("--video-id", required=True)
    parser.add_argument(
        "--count",
        type=int,
        default=DEFAULT_INSERT_COUNT
    )
    parser.add_argument("--provider", default=DEFAULT_PROVIDER)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument(
        "--output-path",
        default=None,
        help=(
            "Write the plan to an explicit path without changing "
            "the video context."
        )
    )
    parser.add_argument(
        "--attach-context",
        action="store_true",
        help=(
            "Register the written plan in the video context. "
            "Disabled by default for safe testing."
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and print the plan without writing files."
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    channel = args.channel.lower()
    video_id = args.video_id.lower()

    if args.dry_run and args.attach_context:
        raise ValueError(
            "Dry-run plans cannot be attached to production context."
        )

    context = load_context(
        channel=channel,
        video_id=video_id
    )

    generation_path = resolve_output(
        context=context,
        key="ai_visual_generation"
    )
    qa_path = resolve_output(
        context=context,
        key="ai_visual_qa"
    )

    plan = build_plan(
        context=context,
        generation_data=load_json(generation_path),
        qa_data=load_json(qa_path),
        count=args.count,
        provider=args.provider,
        model=args.model
    )

    print(f"VIDEO_CONTEXT_ID: {video_id}")
    print(f"RUN_ID: {context['run_id']}")
    print(f"PROVIDER: {plan['provider']['provider_id']}")
    print(f"MODEL: {plan['provider']['model']}")
    print(
        "PLANNED_AI_VIDEO_INSERT_COUNT: "
        f"{plan['summary']['planned_insert_count']}"
    )
    print(
        "PLANNED_AI_VIDEO_DURATION: "
        f"{plan['summary']['planned_total_duration_seconds']}s"
    )
    print("PRODUCTION_API_CALLED: false")

    for item in plan["items"]:
        print(
            f"- {item['insert_id']} | "
            f"{item['source_ai_image_insert_id']} | "
            f"{item['section_hint']}"
        )

    if args.dry_run:
        print("STATUS: ai_video_plan_dry_run_ready")
        return

    output_path = get_output_path(
        context=context,
        explicit_path=args.output_path
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(plan, indent=2, ensure_ascii=True),
        encoding="utf-8"
    )

    context_changed = False

    if args.attach_context:
        context = register_output(
            context=context,
            agent="ai_video_insert_plan",
            reference=relative_path(output_path),
            status="plan_ready"
        )
        save_context(context)
        context_changed = True

    print("STATUS: ai_video_insert_plan_ready")
    print(f"OUTPUT: {relative_path(output_path)}")
    print(
        "CONTEXT_CHANGED: "
        f"{str(context_changed).lower()}"
    )


if __name__ == "__main__":
    main()
