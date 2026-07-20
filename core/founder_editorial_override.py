from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


CHECK_NAMES = (
    "hook_strength",
    "hook_intro_distinctness",
    "narrative_spine",
    "specificity",
    "repetition_risk",
    "title_thumbnail_synergy",
    "standard_cta",
)


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None

    if isinstance(value, (int, float)):
        return int(value)

    if isinstance(value, str):
        normalized = value.strip()

        if not normalized:
            return None

        try:
            return int(float(normalized))
        except ValueError:
            return None

    return None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(
            lambda: handle.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def resolve_context_output(
    *,
    project_root: Path,
    context: dict[str, Any],
    key: str,
) -> Path | None:
    reference = context.get("outputs", {}).get(key)

    if not isinstance(reference, str) or not reference:
        return None

    root = project_root.resolve()
    path = (project_root / reference).resolve()

    try:
        path.relative_to(root)
    except ValueError:
        return None

    if not path.is_file():
        return None

    return path


def current_factual_snapshot(
    fact_risk_data: dict[str, Any],
) -> dict[str, Any]:
    unsupported = fact_risk_data.get(
        "unsupported_statements",
        [],
    )
    risk_issues = fact_risk_data.get(
        "risk_issues",
        [],
    )

    if not isinstance(unsupported, list):
        unsupported = []

    if not isinstance(risk_issues, list):
        risk_issues = []

    high_risk_count = sum(
        1
        for item in risk_issues
        if isinstance(item, dict)
        and item.get("severity") == "high"
    )

    return {
        "status": fact_risk_data.get("status"),
        "factual_grounding_score": _as_int(
            fact_risk_data.get(
                "factual_grounding_score"
            )
        ),
        "risk_compliance_score": _as_int(
            fact_risk_data.get(
                "risk_compliance_score"
            )
        ),
        "unsupported_statement_count": len(
            unsupported
        ),
        "high_risk_issue_count": high_risk_count,
    }


def current_editorial_scores(
    qa_data: dict[str, Any],
) -> dict[str, int | None]:
    checks = qa_data.get("checks", {})

    if not isinstance(checks, dict):
        checks = {}

    result: dict[str, int | None] = {
        "overall_score": _as_int(
            qa_data.get("overall_score")
        )
    }

    for name in CHECK_NAMES:
        item = checks.get(name, {})

        if not isinstance(item, dict):
            item = {}

        result[name] = _as_int(
            item.get("score")
        )

    return result


def load_json_file(path: Path) -> dict[str, Any]:
    return json.loads(
        path.read_text(encoding="utf-8-sig")
    )


def effective_content_approval(
    *,
    project_root: Path,
    context: dict[str, Any],
    qa_data: dict[str, Any],
    fact_risk_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if qa_data.get("status") == "approved":
        return {
            "approved": True,
            "source": "qa",
            "reason": "qa_approved",
        }

    if fact_risk_data is None:
        fact_path = resolve_context_output(
            project_root=project_root,
            context=context,
            key="fact_risk_qa",
        )

        if fact_path is None:
            return {
                "approved": False,
                "source": "none",
                "reason": "fact_risk_output_missing",
            }

        try:
            fact_risk_data = load_json_file(
                fact_path
            )
        except (OSError, ValueError):
            return {
                "approved": False,
                "source": "none",
                "reason": "fact_risk_output_invalid",
            }

    applies, reason = founder_editorial_override_matches(
        project_root=project_root,
        context=context,
        qa_data=qa_data,
        fact_risk_data=fact_risk_data,
    )

    return {
        "approved": applies,
        "source": (
            "founder_editorial_override"
            if applies
            else "none"
        ),
        "reason": reason,
    }


def founder_editorial_override_matches(
    *,
    project_root: Path,
    context: dict[str, Any],
    qa_data: dict[str, Any],
    fact_risk_data: dict[str, Any],
) -> tuple[bool, str]:
    gates = context.get("quality_gates", {})
    override = gates.get(
        "founder_editorial_override"
    )

    if not isinstance(override, dict):
        return False, "override_missing"

    if override.get("approved") is not True:
        return False, "override_not_approved"

    expected_scope = (
        f"{context.get('channel')}/"
        f"{context.get('video_id')}/"
        f"{context.get('run_id')}"
    )

    if override.get("scope") != expected_scope:
        return False, "scope_mismatch"

    if override.get("global_profile_changed") is not False:
        return False, "global_profile_mutation_detected"

    if override.get("override_version") != 2:
        return False, "override_version_invalid"

    factual = current_factual_snapshot(
        fact_risk_data
    )
    required_factual = {
        "status": "approved",
        "factual_grounding_score": 100,
        "risk_compliance_score": 100,
        "unsupported_statement_count": 0,
        "high_risk_issue_count": 0,
    }

    if factual != required_factual:
        return False, "factual_safety_mismatch"

    approved_factual = override.get(
        "factual_snapshot"
    )

    if not isinstance(approved_factual, dict):
        return False, "approved_factual_snapshot_missing"

    for key, expected in required_factual.items():
        if approved_factual.get(key) != expected:
            return False, "approved_factual_snapshot_mismatch"

    current_scores = current_editorial_scores(
        qa_data
    )
    approved_scores = override.get(
        "editorial_scores"
    )

    if not isinstance(approved_scores, dict):
        return False, "approved_editorial_scores_missing"

    for key, current_value in current_scores.items():
        if current_value is None:
            return False, f"current_editorial_score_missing:{key}"

        if _as_int(approved_scores.get(key)) != current_value:
            return False, f"editorial_score_mismatch:{key}"

    expected_hash_keys = {
        "script": "script_sha256",
        "qa": "qa_sha256",
        "fact_risk_qa": "fact_risk_sha256",
    }

    for output_key, hash_key in expected_hash_keys.items():
        path = resolve_context_output(
            project_root=project_root,
            context=context,
            key=output_key,
        )

        if path is None:
            return False, f"output_missing:{output_key}"

        approved_hash = override.get(hash_key)

        if (
            not isinstance(approved_hash, str)
            or len(approved_hash) != 64
        ):
            return False, f"approved_hash_missing:{output_key}"

        if sha256_file(path) != approved_hash:
            return False, f"output_hash_mismatch:{output_key}"

    best = gates.get("editorial_best_candidate")

    if not isinstance(best, dict):
        return False, "best_editorial_candidate_missing"

    if (
        _as_int(best.get("candidate_index"))
        != _as_int(
            override.get("approved_candidate_index")
        )
    ):
        return False, "candidate_index_mismatch"

    return True, "validated"
