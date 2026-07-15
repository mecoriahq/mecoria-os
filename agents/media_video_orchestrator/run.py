import argparse
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.content_usage_registry import (
    register_context_content,
)
from core.media_context_integrity import (
    validate_media_context,
)
from core.video_run_context import (
    assert_topic_approved,
    load_context,
    resolve_output,
    resolve_source,
    save_context,
    set_status,
)


TERMINAL_STATES = {
    "uploaded_for_founder_review",
    "published",
    "public",
}

CONTENT_OUTPUTS = {
    "script": ["script"],
    "seo": ["seo"],
    "qa": ["qa"],
}

PRODUCTION_OUTPUTS = {
    "video_audio_pipeline": [
        "audio_assembly",
        "narration_audio",
    ],
    "video_visual_pipeline": [
        "ai_visual_generation",
        "ai_visual_qa",
        "thumbnail",
        "thumbnail_record",
        "visual_plan",
    ],
    "video_stock_pipeline": [
        "stock_manifest",
        "stock_qa",
    ],
    "hybrid_video_assembly": [
        "hybrid_video_assembly",
        "final_video",
    ],
    "video_qa": [
        "video_qa",
    ],
    "video_publisher": [
        "publisher",
    ],
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_context_path(
    channel: str,
    video_id: str
) -> Path:
    return (
        PROJECT_ROOT
        / "records"
        / "run_contexts"
        / channel
        / f"{video_id}.json"
    )


def resolve_video_id(
    channel: str,
    requested: str
) -> str:
    if requested.lower() != "auto":
        video_id = requested.lower()

        if not re.fullmatch(
            r"video_\d{3,}",
            video_id
        ):
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
        for path in context_dir.glob(
            "video_*.json"
        ):
            match = re.fullmatch(
                r"video_(\d+)",
                path.stem
            )

            if match:
                numbers.append(
                    int(match.group(1))
                )

    return (
        f"video_{max(numbers, default=0) + 1:03d}"
    )


def run_step(
    name: str,
    command: list[str]
) -> None:
    print(
        f"RUNNING_AGENT: {name}",
        flush=True
    )

    result = subprocess.run(
        command,
        cwd=PROJECT_ROOT
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Agent failed: {name} "
            f"(exit code {result.returncode})"
        )


def build_agent_command(
    agent_path: str,
    channel: str,
    video_id: str
) -> list[str]:
    return [
        sys.executable,
        agent_path,
        "--channel",
        channel,
        "--video-id",
        video_id,
    ]


def reference_exists(
    context: dict,
    key: str
) -> bool:
    if key in context.get("outputs", {}):
        try:
            resolve_output(
                context=context,
                key=key
            )
            return True
        except (
            FileNotFoundError,
            KeyError,
            TypeError,
            ValueError,
        ):
            return False

    if key in context.get("sources", {}):
        try:
            resolve_source(
                context=context,
                key=key
            )
            return True
        except (
            FileNotFoundError,
            KeyError,
            TypeError,
            ValueError,
        ):
            return False

    return False


def outputs_ready(
    context: dict,
    keys: list[str]
) -> bool:
    return all(
        reference_exists(context, key)
        for key in keys
    )


def append_history(
    context: dict,
    agent: str,
    status: str,
    reference: str | None = None
) -> None:
    record = {
        "agent": agent,
        "status": status,
        "recorded_at": utc_now(),
    }

    if reference:
        record["output_reference"] = reference

    context.setdefault(
        "history",
        []
    ).append(record)


def topic_is_approved(
    context: dict
) -> bool:
    return (
        context.get(
            "release",
            {}
        ).get("topic_approved")
        is True
    )


def require_topic_approval(
    context: dict
) -> dict:
    if topic_is_approved(context):
        return context

    context.setdefault(
        "release",
        {}
    ).update({
        "topic_approved": False,
        "public_release_approved": False,
    })

    context.setdefault(
        "quality_gates",
        {}
    )["require_topic_approval"] = True

    context = set_status(
        context=context,
        status="topic_approval_required",
        next_agent="founder_topic_approval"
    )

    return context


def approve_topic(
    context: dict
) -> dict:
    if context.get("status") in TERMINAL_STATES:
        raise ValueError(
            "A terminal video cannot receive "
            "a new topic approval."
        )

    context.setdefault(
        "release",
        {}
    ).update({
        "topic_approved": True,
        "topic_approved_at": utc_now(),
        "topic_approved_by": "founder",
        "public_release_approved": False,
    })

    context.setdefault(
        "quality_gates",
        {}
    )["require_topic_approval"] = True

    append_history(
        context=context,
        agent="founder_topic_approval",
        status="approved"
    )

    return set_status(
        context=context,
        status="topic_approved",
        next_agent="script"
    )


def attach_stock_manifest(
    context: dict,
    requested_path: str
) -> dict:
    path = Path(requested_path)

    if not path.is_absolute():
        path = PROJECT_ROOT / path

    path = path.resolve()
    root = PROJECT_ROOT.resolve()

    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise ValueError(
            "Stock manifest must be inside "
            "the repository."
        ) from exc

    if not path.exists():
        raise FileNotFoundError(
            f"Stock manifest not found: {path}"
        )

    reference = str(relative).replace(
        "\\",
        "/"
    )

    if reference.lower().endswith(
        "/latest.json"
    ):
        raise ValueError(
            "Stock manifest cannot use latest.json."
        )

    context.setdefault(
        "sources",
        {}
    )["stock_manifest"] = reference

    append_history(
        context=context,
        agent="media_video_orchestrator",
        status="stock_manifest_attached",
        reference=reference
    )

    return context


def run_new_topic_proposal(
    channel: str,
    video_id: str,
    selected_index: int | None
) -> dict:
    research_command = build_agent_command(
        "agents/research/run.py",
        channel,
        video_id
    )

    selector_command = build_agent_command(
        "agents/content_idea_selector/run.py",
        channel,
        video_id
    )

    if selected_index is not None:
        selector_command.extend([
            "--selected-index",
            str(selected_index)
        ])

    run_step(
        "research",
        research_command
    )
    run_step(
        "content_idea_selector",
        selector_command
    )

    context = load_context(
        channel=channel,
        video_id=video_id
    )

    context = require_topic_approval(
        context
    )
    save_context(context)

    return context


def run_agent_if_missing(
    context: dict,
    agent_name: str,
    agent_path: str,
    required_outputs: list[str]
) -> dict:
    if outputs_ready(
        context,
        required_outputs
    ):
        print(
            f"SKIPPING_AGENT: {agent_name} "
            "outputs_already_ready"
        )
        return context

    run_step(
        agent_name,
        build_agent_command(
            agent_path=agent_path,
            channel=context["channel"],
            video_id=context["video_id"]
        )
    )

    context = load_context(
        channel=context["channel"],
        video_id=context["video_id"]
    )

    if not outputs_ready(
        context,
        required_outputs
    ):
        raise RuntimeError(
            f"Agent completed without required "
            f"outputs: {agent_name}"
        )

    return context


def run_content_phase(
    context: dict
) -> dict:
    assert_topic_approved(context)

    steps = [
        (
            "script",
            "agents/script/run.py",
            CONTENT_OUTPUTS["script"]
        ),
        (
            "seo",
            "agents/seo/run.py",
            CONTENT_OUTPUTS["seo"]
        ),
        (
            "qa",
            "agents/qa/run.py",
            CONTENT_OUTPUTS["qa"]
        ),
    ]

    for name, path, outputs in steps:
        context = run_agent_if_missing(
            context=context,
            agent_name=name,
            agent_path=path,
            required_outputs=outputs
        )

    qa_data = load_context_record(
        context=context,
        key="qa"
    )

    if qa_data.get("status") != "approved":
        raise ValueError(
            "Content QA is not approved."
        )

    content_result = register_context_content(
        context=context
    )

    context.setdefault(
        "quality_gates",
        {}
    ).update({
        "require_content_fingerprint": True,
        "allow_cross_video_content_reuse": False,
    })

    append_history(
        context=context,
        agent="content_fingerprint_gate",
        status="approved",
        reference=str(
            content_result["registry_path"]
            .relative_to(PROJECT_ROOT)
        ).replace("\\", "/")
    )

    context = set_status(
        context=context,
        status="content_qa_ready",
        next_agent="video_audio_pipeline"
    )

    save_context(context)
    return context


def load_context_record(
    context: dict,
    key: str
) -> dict:
    import json

    if key in context.get("outputs", {}):
        path = resolve_output(
            context=context,
            key=key
        )
    else:
        path = resolve_source(
            context=context,
            key=key
        )

    return json.loads(
        path.read_text(encoding="utf-8-sig")
    )


def run_audio_and_visual_phase(
    context: dict
) -> dict:
    context = run_agent_if_missing(
        context=context,
        agent_name="video_audio_pipeline",
        agent_path=(
            "agents/video_audio_pipeline/run.py"
        ),
        required_outputs=PRODUCTION_OUTPUTS[
            "video_audio_pipeline"
        ]
    )

    context = run_agent_if_missing(
        context=context,
        agent_name="video_visual_pipeline",
        agent_path=(
            "agents/video_visual_pipeline/run.py"
        ),
        required_outputs=PRODUCTION_OUTPUTS[
            "video_visual_pipeline"
        ]
    )

    content_result = register_context_content(
        context=context
    )

    append_history(
        context=context,
        agent="visual_content_fingerprint_gate",
        status="approved",
        reference=str(
            content_result["registry_path"]
            .relative_to(PROJECT_ROOT)
        ).replace("\\", "/")
    )

    save_context(context)
    return context


def stock_source_available(
    context: dict
) -> bool:
    if outputs_ready(
        context,
        PRODUCTION_OUTPUTS[
            "video_stock_pipeline"
        ]
    ):
        return True

    return reference_exists(
        context,
        "stock_manifest"
    )


def set_stock_source_required(
    context: dict
) -> dict:
    context = set_status(
        context=context,
        status="stock_source_required",
        next_agent="video_stock_pipeline"
    )

    append_history(
        context=context,
        agent="media_video_orchestrator",
        status="stock_source_required"
    )

    save_context(context)
    return context


def run_stock_phase(
    context: dict
) -> dict:
    return run_agent_if_missing(
        context=context,
        agent_name="video_stock_pipeline",
        agent_path=(
            "agents/video_stock_pipeline/run.py"
        ),
        required_outputs=PRODUCTION_OUTPUTS[
            "video_stock_pipeline"
        ]
    )


def run_render_and_delivery_phase(
    context: dict
) -> dict:
    pre_render_result = validate_media_context(
        context=context
    )

    print(
        "PRE_RENDER_VALIDATED_ASSETS: "
        f"{pre_render_result['validated_asset_count']}"
    )

    steps = [
        (
            "hybrid_video_assembly",
            "agents/hybrid_video_assembly/run.py",
        ),
        (
            "video_qa",
            "agents/video_qa/run.py",
        ),
        (
            "video_publisher",
            "agents/video_publisher/run.py",
        ),
    ]

    for name, path in steps:
        context = run_agent_if_missing(
            context=context,
            agent_name=name,
            agent_path=path,
            required_outputs=PRODUCTION_OUTPUTS[name]
        )

    final_result = validate_media_context(
        context=context
    )

    append_history(
        context=context,
        agent="media_context_integrity",
        status="passed"
    )

    if context.get("status") not in TERMINAL_STATES:
        context = set_status(
            context=context,
            status="founder_review_required",
            next_agent="founder_video_review"
        )

    context.setdefault(
        "release",
        {}
    )["public_release_approved"] = False

    save_context(context)

    print(
        "FINAL_VALIDATED_JSON_RECORDS: "
        f"{final_result['validated_json_record_count']}"
    )
    print(
        "FINAL_VALIDATED_ASSETS: "
        f"{final_result['validated_asset_count']}"
    )
    print(
        "FINAL_VALIDATED_CONTENT_RECORDS: "
        f"{final_result['validated_content_record_count']}"
    )

    return context


def print_topic_gate(
    context: dict
) -> None:
    print("STATUS: topic_approval_required")
    print(
        f"SELECTED_TOPIC: {context['topic_title']}"
    )
    print(
        "NEXT_COMMAND: python "
        "agents/media_video_orchestrator/run.py "
        f"--channel {context['channel']} "
        f"--video-id {context['video_id']} "
        "--approve-topic"
    )


def print_stock_gate(
    context: dict
) -> None:
    print("STATUS: stock_source_required")
    print(
        f"VIDEO_CONTEXT_ID: {context['video_id']}"
    )
    print(
        "REASON: No approved video-specific "
        "stock manifest is attached."
    )
    print(
        "OLD_STOCK_REUSE: blocked"
    )
    print(
        "NEXT_COMMAND: python "
        "agents/media_video_orchestrator/run.py "
        f"--channel {context['channel']} "
        f"--video-id {context['video_id']} "
        "--stock-manifest "
        "<repo-relative-manifest-path>"
    )


def print_dry_run(
    channel: str,
    video_id: str,
    context_exists: bool,
    context: dict | None
) -> None:
    print(f"CHANNEL: {channel}")
    print(f"VIDEO_CONTEXT_ID: {video_id}")
    print(
        f"RUN_ID: {channel}_{video_id}_v1"
        if not context
        else f"RUN_ID: {context['run_id']}"
    )
    print("LATEST_JSON_INPUTS: blocked")
    print("LEGACY_PRODUCTION_AGENTS: blocked")

    if not context_exists:
        print(
            "PLAN: research -> content_idea_selector "
            "-> topic_approval_required"
        )
        print(
            "PRODUCTION_AFTER_APPROVAL: "
            "script -> seo -> qa -> content_fingerprint "
            "-> video_audio_pipeline "
            "-> video_visual_pipeline "
            "-> stock_source_gate "
            "-> video_stock_pipeline "
            "-> hybrid_video_assembly "
            "-> video_qa "
            "-> video_publisher "
            "-> media_context_integrity "
            "-> founder_review_required"
        )
        print("STATUS: new_video_dry_run_ready")
        return

    print(
        f"CURRENT_STATUS: {context.get('status')}"
    )
    print(
        f"CURRENT_NEXT_AGENT: "
        f"{context.get('next_agent')}"
    )
    print(
        f"TOPIC_APPROVED: "
        f"{topic_is_approved(context)}"
    )

    if context.get("status") in TERMINAL_STATES:
        print("PLAN: no_production_action")
    elif not topic_is_approved(context):
        print("PLAN: founder_topic_approval")
    elif not stock_source_available(context):
        print(
            "PLAN: resume_content_and_assets_then_"
            "stop_at_stock_source_required"
        )
    else:
        print(
            "PLAN: resume_from_missing_output_to_"
            "founder_review_required"
        )

    print("STATUS: existing_video_dry_run_ready")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the complete video-specific Mecoria "
            "Media production pipeline with founder "
            "approval and stock-source gates."
        )
    )

    parser.add_argument(
        "--channel",
        default="hiddenova"
    )
    parser.add_argument(
        "--video-id",
        default="auto"
    )
    parser.add_argument(
        "--selected-index",
        type=int,
        default=None
    )
    parser.add_argument(
        "--approve-topic",
        action="store_true"
    )
    parser.add_argument(
        "--stock-manifest",
        default=None
    )
    parser.add_argument(
        "--resume",
        action="store_true"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true"
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    channel = args.channel.lower()

    if (
        args.video_id.lower() == "auto"
        and args.approve_topic
    ):
        raise ValueError(
            "--approve-topic requires an existing video_id."
        )

    video_id = resolve_video_id(
        channel=channel,
        requested=args.video_id
    )

    context_path = get_context_path(
        channel,
        video_id
    )
    exists = context_path.exists()

    context = (
        load_context(
            channel=channel,
            video_id=video_id
        )
        if exists
        else None
    )

    if args.dry_run:
        print_dry_run(
            channel=channel,
            video_id=video_id,
            context_exists=exists,
            context=context
        )
        return

    if not exists:
        context = run_new_topic_proposal(
            channel=channel,
            video_id=video_id,
            selected_index=args.selected_index
        )

        print_topic_gate(context)
        return

    if context.get("status") in TERMINAL_STATES:
        result = validate_media_context(
            context=context
        )

        print(
            f"STATUS: {context['status']}"
        )
        print(
            "MEDIA_CONTEXT_INTEGRITY: "
            f"{result['status']}"
        )
        print("PRODUCTION_ACTION: none")
        return

    if args.approve_topic:
        context = approve_topic(context)
        save_context(context)

        print(
            f"TOPIC_APPROVED: "
            f"{context['topic_title']}"
        )

    if not topic_is_approved(context):
        context = require_topic_approval(
            context
        )
        save_context(context)
        print_topic_gate(context)
        return

    if (
        not args.resume
        and not args.approve_topic
        and not args.stock_manifest
    ):
        print(
            f"STATUS: {context['status']}"
        )
        print(
            f"NEXT_AGENT: {context.get('next_agent')}"
        )
        print(
            "NO_ACTION: Use --resume to continue."
        )
        return

    if args.stock_manifest:
        context = attach_stock_manifest(
            context=context,
            requested_path=args.stock_manifest
        )
        save_context(context)

    context = run_content_phase(context)
    context = run_audio_and_visual_phase(
        context
    )

    if not stock_source_available(context):
        context = set_stock_source_required(
            context
        )
        print_stock_gate(context)
        return

    context = run_stock_phase(context)
    context = run_render_and_delivery_phase(
        context
    )

    print(
        "Media Video Orchestrator completed successfully."
    )
    print(f"TOPIC: {context['topic_title']}")
    print(f"STATUS: {context['status']}")
    print(f"NEXT_AGENT: {context['next_agent']}")
    print("PUBLIC_RELEASE: blocked_pending_founder")


if __name__ == "__main__":
    main()
