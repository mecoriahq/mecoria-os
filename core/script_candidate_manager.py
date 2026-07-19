from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any


SUPPORTED_LOCATION_PATTERN = re.compile(
    r"^(?:hook|introduction|conclusion|call_to_action)\.narration$"
    r"|^main_sections\[(\d+)\]\.narration$"
)


def normalize_repair_location(value: Any) -> str | None:
    if value is None:
        return None

    location = str(value).split(" / ", 1)[0].strip()

    if not SUPPORTED_LOCATION_PATTERN.fullmatch(location):
        return None

    return location


def extract_repair_targets(
    qa_data: dict[str, Any],
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}

    for item in (
        list(qa_data.get("unsupported_statements", []))
        + list(qa_data.get("risk_issues", []))
    ):
        if not isinstance(item, dict):
            continue

        location = normalize_repair_location(
            item.get("location")
        )

        if not location:
            continue

        grouped.setdefault(location, []).append(
            copy.deepcopy(item)
        )

    return [
        {
            "location": location,
            "issues": grouped[location],
        }
        for location in sorted(
            grouped,
            key=repair_location_sort_key,
        )
    ]


def repair_location_sort_key(location: str) -> tuple[int, int]:
    if location == "hook.narration":
        return (0, 0)

    if location == "introduction.narration":
        return (1, 0)

    match = re.fullmatch(
        r"main_sections\[(\d+)\]\.narration",
        location,
    )

    if match:
        return (2, int(match.group(1)))

    if location == "conclusion.narration":
        return (3, 0)

    if location == "call_to_action.narration":
        return (4, 0)

    return (99, 0)


def get_script_block(
    script_data: dict[str, Any],
    location: str,
) -> dict[str, Any]:
    script = script_data.get("script", {})

    if not isinstance(script, dict):
        raise ValueError("Script output is missing script object.")

    if location in {
        "hook.narration",
        "introduction.narration",
        "conclusion.narration",
        "call_to_action.narration",
    }:
        key = location.split(".", 1)[0]
        block = script.get(key)
    else:
        match = re.fullmatch(
            r"main_sections\[(\d+)\]\.narration",
            location,
        )

        if not match:
            raise ValueError(
                f"Unsupported repair location: {location}"
            )

        sections = script.get("main_sections", [])
        index = int(match.group(1))

        if not isinstance(sections, list):
            raise ValueError(
                "Script main_sections must be a list."
            )

        if index >= len(sections):
            raise IndexError(
                f"Repair location is out of range: {location}"
            )

        block = sections[index]

    if not isinstance(block, dict):
        raise ValueError(
            f"Script block must be an object: {location}"
        )

    return copy.deepcopy(block)


def merge_script_repairs(
    script_data: dict[str, Any],
    repairs: list[dict[str, Any]],
    required_locations: list[str],
) -> dict[str, Any]:
    normalized_required = [
        normalize_repair_location(item)
        for item in required_locations
    ]

    if any(item is None for item in normalized_required):
        raise ValueError(
            "Required repair locations contain an unsupported value."
        )

    normalized_required = [
        str(item)
        for item in normalized_required
    ]
    repair_locations = [
        normalize_repair_location(
            item.get("location")
        )
        for item in repairs
        if isinstance(item, dict)
    ]

    if repair_locations != normalized_required:
        raise ValueError(
            "Repair output locations must exactly match the "
            "requested locations in order."
        )

    result = copy.deepcopy(script_data)
    script = result["script"]

    for repair in repairs:
        location = str(
            normalize_repair_location(
                repair["location"]
            )
        )
        narration = str(
            repair.get("narration", "")
        ).strip()
        claim_ids = [
            str(item).strip()
            for item in repair.get("claim_ids", [])
            if str(item).strip()
        ]

        if not narration:
            raise ValueError(
                f"Repair narration is empty: {location}"
            )

        replacement = {
            "narration": narration,
            "claim_ids": list(
                dict.fromkeys(claim_ids)
            ),
        }

        if location in {
            "hook.narration",
            "introduction.narration",
            "conclusion.narration",
            "call_to_action.narration",
        }:
            key = location.split(".", 1)[0]
            existing = script[key]
            existing.update(replacement)
        else:
            match = re.fullmatch(
                r"main_sections\[(\d+)\]\.narration",
                location,
            )

            if not match:
                raise ValueError(
                    f"Unsupported repair location: {location}"
                )

            index = int(match.group(1))
            script["main_sections"][index].update(
                replacement
            )

    return result


def qa_metrics(
    qa_data: dict[str, Any],
) -> dict[str, Any]:
    risk_issues = [
        item
        for item in qa_data.get("risk_issues", [])
        if isinstance(item, dict)
    ]
    high_risk_count = sum(
        1
        for item in risk_issues
        if item.get("severity") == "high"
    )
    unsupported_count = len(
        qa_data.get("unsupported_statements", [])
    )
    risk_issue_count = len(risk_issues)
    factual_score = int(
        qa_data.get("factual_grounding_score", 0)
    )
    risk_score = int(
        qa_data.get("risk_compliance_score", 0)
    )
    approved = (
        qa_data.get("status") == "approved"
        and unsupported_count == 0
        and high_risk_count == 0
        and factual_score == 100
        and risk_score == 100
    )

    rank = (
        0 if approved else 1,
        high_risk_count,
        unsupported_count,
        risk_issue_count,
        100 - factual_score,
        100 - risk_score,
    )

    return {
        "approved": approved,
        "high_risk_issue_count": high_risk_count,
        "unsupported_statement_count": unsupported_count,
        "risk_issue_count": risk_issue_count,
        "factual_grounding_score": factual_score,
        "risk_compliance_score": risk_score,
        "rank": list(rank),
    }


def candidate_is_better(
    candidate_metrics: dict[str, Any],
    incumbent_metrics: dict[str, Any] | None,
) -> bool:
    if incumbent_metrics is None:
        return True

    return tuple(candidate_metrics["rank"]) < tuple(
        incumbent_metrics["rank"]
    )


def archive_fact_risk_candidate(
    *,
    project_root: Path,
    context: dict[str, Any],
    script_data: dict[str, Any],
    qa_data: dict[str, Any],
) -> dict[str, Any]:
    gates = context.setdefault(
        "quality_gates",
        {},
    )
    candidate_index = int(
        gates.get("fact_risk_candidate_count", 0)
    ) + 1
    candidate_dir = (
        project_root
        / "records"
        / "run_contexts"
        / context["channel"]
        / context["video_id"]
        / "candidates"
        / f"candidate_{candidate_index:02d}"
    )
    candidate_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    script_path = candidate_dir / "script.json"
    qa_path = candidate_dir / "fact_risk_qa.json"
    metadata_path = candidate_dir / "metadata.json"
    metrics = qa_metrics(qa_data)

    script_path.write_text(
        json.dumps(
            script_data,
            indent=2,
            ensure_ascii=True,
        )
        + "\n",
        encoding="utf-8",
    )
    qa_path.write_text(
        json.dumps(
            qa_data,
            indent=2,
            ensure_ascii=True,
        )
        + "\n",
        encoding="utf-8",
    )

    def relative(path: Path) -> str:
        return str(
            path.relative_to(project_root)
        ).replace("\\", "/")

    record = {
        "candidate_index": candidate_index,
        "script_reference": relative(script_path),
        "qa_reference": relative(qa_path),
        "metrics": metrics,
    }
    metadata_path.write_text(
        json.dumps(
            record,
            indent=2,
            ensure_ascii=True,
        )
        + "\n",
        encoding="utf-8",
    )

    incumbent = gates.get(
        "fact_risk_best_candidate"
    )
    incumbent_metrics = (
        incumbent.get("metrics")
        if isinstance(incumbent, dict)
        else None
    )
    accepted_as_best = candidate_is_better(
        metrics,
        incumbent_metrics,
    )

    if accepted_as_best:
        gates["fact_risk_best_candidate"] = record

    gates["fact_risk_candidate_count"] = (
        candidate_index
    )

    return {
        "record": record,
        "accepted_as_best": accepted_as_best,
        "best_candidate": gates.get(
            "fact_risk_best_candidate"
        ),
    }


def load_candidate_json(
    project_root: Path,
    reference: str,
) -> dict[str, Any]:
    path = project_root / reference

    if not path.exists():
        raise FileNotFoundError(
            f"Candidate record not found: {path}"
        )

    return json.loads(
        path.read_text(encoding="utf-8-sig")
    )


def restore_best_candidate_script(
    *,
    project_root: Path,
    context: dict[str, Any],
    canonical_script_path: Path,
) -> dict[str, Any]:
    best = context.get(
        "quality_gates",
        {},
    ).get("fact_risk_best_candidate")

    if not isinstance(best, dict):
        raise ValueError(
            "No best factual candidate is available."
        )

    script_data = load_candidate_json(
        project_root,
        best["script_reference"],
    )
    canonical_script_path.write_text(
        json.dumps(
            script_data,
            indent=2,
            ensure_ascii=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return script_data
