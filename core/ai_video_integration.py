import json
import os
from pathlib import Path
from typing import Mapping

from core.ai_video_standard import validate_insert_count


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = (
    PROJECT_ROOT
    / "config"
    / "media"
    / "ai_video_production.json"
)
AI_VIDEO_INTEGRATION_VERSION = "1.0"


def load_ai_video_production_config(
    path: Path = DEFAULT_CONFIG_PATH
) -> dict:
    if not path.exists():
        raise FileNotFoundError(
            f"AI video production config not found: {path}"
        )

    config = json.loads(
        path.read_text(encoding="utf-8-sig")
    )
    validate_ai_video_production_config(config)
    return config


def validate_ai_video_production_config(
    config: dict
) -> None:
    required = {
        "version",
        "orchestrator_enabled",
        "live_generation_enabled",
        "provider",
        "model",
        "insert_count",
        "require_environment_confirmation",
        "environment_confirmation_key",
        "environment_confirmation_value",
        "quality_gates",
    }
    missing = sorted(required - set(config))

    if missing:
        raise ValueError(
            "AI video production config is missing fields: "
            + ", ".join(missing)
        )

    if not isinstance(config["orchestrator_enabled"], bool):
        raise TypeError("orchestrator_enabled must be boolean.")

    if not isinstance(config["live_generation_enabled"], bool):
        raise TypeError("live_generation_enabled must be boolean.")

    validate_insert_count(config["insert_count"])

    gates = config["quality_gates"]

    if not isinstance(gates, dict):
        raise TypeError("quality_gates must be an object.")

    minimum_video_count = int(
        gates.get("minimum_ai_video_insert_count", 0)
    )
    maximum_video_count = int(
        gates.get("maximum_ai_video_insert_count", 0)
    )

    validate_insert_count(minimum_video_count)
    validate_insert_count(maximum_video_count)

    if minimum_video_count > maximum_video_count:
        raise ValueError(
            "minimum_ai_video_insert_count cannot exceed "
            "maximum_ai_video_insert_count."
        )


def environment_confirmation_matches(
    config: dict,
    environ: Mapping[str, str] | None = None
) -> bool:
    if not config.get(
        "require_environment_confirmation",
        True
    ):
        return True

    environ = environ if environ is not None else os.environ
    key = str(config["environment_confirmation_key"])
    expected = str(
        config["environment_confirmation_value"]
    ).strip().lower()
    actual = str(environ.get(key, "")).strip().lower()
    return actual == expected


def assert_live_generation_allowed(
    config: dict,
    confirmed: bool,
    environ: Mapping[str, str] | None = None
) -> None:
    validate_ai_video_production_config(config)

    if not config["orchestrator_enabled"]:
        raise ValueError(
            "AI video production orchestrator is disabled."
        )

    if not config["live_generation_enabled"]:
        raise ValueError(
            "Live AI video generation is disabled."
        )

    if not confirmed:
        raise ValueError(
            "Live AI video cost confirmation is required."
        )

    if not environment_confirmation_matches(
        config=config,
        environ=environ
    ):
        raise ValueError(
            "AI video live environment confirmation is missing."
        )


def ai_video_context_enabled(context: dict | None) -> bool:
    if not context:
        return False

    return (
        context.get("quality_gates", {}).get(
            "ai_video_inserts_enabled"
        )
        is True
    )


def apply_visual_diversity_gates(
    context: dict,
    config: dict
) -> dict:
    gates = context.setdefault("quality_gates", {})
    configured_gates = config.get("quality_gates", {})

    for key in (
        "minimum_ai_insert_count",
        "minimum_ai_video_insert_count",
        "maximum_ai_video_insert_count",
        "minimum_stock_clip_count",
        "maximum_single_stock_clip_share",
        "minimum_timeline_cycle_coverage",
        "maximum_timeline_cycles",
        "maximum_stock_segments_per_clip",
    ):
        if key in configured_gates:
            gates[key] = configured_gates[key]

    gates.update({
        "visual_diversity_standard_version": (
            "hiddenova_visual_diversity_v2"
        ),
        "allow_cross_video_ai_video_reuse": False,
        "require_ai_video_asset_registry_ownership": True,
    })
    return context


def mark_ai_video_context_ready(
    context: dict,
    config: dict
) -> dict:
    context = apply_visual_diversity_gates(
        context=context,
        config=config
    )
    gates = context.setdefault("quality_gates", {})
    gates.update({
        "ai_video_inserts_enabled": True,
        "require_ai_video_inserts": True,
        "ai_video_integration_version": (
            AI_VIDEO_INTEGRATION_VERSION
        ),
        "ai_video_provider": config["provider"],
        "ai_video_model": config["model"],
    })
    return context


def interleave_ai_specs(
    image_specs: list[dict],
    video_specs: list[dict]
) -> list[dict]:
    if not video_specs:
        return list(image_specs)

    if not image_specs:
        return list(video_specs)

    combined = []
    maximum = max(len(image_specs), len(video_specs))

    for index in range(maximum):
        if index < len(image_specs):
            combined.append(image_specs[index])

        if index < len(video_specs):
            combined.append(video_specs[index])

    return combined
