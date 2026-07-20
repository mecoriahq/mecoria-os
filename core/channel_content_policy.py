from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CHANNEL_CONFIG_DIR = PROJECT_ROOT / "config" / "channels"
EDITORIAL_PROFILE_DIR = (
    PROJECT_ROOT / "config" / "editorial_profiles"
)


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Required file not found: {path}")

    return json.loads(path.read_text(encoding="utf-8-sig"))


def normalize_channel(channel: str) -> str:
    normalized = str(channel).strip().lower()

    if not normalized:
        raise ValueError("Channel cannot be empty.")

    return normalized


def load_channel_config(channel: str) -> dict[str, Any]:
    normalized = normalize_channel(channel)
    config = load_json(CHANNEL_CONFIG_DIR / f"{normalized}.json")

    if config.get("channel") != normalized:
        raise ValueError("Channel config identity mismatch.")

    return config


def load_editorial_profile(channel: str) -> dict[str, Any]:
    normalized = normalize_channel(channel)
    profile = load_json(
        EDITORIAL_PROFILE_DIR / f"{normalized}.json"
    )

    required = {
        "profile_name",
        "channel",
        "display_name",
        "version",
        "status",
        "topic_strategy",
        "script",
        "factuality",
        "qa",
        "thumbnail",
    }
    missing = required - set(profile)

    if missing:
        raise ValueError(
            "Editorial profile is missing fields: "
            + ", ".join(sorted(missing))
        )

    if profile.get("channel") != normalized:
        raise ValueError("Editorial profile channel mismatch.")

    if profile.get("status") != "active":
        raise ValueError(
            f"Editorial profile is not active: {normalized}"
        )

    return profile


def build_channel_description(channel: str) -> str:
    config = load_channel_config(channel)
    content = config.get("content", {})
    promise = str(content.get("core_promise", "")).strip()
    niche = str(content.get("niche", "")).strip()

    return promise or niche


def factual_pipeline_required(
    channel_or_profile: str | dict[str, Any]
) -> bool:
    profile = (
        load_editorial_profile(channel_or_profile)
        if isinstance(channel_or_profile, str)
        else channel_or_profile
    )

    return bool(
        profile.get("factuality", {}).get(
            "pipeline_required",
            False,
        )
    )


def thumbnail_standard_path(
    channel_or_profile: str | dict[str, Any]
) -> Path:
    profile = (
        load_editorial_profile(channel_or_profile)
        if isinstance(channel_or_profile, str)
        else channel_or_profile
    )
    reference = Path(
        profile["thumbnail"]["standard_path"]
    )

    if not reference.is_absolute():
        reference = PROJECT_ROOT / reference

    return reference


def build_visual_quality_gates(
    profile: dict[str, Any]
) -> dict[str, Any]:
    visual = profile.get("visual_quality")

    if visual is None:
        return {}

    if not isinstance(visual, dict):
        raise ValueError(
            "visual_quality must be an object."
        )

    required = {
        "standard_name",
        "minimum_ai_insert_count",
        "minimum_stock_clip_count",
        "minimum_hybrid_stock_clip_count",
        "minimum_combined_visual_asset_count",
        "minimum_stock_duration_seconds",
        "minimum_distinct_stock_roles",
        "maximum_single_stock_clip_share",
        "maximum_stock_source_clip_share",
        "maximum_stock_segments_per_clip",
        "minimum_timeline_cycle_coverage",
        "maximum_timeline_cycles",
        "maximum_ai_image_segment_seconds",
        "maximum_ai_image_uses",
        "minimum_ai_reuse_gap_seconds",
        "maximum_average_visual_hold_seconds",
        "maximum_p95_visual_hold_seconds",
        "require_visual_pacing_qa",
    }
    missing = required - set(visual)

    if missing:
        raise ValueError(
            "visual_quality is missing fields: "
            + ", ".join(sorted(missing))
        )

    minimum_ai = int(
        visual["minimum_ai_insert_count"]
    )
    minimum_stock = int(
        visual["minimum_hybrid_stock_clip_count"]
    )
    minimum_combined = int(
        visual["minimum_combined_visual_asset_count"]
    )
    maximum_ai_hold = float(
        visual["maximum_ai_image_segment_seconds"]
    )
    maximum_average_hold = float(
        visual["maximum_average_visual_hold_seconds"]
    )
    maximum_p95_hold = float(
        visual["maximum_p95_visual_hold_seconds"]
    )

    if minimum_ai <= 0 or minimum_stock <= 0:
        raise ValueError(
            "Visual asset minimums must be positive."
        )

    if minimum_combined < minimum_ai + minimum_stock:
        raise ValueError(
            "Combined visual minimum cannot be below "
            "the AI plus stock minimum."
        )

    if not (
        0 < float(
            visual["maximum_stock_source_clip_share"]
        ) <= 1
    ):
        raise ValueError(
            "maximum_stock_source_clip_share must be "
            "between 0 and 1."
        )

    if not (
        maximum_average_hold
        <= maximum_p95_hold
        <= maximum_ai_hold
    ):
        raise ValueError(
            "Visual hold thresholds must satisfy "
            "average <= p95 <= AI maximum."
        )

    return {
        "visual_quality_standard_version": str(
            visual["standard_name"]
        ),
        "minimum_ai_insert_count": minimum_ai,
        "minimum_stock_clip_count": int(
            visual["minimum_stock_clip_count"]
        ),
        "minimum_hybrid_stock_clip_count": minimum_stock,
        "minimum_combined_visual_asset_count": (
            minimum_combined
        ),
        "minimum_stock_duration_seconds": float(
            visual["minimum_stock_duration_seconds"]
        ),
        "minimum_distinct_stock_roles": int(
            visual["minimum_distinct_stock_roles"]
        ),
        "maximum_single_stock_clip_share": float(
            visual["maximum_single_stock_clip_share"]
        ),
        "maximum_stock_source_clip_share": float(
            visual["maximum_stock_source_clip_share"]
        ),
        "maximum_stock_segments_per_clip": int(
            visual["maximum_stock_segments_per_clip"]
        ),
        "minimum_timeline_cycle_coverage": float(
            visual["minimum_timeline_cycle_coverage"]
        ),
        "maximum_timeline_cycles": int(
            visual["maximum_timeline_cycles"]
        ),
        "maximum_ai_image_segment_seconds": (
            maximum_ai_hold
        ),
        "maximum_ai_image_uses": int(
            visual["maximum_ai_image_uses"]
        ),
        "minimum_ai_reuse_gap_seconds": float(
            visual["minimum_ai_reuse_gap_seconds"]
        ),
        "maximum_average_visual_hold_seconds": (
            maximum_average_hold
        ),
        "maximum_p95_visual_hold_seconds": (
            maximum_p95_hold
        ),
        "require_visual_pacing_qa": bool(
            visual["require_visual_pacing_qa"]
        ),
    }


def build_quality_gates(
    profile: dict[str, Any]
) -> dict[str, Any]:
    script = profile["script"]
    factuality = profile["factuality"]
    qa = profile["qa"]
    thumbnail = profile["thumbnail"]
    brand_intro = script["brand_intro"]

    return {
        "editorial_standard_version": profile["profile_name"],
        "target_script_word_count_min": int(
            script["word_count_min"]
        ),
        "target_script_word_count_max": int(
            script["word_count_max"]
        ),
        "target_audio_duration_min_seconds": int(
            script["duration_min_seconds"]
        ),
        "target_audio_duration_max_seconds": int(
            script["duration_max_seconds"]
        ),
        "target_video_duration_min_seconds": int(
            script["duration_min_seconds"]
        ),
        "target_video_duration_max_seconds": int(
            script["duration_max_seconds"]
        ),
        "minimum_editorial_overall_score": int(
            qa["minimum_overall_score"]
        ),
        "minimum_hook_strength_score": int(
            qa["minimum_hook_strength_score"]
        ),
        "minimum_hook_intro_distinctness_score": int(
            qa["minimum_hook_intro_distinctness_score"]
        ),
        "minimum_narrative_spine_score": int(
            qa["minimum_narrative_spine_score"]
        ),
        "minimum_specificity_score": int(
            qa["minimum_specificity_score"]
        ),
        "minimum_repetition_risk_score": int(
            qa["minimum_repetition_risk_score"]
        ),
        "minimum_title_thumbnail_synergy_score": int(
            qa["minimum_title_thumbnail_synergy_score"]
        ),
        "max_editorial_revision_attempts": int(
            qa["max_editorial_revision_attempts"]
        ),
        "require_channel_brand_intro": bool(
            brand_intro["required"]
        ),
        "channel_brand_name": str(
            brand_intro["brand_name"]
        ),
        "channel_brand_intro_scan_words": int(
            brand_intro["scan_word_limit"]
        ),
        "require_hiddenova_brand_intro": bool(
            profile["channel"] == "hiddenova"
            and brand_intro["required"]
        ),
        "require_standard_cta": bool(
            script["cta"]["required"]
        ),
        "factual_pipeline_required": bool(
            factuality["pipeline_required"]
        ),
        "require_web_research": bool(
            factuality["web_search_required"]
        ),
        "minimum_factual_sources": int(
            factuality["minimum_sources"]
        ),
        "minimum_primary_sources": int(
            factuality["minimum_primary_sources"]
        ),
        "minimum_sources_per_high_risk_claim": int(
            factuality[
                "minimum_sources_per_high_risk_claim"
            ]
        ),
        "max_factual_research_revision_attempts": int(
            factuality.get(
                "max_research_revision_attempts",
                0,
            )
        ),
        "require_claims_ledger": bool(
            factuality["require_claims_ledger"]
        ),
        "require_fact_qa": bool(
            factuality["require_fact_qa"]
        ),
        "require_risk_review": bool(
            factuality["require_risk_review"]
        ),
        "thumbnail_standard_name": str(
            thumbnail["standard_name"]
        ),
        **build_visual_quality_gates(profile),
    }


def apply_profile_quality_gates(
    context: dict[str, Any],
    profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    profile = profile or load_editorial_profile(
        context["channel"]
    )
    context.setdefault("quality_gates", {}).update(
        build_quality_gates(profile)
    )
    return context
