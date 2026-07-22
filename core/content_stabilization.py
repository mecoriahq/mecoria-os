from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.content_quality import (
    count_script_narration_words,
)
from core.factual_repair import (
    MAX_DETERMINISTIC_REPAIR_PASSES,
    build_deterministic_factual_repair_plan,
)


STABILIZATION_VERSION = "content_stabilization_v1"


class ContentStabilizationError(RuntimeError):
    """Base error for controlled content stabilization failures."""


class ContentStabilizationBudgetExceeded(
    ContentStabilizationError
):
    """Raised when a bounded stabilization budget is exhausted."""


class ContentStabilizationLoopDetected(
    ContentStabilizationError
):
    """Raised when the same content decision repeats unchanged."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_digest(value: Any) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def reliability_config(
    profile: dict[str, Any],
) -> dict[str, Any]:
    raw = profile.get("reliability", {})

    if not isinstance(raw, dict):
        raw = {}

    sentences = raw.get(
        "safe_word_budget_sentences",
        [],
    )

    if not isinstance(sentences, list):
        sentences = []

    normalized_sentences = [
        str(item).strip()
        for item in sentences
        if str(item).strip()
    ]

    return {
        "max_content_stabilization_steps": int(
            raw.get(
                "max_content_stabilization_steps",
                12,
            )
        ),
        "max_same_signature_attempts": int(
            raw.get(
                "max_same_signature_attempts",
                2,
            )
        ),
        "max_deterministic_factual_repair_attempts": int(
            raw.get(
                "max_deterministic_factual_repair_attempts",
                MAX_DETERMINISTIC_REPAIR_PASSES,
            )
        ),
        "max_safe_word_top_up": int(
            raw.get("max_safe_word_top_up", 20)
        ),
        "safe_word_budget_sentences": (
            normalized_sentences
        ),
    }


def ensure_stabilization_state(
    context: dict[str, Any],
    profile: dict[str, Any],
) -> dict[str, Any]:
    gates = context.setdefault("quality_gates", {})
    state = gates.get("content_stabilization")

    if not isinstance(state, dict):
        state = {}
        gates["content_stabilization"] = state

    config = reliability_config(profile)
    state.setdefault("version", STABILIZATION_VERSION)
    state.setdefault("status", "active")
    state.setdefault("total_steps", 0)
    state.setdefault("phase_attempts", {})
    state.setdefault("action_signatures", {})
    state.setdefault(
        "max_steps",
        config["max_content_stabilization_steps"],
    )
    state.setdefault(
        "max_same_signature_attempts",
        config["max_same_signature_attempts"],
    )
    state.setdefault("history", [])
    return state


def enter_stabilization_step(
    *,
    context: dict[str, Any],
    profile: dict[str, Any],
    phase: str,
) -> dict[str, Any]:
    state = ensure_stabilization_state(
        context,
        profile,
    )
    next_step = int(state.get("total_steps", 0)) + 1
    maximum = int(state.get("max_steps", 12))

    if next_step > maximum:
        state["status"] = "budget_exhausted"
        state["terminal_reason"] = (
            "content_stabilization_budget_exhausted"
        )
        state["updated_at"] = utc_now()
        raise ContentStabilizationBudgetExceeded(
            "Content stabilization exceeded its finite "
            f"budget of {maximum} steps."
        )

    state["total_steps"] = next_step
    phase_attempts = state.setdefault(
        "phase_attempts",
        {},
    )
    phase_attempts[phase] = (
        int(phase_attempts.get(phase, 0)) + 1
    )
    state["current_phase"] = phase
    state["updated_at"] = utc_now()
    state.setdefault("history", []).append({
        "step": next_step,
        "phase": phase,
        "event": "entered",
        "recorded_at": utc_now(),
    })
    return state


def record_stabilization_action(
    *,
    context: dict[str, Any],
    profile: dict[str, Any],
    phase: str,
    action: str,
    payload: Any,
) -> dict[str, Any]:
    state = ensure_stabilization_state(
        context,
        profile,
    )
    signature = canonical_digest({
        "phase": phase,
        "action": action,
        "payload": payload,
    })
    signatures = state.setdefault(
        "action_signatures",
        {},
    )
    count = int(signatures.get(signature, 0)) + 1
    signatures[signature] = count
    maximum = int(
        state.get("max_same_signature_attempts", 2)
    )

    state["last_action"] = action
    state["last_signature"] = signature
    state["last_signature_count"] = count
    state["updated_at"] = utc_now()
    state.setdefault("history", []).append({
        "step": int(state.get("total_steps", 0)),
        "phase": phase,
        "event": action,
        "signature": signature,
        "signature_count": count,
        "recorded_at": utc_now(),
    })

    if count > maximum:
        state["status"] = "loop_detected"
        state["terminal_reason"] = (
            "content_stabilization_loop_detected"
        )
        raise ContentStabilizationLoopDetected(
            "The same content stabilization action repeated "
            f"{count} times without changing its inputs."
        )

    return {
        "signature": signature,
        "count": count,
        "maximum": maximum,
    }


def mark_stabilization_complete(
    context: dict[str, Any],
    profile: dict[str, Any],
) -> None:
    state = ensure_stabilization_state(
        context,
        profile,
    )
    state["status"] = "approved"
    state["current_phase"] = "complete"
    state["completed_at"] = utc_now()
    state["updated_at"] = utc_now()


def factual_snapshot(
    fact_data: dict[str, Any],
) -> dict[str, Any]:
    unsupported = fact_data.get(
        "unsupported_statements",
        [],
    )
    risks = fact_data.get("risk_issues", [])

    if not isinstance(unsupported, list):
        unsupported = []

    if not isinstance(risks, list):
        risks = []

    high_risk_count = sum(
        1
        for item in risks
        if isinstance(item, dict)
        and str(item.get("severity", "")).lower()
        == "high"
    )
    factual_score = int(
        fact_data.get("factual_grounding_score", 0)
    )
    risk_score = int(
        fact_data.get("risk_compliance_score", 0)
    )
    status = str(fact_data.get("status", ""))

    return {
        "status": status,
        "factual_grounding_score": factual_score,
        "risk_compliance_score": risk_score,
        "unsupported_statement_count": len(unsupported),
        "high_risk_issue_count": high_risk_count,
        "approved": (
            status == "approved"
            and factual_score == 100
            and risk_score == 100
            and len(unsupported) == 0
            and high_risk_count == 0
        ),
    }


def word_budget_report(
    *,
    script_data: dict[str, Any],
    profile: dict[str, Any],
) -> dict[str, Any]:
    script_policy = profile.get("script", {})
    minimum = int(script_policy["word_count_min"])
    maximum = int(script_policy["word_count_max"])
    current = count_script_narration_words(
        script_data
    )
    gap = max(0, minimum - current)
    config = reliability_config(profile)
    cta_policy = script_policy.get("cta", {})
    cta = (
        script_data.get("script", {})
        .get("call_to_action", {})
    )
    cta_narration = str(
        cta.get("narration", "")
    ).strip()
    cta_words = len(cta_narration.split())
    cta_max = int(cta_policy.get(
        "word_count_max",
        55,
    ))
    cta_capacity = max(0, cta_max - cta_words)

    return {
        "current_word_count": current,
        "minimum_word_count": minimum,
        "maximum_word_count": maximum,
        "missing_word_count": gap,
        "max_safe_word_top_up": (
            config["max_safe_word_top_up"]
        ),
        "cta_word_count": cta_words,
        "cta_word_capacity": cta_capacity,
        "recoverable": (
            gap > 0
            and gap
            <= config["max_safe_word_top_up"]
            and gap <= cta_capacity
            and bool(
                config["safe_word_budget_sentences"]
            )
        ),
    }


def apply_safe_word_budget_recovery(
    *,
    script_data: dict[str, Any],
    profile: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    report = word_budget_report(
        script_data=script_data,
        profile=profile,
    )

    if report["missing_word_count"] == 0:
        return copy.deepcopy(script_data), {
            **report,
            "applied": False,
            "reason": "word_budget_already_satisfied",
            "added_sentences": [],
        }

    if not report["recoverable"]:
        return copy.deepcopy(script_data), {
            **report,
            "applied": False,
            "reason": "word_budget_not_safely_recoverable",
            "added_sentences": [],
        }

    revised = copy.deepcopy(script_data)
    cta = (
        revised.setdefault("script", {})
        .setdefault("call_to_action", {})
    )
    narration = str(
        cta.get("narration", "")
    ).strip()
    sentences = reliability_config(profile)[
        "safe_word_budget_sentences"
    ]
    added: list[str] = []

    for sentence in sentences:
        if sentence in narration:
            continue

        candidate = (
            f"{narration} {sentence}".strip()
        )
        candidate_words = len(candidate.split())

        if (
            candidate_words
            > report["cta_word_count"]
            + report["cta_word_capacity"]
        ):
            continue

        narration = candidate
        added.append(sentence)
        cta["narration"] = narration

        if (
            count_script_narration_words(revised)
            >= report["minimum_word_count"]
        ):
            break

    final_count = count_script_narration_words(
        revised
    )

    if final_count < report["minimum_word_count"]:
        return copy.deepcopy(script_data), {
            **report,
            "applied": False,
            "reason": "safe_sentences_insufficient",
            "added_sentences": [],
            "revised_word_count": final_count,
        }

    metadata = {
        **report,
        "applied": True,
        "reason": "safe_cta_word_budget_recovery",
        "added_sentences": added,
        "revised_word_count": final_count,
        "added_word_count": (
            final_count - report["current_word_count"]
        ),
        "recovered_at": utc_now(),
        "version": STABILIZATION_VERSION,
    }
    revised.setdefault("quality", {})[
        "automatic_word_budget_recovery"
    ] = metadata
    return revised, metadata


def resolve_context_output(
    *,
    project_root: Path,
    context: dict[str, Any],
    key: str,
) -> Path | None:
    reference = context.get("outputs", {}).get(key)

    if not isinstance(reference, str) or not reference:
        return None

    path = (project_root / reference).resolve()

    try:
        path.relative_to(project_root.resolve())
    except ValueError:
        return None

    return path if path.is_file() else None


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(
        path.read_text(encoding="utf-8-sig")
    )


def automatic_checkpoint_recovery_available(
    *,
    project_root: Path,
    context: dict[str, Any],
    profile: dict[str, Any],
) -> dict[str, Any]:
    status = str(context.get("status") or "")

    if status not in {
        "founder_editorial_review_required",
        "founder_factual_review_required",
    }:
        return {
            "available": False,
            "reason": "not_recoverable_checkpoint",
        }

    script_path = resolve_context_output(
        project_root=project_root,
        context=context,
        key="script",
    )
    fact_path = resolve_context_output(
        project_root=project_root,
        context=context,
        key="fact_risk_qa",
    )

    if script_path is None or fact_path is None:
        return {
            "available": False,
            "reason": "required_output_missing",
        }

    script_data = load_json(script_path)
    fact_data = load_json(fact_path)

    if status == "founder_factual_review_required":
        plan = build_deterministic_factual_repair_plan(
            script_data=script_data,
            qa_data=fact_data,
        )
        repair_count = int(
            context.get("quality_gates", {}).get(
                "deterministic_factual_repair_count",
                0,
            )
        )
        repair_limit = int(
            reliability_config(profile)[
                "max_deterministic_factual_repair_attempts"
            ]
        )
        available = bool(
            plan["available"]
            and repair_count < repair_limit
        )

        return {
            "available": available,
            "reason": (
                "deterministic_factual_repair"
                if available
                else (
                    "deterministic_factual_repair_budget_exhausted"
                    if plan["available"]
                    else "manual_founder_review_required"
                )
            ),
            "factual_repair": plan,
            "deterministic_repair_count": repair_count,
            "deterministic_repair_limit": repair_limit,
        }

    factual = factual_snapshot(fact_data)
    word_report = word_budget_report(
        script_data=script_data,
        profile=profile,
    )
    available = bool(
        factual["approved"]
        and word_report["recoverable"]
    )

    return {
        "available": available,
        "reason": (
            "safe_word_budget_recovery"
            if available
            else "manual_founder_review_required"
        ),
        "factual": factual,
        "word_budget": word_report,
    }
