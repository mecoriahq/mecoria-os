from __future__ import annotations

import re
from typing import Any


def _word_count(value: Any) -> int:
    if value is None:
        return 0

    if not isinstance(value, str):
        value = str(value)

    return len(
        re.findall(
            r"\b[\w'-]+\b",
            value,
            flags=re.UNICODE,
        )
    )


def _build_section_word_targets(
    previous_script: dict[str, Any],
    target_total: int,
) -> dict[str, Any]:
    main_sections = previous_script.get(
        "main_sections",
        [],
    )

    if not isinstance(main_sections, list):
        main_sections = []

    main_count = max(1, len(main_sections))

    fixed_targets = {
        "hook": 90,
        "introduction": 120,
        "conclusion": 100,
        "call_to_action": 35,
    }
    main_total = max(
        120 * main_count,
        target_total - sum(fixed_targets.values()),
    )
    main_target = max(
        120,
        round(main_total / main_count),
    )

    section_targets = {
        "hook": {
            "minimum": 80,
            "target": fixed_targets["hook"],
            "maximum": 105,
        },
        "introduction": {
            "minimum": 105,
            "target": fixed_targets["introduction"],
            "maximum": 135,
        },
        "main_sections": [
            {
                "index": index,
                "minimum": max(120, main_target - 15),
                "target": main_target,
                "maximum": main_target + 20,
            }
            for index in range(main_count)
        ],
        "conclusion": {
            "minimum": 90,
            "target": fixed_targets["conclusion"],
            "maximum": 115,
        },
        "call_to_action": {
            "minimum": 25,
            "target": fixed_targets["call_to_action"],
            "maximum": 45,
        },
    }

    previous_counts = {
        "hook": _word_count(
            previous_script.get("hook", {}).get(
                "narration",
                "",
            )
            if isinstance(
                previous_script.get("hook"),
                dict,
            )
            else previous_script.get("hook", "")
        ),
        "introduction": _word_count(
            previous_script.get(
                "introduction",
                {},
            ).get("narration", "")
            if isinstance(
                previous_script.get("introduction"),
                dict,
            )
            else previous_script.get(
                "introduction",
                "",
            )
        ),
        "main_sections": [
            _word_count(
                section.get("narration", "")
                if isinstance(section, dict)
                else section
            )
            for section in main_sections
        ],
        "conclusion": _word_count(
            previous_script.get(
                "conclusion",
                {},
            ).get("narration", "")
            if isinstance(
                previous_script.get("conclusion"),
                dict,
            )
            else previous_script.get(
                "conclusion",
                "",
            )
        ),
        "call_to_action": _word_count(
            previous_script.get(
                "call_to_action",
                {},
            ).get("narration", "")
            if isinstance(
                previous_script.get("call_to_action"),
                dict,
            )
            else previous_script.get(
                "call_to_action",
                "",
            )
        ),
    }

    return {
        "targets": section_targets,
        "previous_counts": previous_counts,
    }


def _extract_editorial_constraints(
    prior_revision_feedback: dict[str, Any] | None,
) -> dict[str, Any]:
    if not prior_revision_feedback:
        return {
            "issue_count": 0,
            "flagged_statements": [],
            "required_edits": [],
        }

    issues = prior_revision_feedback.get("issues", [])

    if not isinstance(issues, list):
        issues = []

    flagged_statements: list[str] = []
    required_edits: list[str] = []

    for item in issues:
        if not isinstance(item, dict):
            continue

        statement = (
            item.get("statement")
            or item.get("message")
        )
        required_edit = (
            item.get("suggested_action")
            or item.get("required_edit")
        )

        if statement:
            flagged_statements.append(
                str(statement).strip()
            )

        if required_edit:
            required_edits.append(
                str(required_edit).strip()
            )

    return {
        "issue_count": len(issues),
        "flagged_statements": list(
            dict.fromkeys(flagged_statements)
        ),
        "required_edits": list(
            dict.fromkeys(required_edits)
        ),
    }


def build_word_count_revision_feedback(
    *,
    attempt: int,
    word_gate: dict[str, Any],
    previous_script: dict[str, Any],
    prior_revision_feedback: dict[str, Any] | None,
    approved_claim_ids: list[str] | None = None,
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

    target_total = round((minimum + maximum) / 2)
    target_total = max(
        minimum + 75,
        min(maximum - 75, target_total),
    )
    target_band = {
        "minimum": max(minimum, target_total - 30),
        "maximum": min(maximum, target_total + 30),
    }

    if actual < minimum:
        direction = "expand"
        target_net_change = target_total - actual
        instructions = [
            (
                "Regenerate the complete script to land inside the "
                f"target band of {target_band['minimum']} to "
                f"{target_band['maximum']} narration words."
            ),
            (
                "Expand only with details, chronology, attribution, "
                "comparisons, and consequences explicitly contained "
                "in approved claims."
            ),
            (
                "Add depth mainly inside the main sections. Do not "
                "pad the hook, conclusion, or CTA."
            ),
        ]
    else:
        direction = "compress"
        target_net_change = actual - target_total
        instructions = [
            (
                "Regenerate the complete script to land inside the "
                f"target band of {target_band['minimum']} to "
                f"{target_band['maximum']} narration words."
            ),
            (
                "Cut repetition, generic transitions, dramatic "
                "interpretation, and redundant summaries before "
                "removing approved factual detail."
            ),
        ]

    editorial_constraints = (
        _extract_editorial_constraints(
            prior_revision_feedback
        )
    )
    section_word_targets = (
        _build_section_word_targets(
            previous_script=previous_script,
            target_total=target_total,
        )
    )

    instructions.extend([
        (
            "Every correction in the prior Fact/Risk QA brief "
            "remains mandatory. Never reintroduce the flagged "
            "statement or an equivalent unsupported implication."
        ),
        (
            "Do not add general medical, legal, scientific, or "
            "business background unless it exists in an approved "
            "claim."
        ),
        (
            "Do not invent motive, causation, secrecy, collapse, "
            "credibility effects, public psychology, or negative "
            "legal conclusions."
        ),
        (
            "Use only approved claim IDs already available in the "
            "claims ledger. Do not introduce new facts."
        ),
        (
            "Every factual sentence must remain within the wording, "
            "certainty, attribution, and scope of the claim IDs "
            "attached to that narration block."
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
        "target_word_count": target_total,
        "target_word_band": target_band,
        "target_net_change": target_net_change,
        "section_word_targets": section_word_targets,
        "approved_claim_ids": list(
            dict.fromkeys(
                str(item).strip()
                for item in (
                    approved_claim_ids or []
                )
                if str(item).strip()
            )
        ),
        "must_preserve_editorial_corrections": True,
        "editorial_constraints": editorial_constraints,
        "instructions": instructions,
        "prior_editorial_revision_brief": (
            prior_revision_feedback
            if prior_revision_feedback
            else None
        ),
        "previous_script": previous_script,
    }
