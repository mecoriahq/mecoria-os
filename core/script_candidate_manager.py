from __future__ import annotations

import copy
import hashlib
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



def iter_script_narration_blocks(
    script_data: dict[str, Any],
) -> list[tuple[str, dict[str, Any]]]:
    script = script_data.get("script", {})

    if not isinstance(script, dict):
        raise ValueError(
            "Script output is missing script object."
        )

    blocks: list[tuple[str, dict[str, Any]]] = []

    for key in (
        "hook",
        "introduction",
    ):
        block = script.get(key)

        if isinstance(block, dict):
            blocks.append(
                (f"{key}.narration", block)
            )

    sections = script.get("main_sections", [])

    if isinstance(sections, list):
        for index, block in enumerate(sections):
            if isinstance(block, dict):
                blocks.append(
                    (
                        f"main_sections[{index}].narration",
                        block,
                    )
                )

    for key in (
        "conclusion",
        "call_to_action",
    ):
        block = script.get(key)

        if isinstance(block, dict):
            blocks.append(
                (f"{key}.narration", block)
            )

    return blocks


def normalize_statement_text(value: Any) -> str:
    text = str(value or "")
    text = text.replace("\u201c", '"')
    text = text.replace("\u201d", '"')
    text = text.replace("\u2018", "'")
    text = text.replace("\u2019", "'")
    text = re.sub(r"\s+", " ", text)
    return text.strip().strip('"').lower()


def find_statement_location(
    script_data: dict[str, Any],
    statement: Any,
) -> str | None:
    needle = normalize_statement_text(statement)

    if not needle:
        return None

    matches = []

    for location, block in iter_script_narration_blocks(
        script_data
    ):
        narration = normalize_statement_text(
            block.get("narration", "")
        )

        if needle in narration:
            matches.append(location)

    if len(matches) == 1:
        return matches[0]

    return None


def repair_location_exists(
    script_data: dict[str, Any],
    location: str,
) -> bool:
    try:
        get_script_block(
            script_data=script_data,
            location=location,
        )
    except (IndexError, KeyError, TypeError, ValueError):
        return False

    return True


def resolve_repair_targets_for_script(
    script_data: dict[str, Any],
    repair_targets: list[dict[str, Any]],
) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    stale_issues: list[dict[str, Any]] = []
    relocated_issues: list[dict[str, Any]] = []

    for target in repair_targets:
        if not isinstance(target, dict):
            continue

        original_location = normalize_repair_location(
            target.get("location")
        )
        target_issues = target.get("issues", [])

        if not isinstance(target_issues, list):
            target_issues = []

        for issue in target_issues:
            if not isinstance(issue, dict):
                continue

            resolved_location = original_location

            if (
                not resolved_location
                or not repair_location_exists(
                    script_data,
                    resolved_location,
                )
            ):
                resolved_location = find_statement_location(
                    script_data=script_data,
                    statement=issue.get("statement"),
                )

            if not resolved_location:
                stale_record = copy.deepcopy(issue)
                stale_record[
                    "original_location"
                ] = target.get("location")
                stale_issues.append(stale_record)
                continue

            issue_copy = copy.deepcopy(issue)
            issue_copy["location"] = resolved_location
            grouped.setdefault(
                resolved_location,
                [],
            ).append(issue_copy)

            if resolved_location != original_location:
                relocated_issues.append({
                    "original_location": (
                        target.get("location")
                    ),
                    "resolved_location": resolved_location,
                    "statement": issue.get("statement"),
                })

    targets = [
        {
            "location": location,
            "issues": grouped[location],
        }
        for location in sorted(
            grouped,
            key=repair_location_sort_key,
        )
    ]

    return {
        "targets": targets,
        "stale_issues": stale_issues,
        "relocated_issues": relocated_issues,
    }


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


def candidates_are_factually_equivalent(
    candidate_metrics: dict[str, Any],
    incumbent_metrics: dict[str, Any] | None,
) -> bool:
    if incumbent_metrics is None:
        return False

    return (
        bool(candidate_metrics.get("approved"))
        and bool(incumbent_metrics.get("approved"))
        and tuple(candidate_metrics.get("rank", []))
        == tuple(incumbent_metrics.get("rank", []))
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


def load_founder_manual_revision_state(
    *,
    project_root: Path,
    context: dict[str, Any],
) -> dict[str, Any] | None:
    marker = context.get(
        "quality_gates",
        {},
    ).get("founder_manual_editorial_revision")

    if not isinstance(marker, dict):
        return None

    lineage_active = bool(
        marker.get("manual_revision_lineage_active")
        or marker.get("fact_risk_repair_chain_active")
    )
    fallback_recovery_allowed = bool(
        marker.get("factual_validation_status")
        == "fallback_to_best"
        and (
            marker.get("recovered_candidate_script_reference")
            or marker.get("active_candidate_script_reference")
        )
    )
    pending_fact_risk = bool(
        marker.get("pending_fact_risk_qa")
    )

    if not (
        pending_fact_risk
        or lineage_active
        or fallback_recovery_allowed
    ):
        return None

    reference = (
        context.get(
            "sources",
            {},
        ).get("founder_manual_editorial_revision")
        or marker.get("manual_revision_record_reference")
    )
    record: dict[str, Any] | None = None
    revised_hash = ""

    if reference:
        record_path = project_root / str(reference)

        if record_path.is_file():
            loaded = json.loads(
                record_path.read_text(encoding="utf-8-sig")
            )

            identity_matches = all(
                str(loaded.get(key))
                == str(context.get(key))
                for key in ("channel", "video_id", "run_id")
            )
            candidate_hash = str(
                loaded.get("revised_script_sha256", "")
            ).strip().lower()

            if (
                identity_matches
                and re.fullmatch(r"[0-9a-f]{64}", candidate_hash)
            ):
                record = loaded
                revised_hash = candidate_hash

    if not revised_hash:
        recovered_reference = (
            marker.get("recovered_candidate_script_reference")
            or marker.get("active_candidate_script_reference")
        )

        if recovered_reference:
            recovered_path = (
                project_root / str(recovered_reference)
            )

            if recovered_path.is_file():
                revised_hash = sha256_file(recovered_path)
                record = {
                    "channel": context.get("channel"),
                    "video_id": context.get("video_id"),
                    "run_id": context.get("run_id"),
                    "revised_script_sha256": revised_hash,
                    "recovered_script_reference": str(
                        recovered_reference
                    ),
                }

    if not revised_hash or record is None:
        return None

    return {
        "marker": marker,
        "record": record,
        "reference": str(reference or ""),
        "revised_script_sha256": revised_hash,
        "repair_chain_active": bool(
            marker.get("fact_risk_repair_chain_active")
        ),
        "lineage_active": lineage_active,
        "fallback_recovery_allowed": (
            fallback_recovery_allowed
        ),
    }


def evaluate_founder_manual_candidate_policy(
    *,
    project_root: Path,
    context: dict[str, Any],
    candidate_record: dict[str, Any],
    script_data: dict[str, Any],
    qa_data: dict[str, Any],
) -> dict[str, Any]:
    state = load_founder_manual_revision_state(
        project_root=project_root,
        context=context,
    )

    if state is None:
        return {
            "action": "standard_ranking",
            "reason": "no_pending_founder_manual_revision",
            "matches_manual_revision": False,
        }

    script_reference = str(
        candidate_record.get("script_reference", "")
    )
    candidate_path = project_root / script_reference

    if not candidate_path.is_file():
        return {
            "action": "standard_ranking",
            "reason": "candidate_script_missing",
            "matches_manual_revision": False,
        }

    candidate_hash = sha256_file(candidate_path)
    exact_match = (
        candidate_hash == state["revised_script_sha256"]
    )
    chain_match = bool(
        state["repair_chain_active"]
        or state.get("lineage_active")
    )
    matches_manual = exact_match or chain_match

    if not matches_manual:
        return {
            "action": "standard_ranking",
            "reason": "candidate_not_in_manual_revision_chain",
            "matches_manual_revision": False,
            "candidate_script_sha256": candidate_hash,
        }

    metrics = qa_metrics(qa_data)

    if metrics["approved"]:
        return {
            "action": "allow_editorial_evaluation",
            "reason": "manual_revision_factually_approved",
            "matches_manual_revision": True,
            "metrics": metrics,
            "repair_target_count": 0,
            "candidate_script_sha256": candidate_hash,
        }

    if int(metrics["high_risk_issue_count"]) > 0:
        return {
            "action": "fallback_to_best",
            "reason": "manual_revision_has_high_risk_issue",
            "matches_manual_revision": True,
            "metrics": metrics,
            "repair_target_count": 0,
            "candidate_script_sha256": candidate_hash,
        }

    resolved = resolve_repair_targets_for_script(
        script_data=script_data,
        repair_targets=extract_repair_targets(qa_data),
    )
    targets = resolved["targets"]

    if not targets:
        return {
            "action": "fallback_to_best",
            "reason": "manual_revision_has_no_actionable_targets",
            "matches_manual_revision": True,
            "metrics": metrics,
            "repair_target_count": 0,
            "candidate_script_sha256": candidate_hash,
        }

    return {
        "action": "preserve_for_section_repair",
        "reason": "repairable_founder_manual_revision",
        "matches_manual_revision": True,
        "metrics": metrics,
        "repair_target_count": len(targets),
        "repair_locations": [
            item["location"]
            for item in targets
        ],
        "candidate_script_sha256": candidate_hash,
    }


def find_recoverable_founder_manual_candidate(
    *,
    project_root: Path,
    context: dict[str, Any],
) -> dict[str, Any] | None:
    state = load_founder_manual_revision_state(
        project_root=project_root,
        context=context,
    )

    if state is None:
        return None

    candidate_root = (
        project_root
        / "records"
        / "run_contexts"
        / str(context["channel"])
        / str(context["video_id"])
        / "candidates"
    )

    if not candidate_root.is_dir():
        return None

    for metadata_path in sorted(
        candidate_root.glob("candidate_*/metadata.json"),
        reverse=True,
    ):
        record = json.loads(
            metadata_path.read_text(encoding="utf-8-sig")
        )
        script_path = project_root / str(
            record.get("script_reference", "")
        )
        qa_path = project_root / str(
            record.get("qa_reference", "")
        )

        if not script_path.is_file() or not qa_path.is_file():
            continue

        if sha256_file(script_path) != state[
            "revised_script_sha256"
        ]:
            continue

        script_data = json.loads(
            script_path.read_text(encoding="utf-8-sig")
        )
        qa_data = json.loads(
            qa_path.read_text(encoding="utf-8-sig")
        )
        policy = evaluate_founder_manual_candidate_policy(
            project_root=project_root,
            context=context,
            candidate_record=record,
            script_data=script_data,
            qa_data=qa_data,
        )

        if policy["action"] != "preserve_for_section_repair":
            continue

        return {
            "record": record,
            "script_data": script_data,
            "qa_data": qa_data,
            "policy": policy,
        }

    return None


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
