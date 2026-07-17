import argparse
import json
import subprocess
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.ai_video_integration import (
    assert_live_generation_allowed,
    load_ai_video_production_config,
    mark_ai_video_context_ready,
)
from core.video_run_context import (
    load_context,
    resolve_output,
    save_context,
)


DEFAULT_CHANNEL = "hiddenova"
VALID_MODES = {"dry-run", "mock", "live"}


def run_step(name: str, command: list[str]) -> None:
    print(f"RUNNING_AI_VIDEO_STEP: {name}", flush=True)
    result = subprocess.run(command, cwd=PROJECT_ROOT)

    if result.returncode != 0:
        raise RuntimeError(
            f"AI video pipeline step failed: {name} "
            f"(exit code {result.returncode})"
        )


def output_ready(context: dict, key: str) -> bool:
    try:
        return resolve_output(context, key).exists()
    except (
        FileNotFoundError,
        KeyError,
        TypeError,
        ValueError,
    ):
        return False


def sandbox_dir(context: dict, mode: str) -> Path:
    return (
        BASE_DIR
        / "output"
        / context["channel"]
        / context["video_id"]
        / context["run_id"]
        / mode
    )


def relative_path(path: Path) -> str:
    return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def build_base_command(
    agent_path: str,
    context: dict
) -> list[str]:
    return [
        sys.executable,
        agent_path,
        "--channel",
        context["channel"],
        "--video-id",
        context["video_id"],
    ]


def run_non_live_pipeline(
    context: dict,
    mode: str,
    config: dict
) -> None:
    output_dir = sandbox_dir(context, mode)
    output_dir.mkdir(parents=True, exist_ok=True)
    plan_path = output_dir / "ai_video_insert_plan.json"

    plan_command = build_base_command(
        "agents/ai_video_insert_plan/run.py",
        context
    ) + [
        "--count",
        str(config["insert_count"]),
        "--provider",
        config["provider"],
        "--model",
        config["model"],
        "--output-path",
        relative_path(plan_path),
    ]
    run_step("ai_video_insert_plan", plan_command)

    generation_command = build_base_command(
        "agents/ai_video_generation/run.py",
        context
    ) + [
        "--mode",
        mode,
        "--plan-path",
        relative_path(plan_path),
        "--provider",
        config["provider"],
        "--model",
        config["model"],
        "--max-items",
        str(config["insert_count"]),
    ]
    run_step("ai_video_generation", generation_command)

    if mode == "mock":
        generation_path = (
            PROJECT_ROOT
            / "agents"
            / "ai_video_generation"
            / "output"
            / context["channel"]
            / context["video_id"]
            / context["run_id"]
            / "mock"
            / "ai_video_generation.json"
        )
        qa_command = build_base_command(
            "agents/ai_video_qa/run.py",
            context
        ) + [
            "--generation-path",
            relative_path(generation_path),
            "--dry-run",
        ]
        run_step("ai_video_qa", qa_command)

    print("AI_VIDEO_PIPELINE_MODE: " + mode)
    print("PRODUCTION_API_CALLED: false")
    print("CONTEXT_CHANGED: false")
    print("STATUS: ai_video_pipeline_validation_ready")


def run_live_pipeline(
    context: dict,
    config: dict,
    confirmed: bool
) -> None:
    assert_live_generation_allowed(
        config=config,
        confirmed=confirmed
    )

    if not output_ready(context, "ai_video_insert_plan"):
        plan_command = build_base_command(
            "agents/ai_video_insert_plan/run.py",
            context
        ) + [
            "--count",
            str(config["insert_count"]),
            "--provider",
            config["provider"],
            "--model",
            config["model"],
            "--attach-context",
        ]
        run_step("ai_video_insert_plan", plan_command)
        context = load_context(
            channel=context["channel"],
            video_id=context["video_id"]
        )
    else:
        print(
            "SKIPPING_AI_VIDEO_STEP: "
            "ai_video_insert_plan outputs_already_ready"
        )

    if not output_ready(context, "ai_video_generation"):
        generation_command = build_base_command(
            "agents/ai_video_generation/run.py",
            context
        ) + [
            "--mode",
            "live",
            "--provider",
            config["provider"],
            "--model",
            config["model"],
            "--max-items",
            str(config["insert_count"]),
            "--attach-context",
            "--confirm-live-cost",
        ]
        run_step("ai_video_generation", generation_command)
        context = load_context(
            channel=context["channel"],
            video_id=context["video_id"]
        )
    else:
        print(
            "SKIPPING_AI_VIDEO_STEP: "
            "ai_video_generation outputs_already_ready"
        )

    if not output_ready(context, "ai_video_qa"):
        qa_command = build_base_command(
            "agents/ai_video_qa/run.py",
            context
        ) + ["--attach-context"]
        run_step("ai_video_qa", qa_command)
        context = load_context(
            channel=context["channel"],
            video_id=context["video_id"]
        )
    else:
        print(
            "SKIPPING_AI_VIDEO_STEP: "
            "ai_video_qa outputs_already_ready"
        )

    qa_path = resolve_output(context, "ai_video_qa")
    qa_data = read_json(qa_path)

    if qa_data.get("status") != "approved":
        raise RuntimeError(
            "Live AI video QA is not approved."
        )

    context = mark_ai_video_context_ready(
        context=context,
        config=config
    )
    save_context(context)

    print("AI_VIDEO_PIPELINE_MODE: live")
    print("PRODUCTION_API_CALLED: true")
    print("CONTEXT_CHANGED: true")
    print("STATUS: ai_video_pipeline_production_ready")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the resumable AI video insert pipeline. "
            "Live mode is protected by config, environment, "
            "and explicit cost confirmation."
        )
    )
    parser.add_argument("--channel", default=DEFAULT_CHANNEL)
    parser.add_argument("--video-id", required=True)
    parser.add_argument(
        "--mode",
        choices=sorted(VALID_MODES),
        default="dry-run"
    )
    parser.add_argument(
        "--confirm-live-cost",
        action="store_true"
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    context = load_context(
        channel=args.channel.lower(),
        video_id=args.video_id.lower()
    )
    config = load_ai_video_production_config()

    print(f"VIDEO_CONTEXT_ID: {context['video_id']}")
    print(f"RUN_ID: {context['run_id']}")
    print(f"AI_VIDEO_MODE: {args.mode}")
    print(f"PROVIDER: {config['provider']}")
    print(f"MODEL: {config['model']}")

    if args.mode == "live":
        run_live_pipeline(
            context=context,
            config=config,
            confirmed=args.confirm_live_cost
        )
    else:
        run_non_live_pipeline(
            context=context,
            mode=args.mode,
            config=config
        )


if __name__ == "__main__":
    main()
