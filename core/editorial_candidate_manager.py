from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def factual_metrics(
    fact_risk_data: dict[str, Any],
) -> dict[str, Any]:
    risk_issues = [
        item
        for item in fact_risk_data.get("risk_issues", [])
        if isinstance(item, dict)
    ]
    high_risk = sum(
        1 for item in risk_issues if item.get("severity") == "high"
    )
    unsupported = len(
        fact_risk_data.get("unsupported_statements", [])
    )
    factual_score = int(
        fact_risk_data.get("factual_grounding_score", 0)
    )
    risk_score = int(
        fact_risk_data.get("risk_compliance_score", 0)
    )
    approved = (
        fact_risk_data.get("status") == "approved"
        and factual_score == 100
        and risk_score == 100
        and unsupported == 0
        and high_risk == 0
    )
    return {
        "approved": approved,
        "unsupported_statement_count": unsupported,
        "high_risk_issue_count": high_risk,
        "factual_grounding_score": factual_score,
        "risk_compliance_score": risk_score,
    }


def editorial_metrics(
    *,
    qa_data: dict[str, Any],
    gate_result: dict[str, Any],
    fact_risk_data: dict[str, Any],
) -> dict[str, Any]:
    fact = factual_metrics(fact_risk_data)
    failures = [
        item
        for item in gate_result.get("failures", [])
        if isinstance(item, dict)
    ]
    deficit = sum(
        max(
            0,
            int(item.get("minimum", 0))
            - int(item.get("score", 0)),
        )
        for item in failures
    )
    overall = int(qa_data.get("overall_score", 0))
    editorial_approved = bool(gate_result.get("approved"))
    rank = (
        0 if fact["approved"] else 1,
        0 if editorial_approved else 1,
        len(failures),
        deficit,
        100 - overall,
    )
    return {
        **fact,
        "editorial_approved": editorial_approved,
        "editorial_overall_score": overall,
        "editorial_failure_count": len(failures),
        "editorial_deficit": deficit,
        "rank": list(rank),
    }


def candidate_is_better(
    candidate: dict[str, Any],
    incumbent: dict[str, Any] | None,
) -> bool:
    if incumbent is None:
        return True
    return tuple(candidate["rank"]) < tuple(incumbent["rank"])


def _relative(project_root: Path, path: Path) -> str:
    return str(path.relative_to(project_root)).replace("\\", "/")


def archive_editorial_candidate(
    *,
    project_root: Path,
    context: dict[str, Any],
    script_data: dict[str, Any],
    seo_data: dict[str, Any],
    qa_data: dict[str, Any],
    fact_risk_data: dict[str, Any],
    gate_result: dict[str, Any],
) -> dict[str, Any]:
    gates = context.setdefault("quality_gates", {})
    candidate_index = int(
        gates.get("editorial_candidate_count", 0)
    ) + 1
    candidate_dir = (
        project_root
        / "records"
        / "run_contexts"
        / context["channel"]
        / context["video_id"]
        / "editorial_candidates"
        / f"candidate_{candidate_index:02d}"
    )
    candidate_dir.mkdir(parents=True, exist_ok=True)

    records = {
        "script": script_data,
        "seo": seo_data,
        "qa": qa_data,
        "fact_risk_qa": fact_risk_data,
    }
    references: dict[str, str] = {}

    for name, data in records.items():
        path = candidate_dir / f"{name}.json"
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )
        references[f"{name}_reference"] = _relative(project_root, path)

    metrics = editorial_metrics(
        qa_data=qa_data,
        gate_result=gate_result,
        fact_risk_data=fact_risk_data,
    )
    record = {
        "candidate_index": candidate_index,
        **references,
        "metrics": metrics,
    }
    metadata_path = candidate_dir / "metadata.json"
    metadata_path.write_text(
        json.dumps(record, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )

    incumbent = gates.get("editorial_best_candidate")
    incumbent_metrics = (
        incumbent.get("metrics")
        if isinstance(incumbent, dict)
        else None
    )
    accepted = candidate_is_better(metrics, incumbent_metrics)

    if accepted:
        gates["editorial_best_candidate"] = record

    gates["editorial_candidate_count"] = candidate_index
    return {
        "record": record,
        "accepted_as_best": accepted,
        "best_candidate": gates.get("editorial_best_candidate"),
    }


def load_json_reference(
    project_root: Path,
    reference: str,
) -> dict[str, Any]:
    path = project_root / reference
    if not path.exists():
        raise FileNotFoundError(f"Candidate record not found: {path}")
    return json.loads(path.read_text(encoding="utf-8-sig"))


def restore_editorial_candidate(
    *,
    project_root: Path,
    candidate: dict[str, Any],
    canonical_script_path: Path,
    canonical_seo_path: Path | None = None,
) -> dict[str, Any]:
    script_data = load_json_reference(
        project_root,
        candidate["script_reference"],
    )
    canonical_script_path.parent.mkdir(parents=True, exist_ok=True)
    canonical_script_path.write_text(
        json.dumps(script_data, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )

    if canonical_seo_path is not None:
        seo_data = load_json_reference(
            project_root,
            candidate["seo_reference"],
        )
        canonical_seo_path.parent.mkdir(parents=True, exist_ok=True)
        canonical_seo_path.write_text(
            json.dumps(seo_data, indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )

    return script_data
