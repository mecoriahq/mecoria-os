import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.content_quality import (
    DEFAULT_EDITORIAL_OVERALL_MIN,
    DEFAULT_HIDDENOVA_BRAND_INTRO_MIN,
    DEFAULT_HOOK_INTRO_DISTINCTNESS_MIN,
    DEFAULT_HOOK_STRENGTH_MIN,
    DEFAULT_MEDIA_DURATION_MAX_SECONDS,
    DEFAULT_MEDIA_DURATION_MIN_SECONDS,
    DEFAULT_NARRATIVE_SPINE_MIN,
    DEFAULT_REPETITION_RISK_MIN,
    DEFAULT_SCRIPT_WORD_MAX,
    DEFAULT_SCRIPT_WORD_MIN,
    DEFAULT_SPECIFICITY_MIN,
    DEFAULT_STANDARD_CTA_MIN,
    DEFAULT_TITLE_THUMBNAIL_SYNERGY_MIN,
    evaluate_qa_editorial_gate,
    evaluate_script_word_count,
)
from core.script_preflight import (
    evaluate_script_preflight,
)
from core.channel_content_policy import (
    apply_profile_quality_gates,
    factual_pipeline_required,
    load_editorial_profile,
)
from core.content_usage_registry import (
    register_context_content,
    remove_video_content_records,
)
from core.media_context_integrity import (
    validate_media_context,
)
from core.ai_video_integration import (
    apply_visual_diversity_gates,
    load_ai_video_production_config,
)
from core.video_run_context import (
    assert_topic_approved,
    load_context,
    resolve_output,
    resolve_source,
    save_context,
    set_status,
)


LEGACY_THUMBNAIL_V2_COMPATIBILITY = {
    "thumbnail_style": "hiddenova_cinematic_v2",
    "thumbnail_standard_name": "hiddenova_cinematic_v2",
}


TERMINAL_STATES = {
    "uploaded_for_founder_review",
    "published",
    "public",
}

CONTENT_OUTPUTS = {
    "factual_research": ["factual_research"],
    "claims_ledger": ["claims_ledger"],
    "script": ["script"],
    "seo": ["seo"],
    "fact_risk_qa": [
        "fact_qa",
        "risk_review",
        "fact_risk_qa",
    ],
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
    "ai_video_pipeline": [
        "ai_video_insert_plan",
        "ai_video_generation",
        "ai_video_qa",
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


EDITORIAL_STANDARD_VERSION = "hiddenova_editorial_v2"


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


def apply_production_quality_standard(
    context: dict
) -> dict:
    channel = str(context.get("channel") or "hiddenova").lower()
    profile = load_editorial_profile(channel)
    gates = context.setdefault("quality_gates", {})
    standard_version = profile["profile_name"]
    previous_standard_version = gates.get(
        "editorial_standard_version"
    )
    total_revision_count = int(
        gates.get("editorial_revision_count", 0)
    )
    duration_revision_count = int(
        gates.get("audio_duration_revision_count", 0)
    )
    adjusted_word_min = gates.get(
        "target_script_word_count_min"
    )
    adjusted_word_max = gates.get(
        "target_script_word_count_max"
    )

    if previous_standard_version != standard_version:
        gates["editorial_standard_revision_count"] = 0
        gates["editorial_quality_gate_passed"] = False

        if previous_standard_version or total_revision_count > 0:
            previous_label = (
                str(previous_standard_version)
                if previous_standard_version
                else "legacy"
            )
            append_history(
                context=context,
                agent="editorial_standard_migration",
                status="revision_budget_reset",
                reference=(
                    f"from={previous_label};"
                    f"to={standard_version};"
                    "preserved_total_revisions="
                    f"{total_revision_count}"
                )
            )
            print(
                "EDITORIAL_STANDARD_MIGRATION: "
                f"{previous_label} -> {standard_version}",
                flush=True
            )
            print(
                "EDITORIAL_STANDARD_REVISION_BUDGET: reset",
                flush=True
            )

    context = apply_profile_quality_gates(
        context=context,
        profile=profile,
    )
    gates = context["quality_gates"]

    if duration_revision_count > 0:
        if adjusted_word_min is not None:
            gates["target_script_word_count_min"] = int(
                adjusted_word_min
            )
        if adjusted_word_max is not None:
            gates["target_script_word_count_max"] = int(
                adjusted_word_max
            )

    gates.update({
        "require_actual_chapters": True,
        "chapter_timing_source": "actual_audio_sections",
        "max_audio_duration_revision_attempts": int(
            gates.get(
                "max_audio_duration_revision_attempts",
                2
            )
        ),
        "editorial_revision_count": int(
            gates.get("editorial_revision_count", 0)
        ),
        "editorial_standard_revision_count": int(
            gates.get("editorial_standard_revision_count", 0)
        ),
        "thumbnail_previous_standard_name": (
            "hiddenova_cinematic_v2"
            if channel == "hiddenova"
            else None
        ),
        "thumbnail_layout_signature": (
            "oversized_headline_left__dominant_subject_right"
        ),
        "thumbnail_gold_reference_required": bool(
            channel == "hiddenova"
        ),
        "thumbnail_text_position": "left",
        "thumbnail_subject_position": "right",
        "thumbnail_two_color_required": True,
        "thumbnail_candidate_count": 3,
        "thumbnail_finalist_count": 2,
        "thumbnail_vision_qa_required": True,
        "thumbnail_minimum_final_score": 85,
    })

    context = apply_visual_diversity_gates(
        context=context,
        config=load_ai_video_production_config()
    )

    return context


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

    context = apply_production_quality_standard(context)
    profile = load_editorial_profile(
        str(context.get("channel") or "hiddenova")
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

    next_agent = (
        "factual_research"
        if factual_pipeline_required(profile)
        else "script"
    )

    return set_status(
        context=context,
        status="topic_approved",
        next_agent=next_agent
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



def evaluate_context_script_preflight(
    *,
    context: dict,
    script_data: dict,
    profile: dict | None = None,
) -> dict:
    editorial_profile = profile or load_editorial_profile(
        str(context.get("channel") or "hiddenova")
    )
    script_policy = editorial_profile.get(
        "script",
        {},
    )
    gates = context.get(
        "quality_gates",
        {},
    )

    return evaluate_script_preflight(
        script_data=script_data,
        target_minimum=int(
            gates.get(
                "target_script_word_count_min",
                DEFAULT_SCRIPT_WORD_MIN,
            )
        ),
        target_maximum=int(
            gates.get(
                "target_script_word_count_max",
                DEFAULT_SCRIPT_WORD_MAX,
            )
        ),
        absolute_floor=int(
            script_policy.get(
                "pre_audio_word_floor",
                1100,
            )
        ),
        minimum_ratio=float(
            script_policy.get(
                "pre_audio_minimum_ratio",
                0.85,
            )
        ),
        audio_duration_authoritative=bool(
            script_policy.get(
                "audio_duration_authoritative",
                False,
            )
        ),
    )


def invalidate_bad_content_outputs(
    context: dict
) -> dict:
    duration_revision_required = (
        context.get("status")
        == "audio_duration_revision_required"
    )

    script_ready = reference_exists(
        context,
        "script"
    )

    if not script_ready:
        return context

    script_data = load_context_record(
        context=context,
        key="script"
    )

    preflight_gate = evaluate_context_script_preflight(
        context=context,
        script_data=script_data,
    )

    if (
        preflight_gate["accepted"]
        and not duration_revision_required
    ):
        return context

    removed_outputs = []

    for key in (
        "script",
        "seo",
        "fact_qa",
        "risk_review",
        "fact_risk_qa",
        "qa",
        "voice",
        "voice_generation",
        "audio_qa",
        "audio_assembly",
        "narration_audio",
        "visual_plan",
        "ai_visual_generation",
        "ai_visual_qa",
        "thumbnail",
        "thumbnail_record",
        "ai_video_insert_plan",
        "ai_video_generation",
        "ai_video_qa",
        "hybrid_video_assembly",
        "final_video",
        "video_qa",
        "publisher",
    ):
        if key in context.get("outputs", {}):
            context["outputs"].pop(key)
            removed_outputs.append(key)

    removed_registry_records = (
        remove_video_content_records(
            channel=context["channel"],
            video_id=context["video_id"],
            record_types=[
                "script",
                "seo"
            ]
        )
    )

    append_history(
        context=context,
        agent=(
            "audio_duration_gate"
            if duration_revision_required
            else "content_word_count_gate"
        ),
        status="invalidated",
        reference=(
            "word_count="
            f"{preflight_gate['word_count']};"
            "reason="
            f"{'audio_duration' if duration_revision_required else 'word_count'};"
            "removed_outputs="
            f"{','.join(removed_outputs)};"
            "removed_registry_records="
            f"{removed_registry_records}"
        )
    )

    context = set_status(
        context=context,
        status="topic_approved",
        next_agent="script"
    )

    save_context(context)

    print(
        "INVALIDATED_CONTENT_OUTPUTS: "
        f"{removed_outputs}"
    )
    print(
        "REMOVED_CONTENT_REGISTRY_RECORDS: "
        f"{removed_registry_records}"
    )
    print(
        "CONTENT_INVALIDATION_REASON: "
        f"{'audio_duration' if duration_revision_required else 'word_count'}"
    )

    return context


def get_editorial_thresholds(
    context: dict
) -> dict:
    gates = context.get(
        "quality_gates",
        {}
    )

    thresholds = {
        "hook_strength": int(
            gates.get(
                "minimum_hook_strength_score",
                DEFAULT_HOOK_STRENGTH_MIN
            )
        ),
        "hook_intro_distinctness": int(
            gates.get(
                "minimum_hook_intro_distinctness_score",
                DEFAULT_HOOK_INTRO_DISTINCTNESS_MIN
            )
        ),
        "narrative_spine": int(
            gates.get(
                "minimum_narrative_spine_score",
                DEFAULT_NARRATIVE_SPINE_MIN
            )
        ),
        "specificity": int(
            gates.get(
                "minimum_specificity_score",
                DEFAULT_SPECIFICITY_MIN
            )
        ),
        "repetition_risk": int(
            gates.get(
                "minimum_repetition_risk_score",
                DEFAULT_REPETITION_RISK_MIN
            )
        ),
        "title_thumbnail_synergy": int(
            gates.get(
                "minimum_title_thumbnail_synergy_score",
                DEFAULT_TITLE_THUMBNAIL_SYNERGY_MIN
            )
        ),
    }

    if gates.get("require_channel_brand_intro", False):
        thresholds["hiddenova_brand_intro"] = int(
            DEFAULT_HIDDENOVA_BRAND_INTRO_MIN
        )

    if gates.get("require_standard_cta", False):
        thresholds["standard_cta"] = int(
            DEFAULT_STANDARD_CTA_MIN
        )

    return thresholds


def write_editorial_revision_brief(
    context: dict,
    qa_data: dict,
    gate_result: dict
) -> dict:
    profile = load_editorial_profile(
        str(context.get("channel") or "hiddenova")
    )
    gates = context.setdefault("quality_gates", {})
    revision_count = int(
        gates.get("editorial_revision_count", 0)
    ) + 1
    standard_revision_count = int(
        gates.get("editorial_standard_revision_count", 0)
    ) + 1

    brief_dir = (
        PROJECT_ROOT
        / "records"
        / "run_contexts"
        / context["channel"]
        / context["video_id"]
        / "inputs"
    )
    brief_dir.mkdir(parents=True, exist_ok=True)
    brief_path = brief_dir / (
        "editorial_revision_"
        f"{revision_count:02d}.json"
    )
    instructions = [
        "Strengthen the first 120 words with a concrete tension, "
        "paradox, decision, or consequence.",
        "Make the introduction advance the story instead of "
        "restating the hook.",
        "Use one cause-and-effect narrative spine rather than "
        "list-like exposition.",
        "Replace abstract filler with concrete mechanisms, dates, "
        "decisions, and consequences supported by approved research.",
        "Create a direct title and an ALL-CAPS 2-4 word thumbnail "
        "phrase that add different information.",
        "End with a concise CTA that explicitly asks viewers to "
        "comment, like, and subscribe.",
        "Return no estimated chapter timestamps.",
    ]

    if profile["script"]["brand_intro"]["required"]:
        instructions.append(
            "Begin the introduction with a very short brand/context "
            f"line containing the exact word {profile['display_name']} "
            f"within its first {profile['script']['brand_intro']['scan_word_limit']} words."
        )

    if factual_pipeline_required(profile):
        instructions.extend([
            "Use only approved claims from the claims ledger.",
            "Attach approved claim_ids to every factual narration block.",
            "Keep allegations attributed and never intensify certainty.",
        ])

    brief = {
        "schema_version": "1.0",
        "channel": context["channel"],
        "video_id": context["video_id"],
        "run_id": context["run_id"],
        "attempt": revision_count,
        "standard_version": profile["profile_name"],
        "standard_attempt": standard_revision_count,
        "topic_title": context["topic_title"],
        "status": "editorial_revision_required",
        "failed_checks": gate_result.get("failures", []),
        "qa_checks": qa_data.get("checks", {}),
        "issues": qa_data.get("issues", []),
        "recommendations": qa_data.get("recommendations", []),
        "mandatory_instructions": instructions,
        "created_at": utc_now(),
    }
    brief_path.write_text(
        json.dumps(brief, indent=2, ensure_ascii=True),
        encoding="utf-8"
    )
    reference = str(
        brief_path.relative_to(PROJECT_ROOT)
    ).replace("\\", "/")
    context.setdefault("sources", {})[
        "editorial_revision_brief"
    ] = reference
    gates["editorial_revision_count"] = revision_count
    gates["editorial_standard_revision_count"] = (
        standard_revision_count
    )

    removed_outputs = []
    for key in (
        "script",
        "seo",
        "fact_qa",
        "risk_review",
        "fact_risk_qa",
        "qa",
        "voice",
        "voice_generation",
        "audio_qa",
        "audio_assembly",
        "narration_audio",
        "visual_plan",
        "ai_visual_generation",
        "ai_visual_qa",
        "thumbnail",
        "thumbnail_record",
        "ai_video_insert_plan",
        "ai_video_generation",
        "ai_video_qa",
        "hybrid_video_assembly",
        "final_video",
        "video_qa",
        "publisher",
    ):
        if key in context.get("outputs", {}):
            context["outputs"].pop(key)
            removed_outputs.append(key)

    removed_registry_records = remove_video_content_records(
        channel=context["channel"],
        video_id=context["video_id"],
        record_types=["script", "seo"],
    )
    append_history(
        context=context,
        agent="editorial_quality_gate",
        status="revision_required",
        reference=reference
    )
    context = set_status(
        context=context,
        status="topic_approved",
        next_agent="script"
    )
    save_context(context)

    print(
        "EDITORIAL_REVISION_REQUIRED: "
        f"attempt_{revision_count}",
        flush=True
    )
    print(
        "EDITORIAL_STANDARD_ATTEMPT: "
        f"{standard_revision_count}",
        flush=True
    )
    print(
        "EDITORIAL_REVISION_BRIEF: "
        f"{reference}",
        flush=True
    )
    print(
        "INVALIDATED_CONTENT_OUTPUTS: "
        f"{removed_outputs}",
        flush=True
    )
    print(
        "REMOVED_CONTENT_REGISTRY_RECORDS: "
        f"{removed_registry_records}",
        flush=True
    )
    return context


def write_fact_risk_revision_brief(
    context: dict,
    fact_risk_data: dict,
) -> dict:
    gate_result = {
        "failures": [
            {
                "check": "factual_grounding",
                "score": fact_risk_data.get(
                    "factual_grounding_score",
                    0,
                ),
                "minimum": 100,
            },
            {
                "check": "risk_compliance",
                "score": fact_risk_data.get(
                    "risk_compliance_score",
                    0,
                ),
                "minimum": 100,
            },
        ]
    }
    qa_data = {
        "checks": {},
        "issues": (
            fact_risk_data.get("unsupported_statements", [])
            + fact_risk_data.get("risk_issues", [])
        ),
        "recommendations": [
            {
                "field": "script",
                "suggestion": item.get(
                    "suggested_action",
                    "Revise the statement using only approved claim language.",
                ),
            }
            for item in fact_risk_data.get(
                "unsupported_statements",
                [],
            )
        ],
    }
    return write_editorial_revision_brief(
        context=context,
        qa_data=qa_data,
        gate_result=gate_result,
    )


def invalidate_factual_research_outputs(
    context: dict,
    reason: str,
    attempt: int,
) -> dict:
    removed_outputs: list[str] = []

    for key in (
        "factual_research",
        "claims_ledger",
    ):
        if key in context.get("outputs", {}):
            context["outputs"].pop(key)
            removed_outputs.append(key)

    context.setdefault("quality_gates", {})[
        "factual_research_revision_count"
    ] = int(attempt)
    append_history(
        context=context,
        agent="factual_research_quality_gate",
        status="revision_required",
        reference=(
            f"reason={reason};"
            f"attempt={attempt};"
            "removed_outputs="
            f"{','.join(removed_outputs)}"
        ),
    )
    context = set_status(
        context=context,
        status="topic_approved",
        next_agent="factual_research",
    )
    save_context(context)

    print(
        "FACTUAL_RESEARCH_REVISION_REQUIRED: "
        f"attempt_{attempt}",
        flush=True,
    )
    print(
        "FACTUAL_RESEARCH_REVISION_REASON: "
        f"{reason}",
        flush=True,
    )
    print(
        "INVALIDATED_FACTUAL_OUTPUTS: "
        f"{removed_outputs}",
        flush=True,
    )
    return context


def invalidate_stale_claims_ledger(
    context: dict,
) -> dict:
    if not reference_exists(context, "claims_ledger"):
        return context

    ledger_data = load_context_record(
        context=context,
        key="claims_ledger",
    )
    summary = ledger_data.get("summary", {})
    current_policy = (
        str(ledger_data.get("version", ""))
        == "1.1"
        and "continuation_eligible" in summary
        and "quarantined_claim_count" in summary
    )

    if current_policy:
        return context

    context.get("outputs", {}).pop(
        "claims_ledger",
        None,
    )
    append_history(
        context=context,
        agent="claims_ledger_policy_upgrade",
        status="invalidated",
        reference=(
            "reason=legacy_all_or_nothing_policy;"
            "next=claims_ledger_v1_1"
        ),
    )
    context = set_status(
        context=context,
        status="factual_research_ready",
        next_agent="claims_ledger",
    )
    save_context(context)

    print(
        "STALE_CLAIMS_LEDGER_INVALIDATED: true",
        flush=True,
    )
    return context


def run_content_phase(
    context: dict
) -> dict:
    assert_topic_approved(context)
    profile = load_editorial_profile(
        str(context.get("channel") or "hiddenova")
    )
    requires_factual = factual_pipeline_required(profile)

    context = invalidate_bad_content_outputs(context)
    context = apply_production_quality_standard(context)
    save_context(context)

    if requires_factual:
        max_research_revisions = int(
            context.get("quality_gates", {}).get(
                "max_factual_research_revision_attempts",
                1,
            )
        )

        for research_attempt in range(
            max_research_revisions + 1
        ):
            context = run_agent_if_missing(
                context=context,
                agent_name="factual_research",
                agent_path="agents/factual_research/run.py",
                required_outputs=CONTENT_OUTPUTS[
                    "factual_research"
                ],
            )
            research_data = load_context_record(
                context=context,
                key="factual_research",
            )

            if research_data.get("status") != "approved":
                if research_attempt >= max_research_revisions:
                    raise RuntimeError(
                        "Factual research remained rejected after "
                        "the maximum automatic revision attempts."
                    )

                context = invalidate_factual_research_outputs(
                    context=context,
                    reason="source_validation_failed",
                    attempt=research_attempt + 1,
                )
                continue

            context = invalidate_stale_claims_ledger(
                context
            )
            context = run_agent_if_missing(
                context=context,
                agent_name="claims_ledger",
                agent_path="agents/claims_ledger/run.py",
                required_outputs=CONTENT_OUTPUTS[
                    "claims_ledger"
                ],
            )
            ledger_data = load_context_record(
                context=context,
                key="claims_ledger",
            )

            if ledger_data.get("status") == "approved":
                summary = ledger_data.get("summary", {})
                print(
                    "CLAIMS_LEDGER_CONTINUATION: approved",
                    flush=True,
                )
                print(
                    "APPROVED_CLAIM_COUNT: "
                    f"{summary.get('approved_claim_count', 0)}",
                    flush=True,
                )
                print(
                    "QUARANTINED_CLAIM_COUNT: "
                    f"{summary.get('quarantined_claim_count', 0)}",
                    flush=True,
                )
                break

            if research_attempt >= max_research_revisions:
                raise RuntimeError(
                    "Claims ledger remained rejected after the "
                    "maximum automatic research revisions."
                )

            context = invalidate_factual_research_outputs(
                context=context,
                reason="claims_ledger_rejected",
                attempt=research_attempt + 1,
            )
        else:
            raise RuntimeError(
                "Factual research pipeline did not reach approval."
            )

    while True:
        for name, agent_path, outputs in (
            (
                "script",
                "agents/script/run.py",
                CONTENT_OUTPUTS["script"],
            ),
            (
                "seo",
                "agents/seo/run.py",
                CONTENT_OUTPUTS["seo"],
            ),
        ):
            context = run_agent_if_missing(
                context=context,
                agent_name=name,
                agent_path=agent_path,
                required_outputs=outputs,
            )

        gates = context.get("quality_gates", {})
        script_data = load_context_record(
            context=context,
            key="script"
        )
        script_preflight = evaluate_context_script_preflight(
            context=context,
            script_data=script_data,
            profile=profile,
        )

        if not script_preflight["accepted"]:
            raise ValueError(
                "Content phase produced a script that failed "
                "the pre-audio narration gate."
            )

        gates["script_preflight_status"] = (
            script_preflight["status"]
        )
        gates["script_preflight_word_count"] = (
            script_preflight["word_count"]
        )
        gates["script_preflight_floor"] = (
            script_preflight["provisional_floor"]
        )

        if script_preflight["status"] == "provisional":
            append_history(
                context=context,
                agent="script_preflight_gate",
                status="provisional",
                reference=(
                    "word_count="
                    f"{script_preflight['word_count']};"
                    "target="
                    f"{script_preflight['target_minimum']}-"
                    f"{script_preflight['target_maximum']};"
                    "final_authority=actual_audio_duration"
                ),
            )

        save_context(context)

        print(
            "SCRIPT_PREFLIGHT_STATUS: "
            f"{script_preflight['status']}",
            flush=True,
        )
        print(
            "SCRIPT_PREFLIGHT_WORD_COUNT: "
            f"{script_preflight['word_count']}",
            flush=True,
        )

        if requires_factual:
            context = run_agent_if_missing(
                context=context,
                agent_name="fact_risk_qa",
                agent_path="agents/fact_risk_qa/run.py",
                required_outputs=CONTENT_OUTPUTS["fact_risk_qa"],
            )
            fact_risk_data = load_context_record(
                context=context,
                key="fact_risk_qa",
            )

            if fact_risk_data.get("status") != "approved":
                revision_count = int(
                    gates.get(
                        "editorial_standard_revision_count",
                        0,
                    )
                )
                max_revisions = int(
                    gates.get(
                        "max_editorial_revision_attempts",
                        2,
                    )
                )

                if revision_count >= max_revisions:
                    raise RuntimeError(
                        "Factual or risk review remained rejected "
                        "after the maximum automatic revisions."
                    )

                context = write_fact_risk_revision_brief(
                    context=context,
                    fact_risk_data=fact_risk_data,
                )
                continue

        context = run_agent_if_missing(
            context=context,
            agent_name="qa",
            agent_path="agents/qa/run.py",
            required_outputs=CONTENT_OUTPUTS["qa"],
        )
        qa_data = load_context_record(
            context=context,
            key="qa"
        )
        gate_result = evaluate_qa_editorial_gate(
            qa_data=qa_data,
            minimum_overall=int(
                gates.get(
                    "minimum_editorial_overall_score",
                    DEFAULT_EDITORIAL_OVERALL_MIN,
                )
            ),
            critical_thresholds=get_editorial_thresholds(context),
        )

        print(
            "EDITORIAL_QUALITY_GATE: "
            f"{gate_result['status']}",
            flush=True
        )

        for check_name, threshold in gate_result[
            "critical_thresholds"
        ].items():
            score = qa_data.get("checks", {}).get(
                check_name,
                {},
            ).get("score")
            print(
                "EDITORIAL_CHECK_"
                f"{check_name.upper()}: "
                f"{score} / {threshold}",
                flush=True
            )

        if gate_result["approved"]:
            break

        revision_count = int(
            gates.get("editorial_standard_revision_count", 0)
        )
        max_revisions = int(
            gates.get("max_editorial_revision_attempts", 2)
        )

        if revision_count >= max_revisions:
            failed = ", ".join(
                item["check"]
                for item in gate_result["failures"]
            )
            raise RuntimeError(
                "Editorial quality remained below the current "
                "production standard after the maximum automatic "
                f"revision attempts. Failed checks: {failed}."
            )

        context = write_editorial_revision_brief(
            context=context,
            qa_data=qa_data,
            gate_result=gate_result,
        )

    content_result = register_context_content(context=context)
    context.setdefault("quality_gates", {}).update({
        "require_content_fingerprint": True,
        "allow_cross_video_content_reuse": False,
        "editorial_quality_gate_passed": True,
        "factual_quality_gate_passed": (
            True if requires_factual else None
        ),
    })
    context.get("sources", {}).pop(
        "editorial_revision_brief",
        None,
    )
    append_history(
        context=context,
        agent="editorial_quality_gate",
        status="approved",
        reference=(
            "overall_score="
            f"{qa_data.get('overall_score')}"
        )
    )

    if requires_factual:
        append_history(
            context=context,
            agent="fact_risk_quality_gate",
            status="approved",
            reference="factual_grounding=100;risk_compliance=100",
        )

    append_history(
        context=context,
        agent="content_fingerprint_gate",
        status="approved",
        reference=str(
            content_result["registry_path"].relative_to(PROJECT_ROOT)
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
    max_revisions = int(
        context.get("quality_gates", {}).get(
            "max_audio_duration_revision_attempts",
            2
        )
    )

    while True:
        try:
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
            break
        except RuntimeError:
            context = load_context(
                channel=context["channel"],
                video_id=context["video_id"]
            )

            if (
                context.get("status")
                != "audio_duration_revision_required"
            ):
                raise

            revision_count = int(
                context.get("quality_gates", {}).get(
                    "audio_duration_revision_count",
                    0
                )
            )

            if revision_count > max_revisions:
                raise RuntimeError(
                    "Audio duration remained outside the "
                    "8-12 minute range after the maximum "
                    "automatic revision attempts."
                )

            print(
                "AUTO_SCRIPT_DURATION_REVISION: "
                f"attempt_{revision_count}",
                flush=True
            )

            context = run_content_phase(context)

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


def invalidate_downstream_render_outputs(
    context: dict
) -> dict:
    removed = []

    for key in (
        "hybrid_video_assembly",
        "final_video",
        "video_qa",
        "publisher",
    ):
        if key in context.get("outputs", {}):
            context["outputs"].pop(key)
            removed.append(key)

    if removed:
        append_history(
            context=context,
            agent="ai_video_downstream_invalidation",
            status="completed",
            reference=",".join(removed)
        )

    return context


def run_ai_video_phase(
    context: dict
) -> dict:
    config = load_ai_video_production_config()

    if not config.get("orchestrator_enabled", False):
        print("AI_VIDEO_ORCHESTRATOR_ENABLED: false")
        print("AI_VIDEO_LIVE_API_CALLED: false")
        return context

    if not config.get("live_generation_enabled", False):
        raise RuntimeError(
            "AI video orchestrator is enabled but live "
            "generation is disabled in config."
        )

    was_ready = outputs_ready(
        context,
        PRODUCTION_OUTPUTS["ai_video_pipeline"]
    )

    if not was_ready:
        run_step(
            "ai_video_pipeline",
            build_agent_command(
                agent_path="agents/ai_video_pipeline/run.py",
                channel=context["channel"],
                video_id=context["video_id"]
            ) + [
                "--mode",
                "live",
                "--confirm-live-cost",
            ]
        )

        context = load_context(
            channel=context["channel"],
            video_id=context["video_id"]
        )

        if not outputs_ready(
            context,
            PRODUCTION_OUTPUTS["ai_video_pipeline"]
        ):
            raise RuntimeError(
                "AI video pipeline completed without all "
                "required production outputs."
            )

        context = invalidate_downstream_render_outputs(
            context
        )
        save_context(context)
    else:
        print(
            "SKIPPING_AGENT: ai_video_pipeline "
            "outputs_already_ready"
        )

    print("AI_VIDEO_ORCHESTRATOR_ENABLED: true")
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
    profile = load_editorial_profile(channel)
    requires_factual = factual_pipeline_required(profile)
    content_flow = (
        "factual_research -> claims_ledger -> script -> seo -> "
        "fact_risk_qa -> strict_editorial_qa"
        if requires_factual
        else "script -> seo -> strict_editorial_qa"
    )

    print(f"CHANNEL: {channel}")
    print(f"VIDEO_CONTEXT_ID: {video_id}")
    print(
        f"RUN_ID: {channel}_{video_id}_v1"
        if not context
        else f"RUN_ID: {context['run_id']}"
    )
    print(
        "EDITORIAL_STANDARD: "
        f"{profile['profile_name']}"
    )
    print(
        "THUMBNAIL_STANDARD: "
        f"{profile['thumbnail']['standard_name']}"
    )
    print(
        "FACTUAL_PIPELINE_REQUIRED: "
        f"{str(requires_factual).lower()}"
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
            f"{content_flow} "
            "-> automatic_revision_if_needed "
            "-> content_fingerprint "
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

    print(f"CURRENT_STATUS: {context.get('status')}")
    print(
        f"CURRENT_NEXT_AGENT: {context.get('next_agent')}"
    )
    print(
        f"TOPIC_APPROVED: {topic_is_approved(context)}"
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
        "--stop-after-content",
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

    if context.get("status") not in TERMINAL_STATES:
        context = apply_production_quality_standard(context)
        save_context(context)

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

    if args.stop_after_content:
        print(
            "Media Video Orchestrator stopped "
            "after content validation."
        )
        print(
            f"STATUS: {context['status']}"
        )
        print(
            f"NEXT_AGENT: {context['next_agent']}"
        )
        return

    context = run_audio_and_visual_phase(
        context
    )
    context = run_ai_video_phase(context)

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
