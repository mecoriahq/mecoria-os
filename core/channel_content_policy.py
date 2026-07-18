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
