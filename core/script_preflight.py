from __future__ import annotations

import math
from typing import Any

from core.content_quality import (
    evaluate_script_word_count,
)


def evaluate_script_preflight(
    *,
    script_data: dict[str, Any],
    target_minimum: int,
    target_maximum: int,
    absolute_floor: int = 1100,
    minimum_ratio: float = 0.85,
    audio_duration_authoritative: bool = True,
) -> dict[str, Any]:
    target_minimum = int(target_minimum)
    target_maximum = int(target_maximum)
    absolute_floor = int(absolute_floor)
    minimum_ratio = float(minimum_ratio)

    if target_minimum < 1:
        raise ValueError("target_minimum must be at least 1.")

    if target_maximum <= target_minimum:
        raise ValueError(
            "target_maximum must be greater than target_minimum."
        )

    if absolute_floor < 1:
        raise ValueError("absolute_floor must be at least 1.")

    if not 0.0 < minimum_ratio <= 1.0:
        raise ValueError(
            "minimum_ratio must be greater than 0 and at most 1."
        )

    target_gate = evaluate_script_word_count(
        script_data=script_data,
        minimum=target_minimum,
        maximum=target_maximum,
    )
    word_count = int(target_gate["word_count"])
    provisional_floor = max(
        absolute_floor,
        math.ceil(target_minimum * minimum_ratio),
    )

    if target_gate["approved"]:
        status = "passed"
        accepted = True
        reason = "within_target_word_range"
        next_gate = "fact_risk_qa"
    elif (
        word_count < target_minimum
        and word_count >= provisional_floor
        and audio_duration_authoritative
    ):
        status = "provisional"
        accepted = True
        reason = "below_target_pending_actual_audio_duration"
        next_gate = "fact_risk_qa_then_audio_duration"
    elif word_count > target_maximum:
        status = "rejected"
        accepted = False
        reason = "above_target_maximum"
        next_gate = "script_revision"
    else:
        status = "rejected"
        accepted = False
        reason = "below_pre_audio_word_floor"
        next_gate = "script_revision"

    return {
        "status": status,
        "accepted": accepted,
        "word_count": word_count,
        "target_minimum": target_minimum,
        "target_maximum": target_maximum,
        "provisional_floor": provisional_floor,
        "minimum_ratio": minimum_ratio,
        "audio_duration_authoritative": bool(
            audio_duration_authoritative
        ),
        "reason": reason,
        "next_gate": next_gate,
        "target_gate": target_gate,
    }


def assert_script_preflight(
    *,
    script_data: dict[str, Any],
    target_minimum: int,
    target_maximum: int,
    absolute_floor: int = 1100,
    minimum_ratio: float = 0.85,
    audio_duration_authoritative: bool = True,
) -> dict[str, Any]:
    result = evaluate_script_preflight(
        script_data=script_data,
        target_minimum=target_minimum,
        target_maximum=target_maximum,
        absolute_floor=absolute_floor,
        minimum_ratio=minimum_ratio,
        audio_duration_authoritative=(
            audio_duration_authoritative
        ),
    )

    if not result["accepted"]:
        raise ValueError(
            "Script narration failed the pre-audio gate: "
            f"actual={result['word_count']} "
            f"target={result['target_minimum']}-"
            f"{result['target_maximum']} "
            f"provisional_floor={result['provisional_floor']} "
            f"reason={result['reason']}."
        )

    return result
