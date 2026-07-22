from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.content_stabilization import (
    factual_snapshot,
)


FOUNDER_OVERRIDE_VERSION = 2


class FounderActionError(RuntimeError):
    """Raised when a founder action is unsafe or invalid."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(
        path.read_text(encoding="utf-8-sig")
    )


def save_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(
            payload,
            indent=2,
            ensure_ascii=True,
        )
        + "\n",
        encoding="utf-8",
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(
            lambda: handle.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def resolve_output(
    *,
    project_root: Path,
    context: dict[str, Any],
    key: str,
) -> Path:
    reference = context.get("outputs", {}).get(key)

    if not isinstance(reference, str) or not reference:
        raise FounderActionError(
            f"Required output is missing: {key}"
        )

    path = (project_root / reference).resolve()

    try:
        path.relative_to(project_root.resolve())
    except ValueError as exc:
        raise FounderActionError(
            f"Output escapes repository root: {key}"
        ) from exc

    if not path.is_file():
        raise FounderActionError(
            f"Required output file is missing: {reference}"
        )

    return path


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None

    if isinstance(value, (int, float)):
        return int(value)

    if isinstance(value, str):
        try:
            return int(float(value.strip()))
        except (TypeError, ValueError):
            return None

    return None


def editorial_scores(
    qa_data: dict[str, Any],
) -> dict[str, int]:
    checks = qa_data.get("checks", {})

    if not isinstance(checks, dict):
        checks = {}

    names = (
        "hook_strength",
        "hook_intro_distinctness",
        "narrative_spine",
        "specificity",
        "repetition_risk",
        "title_thumbnail_synergy",
        "standard_cta",
    )
    scores = {
        "overall_score": int(
            _as_int(qa_data.get("overall_score")) or 0
        )
    }

    for name in names:
        item = checks.get(name, {})

        if not isinstance(item, dict):
            item = {}

        scores[name] = int(
            _as_int(item.get("score")) or 0
        )

    return scores


def append_history(
    context: dict[str, Any],
    *,
    agent: str,
    status: str,
    reference: str,
) -> None:
    context.setdefault("history", []).append({
        "agent": agent,
        "status": status,
        "recorded_at": utc_now(),
        "output_reference": reference,
    })


def approve_editorial_context(
    *,
    project_root: Path,
    context: dict[str, Any],
    reason: str,
) -> dict[str, Any]:
    gates = context.setdefault("quality_gates", {})
    existing = gates.get("founder_editorial_override")

    if (
        isinstance(existing, dict)
        and existing.get("approved") is True
        and existing.get("scope")
        == (
            f"{context.get('channel')}/"
            f"{context.get('video_id')}/"
            f"{context.get('run_id')}"
        )
    ):
        return {
            "context": context,
            "already_approved": True,
            "override": existing,
        }

    if (
        context.get("status")
        != "founder_editorial_review_required"
    ):
        raise FounderActionError(
            "This video is not waiting for editorial approval."
        )

    script_path = resolve_output(
        project_root=project_root,
        context=context,
        key="script",
    )
    qa_path = resolve_output(
        project_root=project_root,
        context=context,
        key="qa",
    )
    fact_path = resolve_output(
        project_root=project_root,
        context=context,
        key="fact_risk_qa",
    )
    qa_data = load_json(qa_path)
    fact_data = load_json(fact_path)
    factual = factual_snapshot(fact_data)

    if factual.get("approved") is not True:
        raise FounderActionError(
            "Editorial approval is blocked because Fact/Risk QA "
            "is not fully approved."
        )

    best = gates.get("editorial_best_candidate")

    if not isinstance(best, dict):
        raise FounderActionError(
            "Editorial candidate record is missing."
        )

    candidate_index = _as_int(
        best.get("candidate_index")
    )

    if candidate_index is None:
        raise FounderActionError(
            "Editorial candidate index is invalid."
        )

    approved_at = utc_now()
    scope = (
        f"{context['channel']}/"
        f"{context['video_id']}/"
        f"{context['run_id']}"
    )
    override = {
        "override_version": FOUNDER_OVERRIDE_VERSION,
        "approved": True,
        "approved_at": approved_at,
        "approved_by": "founder",
        "scope": scope,
        "reason": reason.strip(),
        "global_profile_changed": False,
        "approved_candidate_index": candidate_index,
        "script_reference": context["outputs"]["script"],
        "qa_reference": context["outputs"]["qa"],
        "fact_risk_reference": (
            context["outputs"]["fact_risk_qa"]
        ),
        "script_sha256": sha256_file(script_path),
        "qa_sha256": sha256_file(qa_path),
        "fact_risk_sha256": sha256_file(fact_path),
        "factual_snapshot": {
            key: factual[key]
            for key in (
                "status",
                "factual_grounding_score",
                "risk_compliance_score",
                "unsupported_statement_count",
                "high_risk_issue_count",
            )
        },
        "editorial_scores": editorial_scores(qa_data),
        "original_thresholds": {
            key: gates.get(key)
            for key in (
                "minimum_editorial_overall_score",
                "minimum_hook_strength_score",
                "minimum_hook_intro_distinctness_score",
                "minimum_narrative_spine_score",
                "minimum_specificity_score",
                "minimum_repetition_risk_score",
                "minimum_title_thumbnail_synergy_score",
            )
        },
        "consumed": False,
    }
    gates["founder_editorial_override"] = override
    append_history(
        context,
        agent="founder_editorial_review",
        status="approved_override",
        reference=(
            f"scope={scope};"
            f"candidate={candidate_index};"
            "factual=100;risk=100"
        ),
    )
    context["status"] = "fact_risk_qa_ready"
    context["next_agent"] = "qa"
    context["updated_at"] = approved_at
    return {
        "context": context,
        "already_approved": False,
        "override": override,
    }


def approve_video_context(
    *,
    context: dict[str, Any],
    reason: str,
) -> dict[str, Any]:
    release = context.setdefault("release", {})

    if release.get("founder_video_review_approved") is True:
        return {
            "context": context,
            "already_approved": True,
        }

    if context.get("status") not in {
        "founder_review_required",
        "uploaded_for_founder_review",
    }:
        raise FounderActionError(
            "This video is not waiting for final video approval."
        )

    approved_at = utc_now()
    release["founder_video_review_approved"] = True
    release["founder_video_review_approved_at"] = approved_at
    release["founder_video_review_approved_by"] = "founder"
    release["founder_video_review_reason"] = reason.strip()
    append_history(
        context,
        agent="founder_video_review",
        status="approved_for_upload",
        reference=reason.strip(),
    )

    if context.get("status") == "founder_review_required":
        context["status"] = "video_approved_for_upload"
        context["next_agent"] = "youtube_upload_manual"

    context["updated_at"] = approved_at
    return {
        "context": context,
        "already_approved": False,
    }
