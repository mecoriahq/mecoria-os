from __future__ import annotations

from typing import Any


def build_word_count_revision_feedback(
    *,
    attempt: int,
    word_gate: dict[str, Any],
    previous_script: dict[str, Any],
    prior_revision_feedback: dict[str, Any] | None,
) -> dict[str, Any]:
    attempt = int(attempt)

    if attempt < 1:
        raise ValueError("attempt must be at least 1.")

    actual = int(word_gate["word_count"])
    minimum = int(word_gate["minimum"])
    maximum = int(word_gate["maximum"])

    if minimum <= actual <= maximum:
        raise ValueError(
            "Word-count revision feedback requires a failed gate."
        )

    if not isinstance(previous_script, dict):
        raise TypeError("previous_script must be a dictionary.")

    if actual < minimum:
        deficit = minimum - actual
        safe_change = deficit + 50
        direction = "expand"
        instructions = [
            (
                "Add at least "
                f"{safe_change} net narration words so the final "
                "script safely clears the minimum."
            ),
            (
                "Expand causal explanation, mechanisms, turning "
                "points, and consequences inside the main sections."
            ),
            (
                "Do not pad the hook, CTA, or repeat existing "
                "summaries merely to increase length."
            ),
        ]
    else:
        excess = actual - maximum
        safe_change = excess + 35
        direction = "compress"
        instructions = [
            (
                "Remove at least "
                f"{safe_change} narration words so the final script "
                "safely falls below the maximum."
            ),
            (
                "Cut repetition, generic transitions, and redundant "
                "summary language before removing factual detail."
            ),
        ]

    instructions.extend([
        (
            "Use only approved claim IDs already available in the "
            "claims ledger. Do not introduce new facts."
        ),
        (
            "Preserve attribution, chronology, the narrative spine, "
            "and every factual safeguard."
        ),
        (
            "Return the complete required JSON structure, not a "
            "partial patch or commentary."
        ),
    ])

    return {
        "attempt": attempt,
        "reason": "script_word_count_out_of_range",
        "direction": direction,
        "actual_word_count": actual,
        "minimum_word_count": minimum,
        "maximum_word_count": maximum,
        "target_net_change": safe_change,
        "instructions": instructions,
        "prior_editorial_revision_brief": (
            prior_revision_feedback
            if prior_revision_feedback
            else None
        ),
        "previous_script": previous_script,
    }
