from __future__ import annotations

import copy
from difflib import SequenceMatcher
import hashlib
import json
import re
import unicodedata
from pathlib import Path
from typing import Any

from core.factuality import validate_script_claim_references


REPAIR_VERSION = "deterministic_factual_repair_v2"
MAX_DETERMINISTIC_REPAIR_PASSES = 2

SAFE_ACTION_TYPES = {
    "add_claim_id",
    "remove_exact_text",
}

DOUBLE_QUOTED_TEXT = re.compile(
    r'[\u201c"]([^\u201d"]+)[\u201d"]'
)
CLAIM_ID_PATTERN = re.compile(r"\bC\d{2,}\b", re.IGNORECASE)
MAIN_SECTION_LOCATION = re.compile(
    r"^main_sections\[(\d+)\]\.narration$"
)
SENTENCE_BOUNDARY = re.compile(
    r"[.!?](?=\s+(?:[\"\u201c\u2018']?[A-Z0-9])|$)"
)
MIN_ANCHORED_STATEMENT_WORDS = 12
ANCHORED_PREFIX_WORDS = 8
ANCHORED_SUFFIX_WORDS = 6
MIN_ANCHORED_SIMILARITY = 0.72
MIN_ANCHORED_LENGTH_RATIO = 0.70


class FactualRepairError(RuntimeError):
    """Raised when a deterministic factual repair cannot be applied safely."""


def _strip_outer_quotes(value: Any) -> str:
    text = str(value or "").strip()

    pairs = {
        ('"', '"'),
        ("'", "'"),
        ("\u201c", "\u201d"),
        ("\u2018", "\u2019"),
    }

    while len(text) >= 2 and (text[0], text[-1]) in pairs:
        text = text[1:-1].strip()

    return text


def _normalize_location(value: Any) -> str | None:
    location = str(value or "").strip()

    if location in {
        "hook.narration",
        "introduction.narration",
        "conclusion.narration",
        "call_to_action.narration",
    }:
        return location

    match = MAIN_SECTION_LOCATION.fullmatch(location)

    if match:
        return f"main_sections[{int(match.group(1))}].narration"

    return None


def _get_script_block(
    script_data: dict[str, Any],
    location: str,
) -> dict[str, Any]:
    script = script_data.get("script")

    if not isinstance(script, dict):
        raise FactualRepairError(
            "Script output is missing the script object."
        )

    if location in {
        "hook.narration",
        "introduction.narration",
        "conclusion.narration",
        "call_to_action.narration",
    }:
        key = location.split(".", 1)[0]
        block = script.get(key)
    else:
        match = MAIN_SECTION_LOCATION.fullmatch(location)

        if not match:
            raise FactualRepairError(
                f"Unsupported factual repair location: {location}"
            )

        sections = script.get("main_sections")

        if not isinstance(sections, list):
            raise FactualRepairError(
                "Script main_sections must be a list."
            )

        index = int(match.group(1))

        if index >= len(sections):
            raise FactualRepairError(
                f"Factual repair location is out of range: {location}"
            )

        block = sections[index]

    if not isinstance(block, dict):
        raise FactualRepairError(
            f"Script block must be an object: {location}"
        )

    return block


def _quoted_fragments(text: str) -> list[str]:
    return [
        match.group(1).strip()
        for match in DOUBLE_QUOTED_TEXT.finditer(text)
        if match.group(1).strip()
    ]


def _approved_claim_ids(qa_data: dict[str, Any]) -> set[str]:
    return {
        str(item).strip().upper()
        for item in qa_data.get("approved_claim_ids", [])
        if str(item).strip()
    }


def _action_key(action: dict[str, Any]) -> str:
    return json.dumps(
        action,
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
    )


def _normalize_match_text(value: Any) -> str:
    text = unicodedata.normalize(
        "NFKC",
        str(value or ""),
    ).casefold()
    text = text.replace("\u2019", "'").replace("\u2018", "'")
    text = text.replace("\u2013", "-").replace("\u2014", "-")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def _sentence_candidates(text: str) -> list[str]:
    candidates: list[str] = []
    start = 0

    for match in SENTENCE_BOUNDARY.finditer(text):
        end = match.end()
        candidate = text[start:end].strip()

        if candidate:
            candidates.append(candidate)

        start = end

    remainder = text[start:].strip()

    if remainder:
        candidates.append(remainder)

    return candidates


def _find_safe_full_statement_match(
    *,
    narration: str,
    statement: str,
) -> tuple[dict[str, Any] | None, str]:
    if not statement:
        return None, "statement_missing"

    if statement in narration:
        return {
            "text": statement,
            "mode": "exact",
            "similarity": 1.0,
        }, "exact_match"

    normalized_statement = _normalize_match_text(statement)
    statement_tokens = normalized_statement.split()

    if len(statement_tokens) < MIN_ANCHORED_STATEMENT_WORDS:
        return None, "statement_too_short_for_anchored_match"

    normalized_exact: list[dict[str, Any]] = []
    anchored: list[dict[str, Any]] = []

    for candidate in _sentence_candidates(narration):
        normalized_candidate = _normalize_match_text(candidate)
        candidate_tokens = normalized_candidate.split()

        if normalized_candidate == normalized_statement:
            normalized_exact.append({
                "text": candidate,
                "mode": "normalized_exact",
                "similarity": 1.0,
            })
            continue

        if len(candidate_tokens) < MIN_ANCHORED_STATEMENT_WORDS:
            continue

        length_ratio = (
            min(len(statement_tokens), len(candidate_tokens))
            / max(len(statement_tokens), len(candidate_tokens))
        )

        if length_ratio < MIN_ANCHORED_LENGTH_RATIO:
            continue

        prefix_size = min(
            ANCHORED_PREFIX_WORDS,
            len(statement_tokens),
            len(candidate_tokens),
        )
        suffix_size = min(
            ANCHORED_SUFFIX_WORDS,
            len(statement_tokens),
            len(candidate_tokens),
        )
        prefix_matches = (
            statement_tokens[:prefix_size]
            == candidate_tokens[:prefix_size]
        )
        suffix_matches = (
            statement_tokens[-suffix_size:]
            == candidate_tokens[-suffix_size:]
        )

        if not prefix_matches or not suffix_matches:
            continue

        similarity = SequenceMatcher(
            None,
            normalized_statement,
            normalized_candidate,
        ).ratio()

        if similarity < MIN_ANCHORED_SIMILARITY:
            continue

        anchored.append({
            "text": candidate,
            "mode": "anchored_sentence",
            "similarity": round(similarity, 6),
        })

    if len(normalized_exact) == 1:
        return normalized_exact[0], "normalized_exact_match"

    if len(normalized_exact) > 1:
        return None, "ambiguous_normalized_exact_match"

    if len(anchored) == 1:
        return anchored[0], "anchored_sentence_match"

    if len(anchored) > 1:
        return None, "ambiguous_anchored_sentence_match"

    return None, "statement_not_located_safely"


def _build_issue_action(
    *,
    script_data: dict[str, Any],
    qa_data: dict[str, Any],
    issue: dict[str, Any],
    issue_index: int,
) -> tuple[list[dict[str, Any]], str | None]:
    location = _normalize_location(issue.get("location"))

    if not location:
        return [], "unsupported_or_missing_location"

    try:
        block = _get_script_block(script_data, location)
    except FactualRepairError as error:
        return [], str(error)

    narration = str(block.get("narration") or "")
    claim_ids = {
        str(item).strip().upper()
        for item in block.get("claim_ids", [])
        if str(item).strip()
    }
    statement = _strip_outer_quotes(issue.get("statement"))
    suggestion = str(issue.get("suggested_action") or "").strip()
    suggestion_lower = suggestion.lower()
    approved_claim_ids = _approved_claim_ids(qa_data)
    actions: list[dict[str, Any]] = []

    claim_candidates = [
        item.upper()
        for item in CLAIM_ID_PATTERN.findall(suggestion)
    ]

    if (
        re.search(r"\b(attach|add|include)\b", suggestion_lower)
        and claim_candidates
    ):
        for claim_id in claim_candidates:
            if claim_id not in approved_claim_ids:
                return [], f"claim_id_not_approved:{claim_id}"

            if claim_id not in claim_ids:
                actions.append({
                    "type": "add_claim_id",
                    "location": location,
                    "claim_id": claim_id,
                    "issue_index": issue_index,
                })

        if actions:
            return actions, None

        # An already attached approved claim means the issue is stale rather
        # than safely repairable. The QA must be rerun after another change.
        return [], "claim_id_already_attached"

    quoted = _quoted_fragments(suggestion)

    if "remove" in suggestion_lower:
        for fragment in quoted:
            if fragment and fragment in narration:
                return [{
                    "type": "remove_exact_text",
                    "location": location,
                    "old_text": fragment,
                    "issue_index": issue_index,
                    "match_mode": "exact_fragment",
                    "match_similarity": 1.0,
                }], None

    full_statement_removal_allowed = any(
        phrase in suggestion_lower
        for phrase in (
            "remove",
            "qualify",
            "use a more neutral",
            "keep to the",
            "tie the",
        )
    )

    if statement and full_statement_removal_allowed:
        match, match_reason = _find_safe_full_statement_match(
            narration=narration,
            statement=statement,
        )

        if match is not None:
            return [{
                "type": "remove_exact_text",
                "location": location,
                "old_text": match["text"],
                "issue_index": issue_index,
                "match_mode": match["mode"],
                "match_similarity": match["similarity"],
            }], None

        return [], match_reason

    return [], "no_whitelisted_exact_action"


def build_deterministic_factual_repair_plan(
    *,
    script_data: dict[str, Any],
    qa_data: dict[str, Any],
) -> dict[str, Any]:
    unsupported = [
        item
        for item in qa_data.get("unsupported_statements", [])
        if isinstance(item, dict)
    ]
    risk_issues = [
        item
        for item in qa_data.get("risk_issues", [])
        if isinstance(item, dict)
    ]
    actions: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    stale_issues: list[dict[str, Any]] = []
    covered_locations: set[str] = set()
    stale_locations: set[str] = set()

    high_risk = [
        item
        for item in risk_issues
        if str(item.get("severity", "")).lower() == "high"
    ]

    if high_risk:
        unresolved.extend({
            "kind": "high_risk_issue",
            "location": item.get("location"),
            "reason": item.get("message") or item.get("required_edit"),
        } for item in high_risk)

    for index, issue in enumerate(unsupported):
        issue_actions, reason = _build_issue_action(
            script_data=script_data,
            qa_data=qa_data,
            issue=issue,
            issue_index=index,
        )

        if reason:
            location = _normalize_location(issue.get("location"))
            stale_reasons = {
                "statement_not_located_safely",
                "statement_missing",
                "statement_too_short_for_anchored_match",
                "claim_id_already_attached",
            }

            if reason in stale_reasons and location:
                stale_issues.append({
                    "kind": "stale_or_unanchored_qa_statement",
                    "issue_index": index,
                    "location": location,
                    "statement": issue.get("statement"),
                    "reason": reason,
                })
                stale_locations.add(location)
                continue

            unresolved.append({
                "kind": "unsupported_statement",
                "issue_index": index,
                "location": issue.get("location"),
                "statement": issue.get("statement"),
                "reason": reason,
            })
            continue

        for action in issue_actions:
            if action["type"] not in SAFE_ACTION_TYPES:
                unresolved.append({
                    "kind": "unsafe_action_type",
                    "issue_index": index,
                    "location": issue.get("location"),
                    "reason": action["type"],
                })
                continue

            actions.append(action)
            covered_locations.add(action["location"])

    # Low/medium risk issues may proceed only when an exact action already
    # covers the same script block. This keeps the risk layer from authorizing
    # an unrelated edit.
    for item in risk_issues:
        severity = str(item.get("severity", "")).lower()

        if severity == "high":
            continue

        location = _normalize_location(item.get("location"))

        if location in stale_locations:
            stale_issues.append({
                "kind": "stale_or_unanchored_risk_issue",
                "location": location,
                "reason": item.get("message") or item.get("required_edit"),
            })
            continue

        if not location or location not in covered_locations:
            unresolved.append({
                "kind": "uncovered_risk_issue",
                "location": item.get("location"),
                "reason": item.get("message") or item.get("required_edit"),
            })

    deduplicated: list[dict[str, Any]] = []
    seen: set[str] = set()

    for action in actions:
        key = _action_key(action)

        if key in seen:
            continue

        seen.add(key)
        deduplicated.append(action)

    signature_payload = {
        "actions": deduplicated,
        "unresolved": unresolved,
        "stale_issues": stale_issues,
    }
    signature = hashlib.sha256(
        json.dumps(
            signature_payload,
            sort_keys=True,
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    available = (
        bool(unsupported)
        and not unresolved
        and bool(deduplicated)
    )

    return {
        "version": "1.0",
        "available": available,
        "action_count": len(deduplicated),
        "actions": deduplicated,
        "action_types": sorted({
            action["type"]
            for action in deduplicated
        }),
        "unsupported_statement_count": len(unsupported),
        "risk_issue_count": len(risk_issues),
        "high_risk_issue_count": len(high_risk),
        "unresolved_count": len(unresolved),
        "unresolved": unresolved,
        "stale_issue_count": len(stale_issues),
        "stale_issues": stale_issues,
        "signature": signature,
        "reason": (
            "all_current_anchored_issues_have_whitelisted_actions"
            if available
            else "manual_or_model_repair_required"
        ),
    }


def _cleanup_narration(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    cleaned = re.sub(r"\s+([,.;:!?])", r"\1", cleaned)
    cleaned = re.sub(r"^[,;:\-\s]+", "", cleaned)
    cleaned = re.sub(r"([.!?])\s*([.!?])", r"\1", cleaned)

    chars = list(cleaned)
    capitalize_next = True

    for index, char in enumerate(chars):
        if capitalize_next and char.isalpha():
            chars[index] = char.upper()
            capitalize_next = False
        elif char in ".!?":
            capitalize_next = True
        elif not char.isspace() and capitalize_next:
            # Opening quotes or punctuation do not consume capitalization.
            continue

    return "".join(chars).strip()


def apply_deterministic_factual_repair(
    *,
    script_data: dict[str, Any],
    ledger_data: dict[str, Any],
    qa_data: dict[str, Any],
    plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    plan = plan or build_deterministic_factual_repair_plan(
        script_data=script_data,
        qa_data=qa_data,
    )

    if plan.get("available") is not True:
        return {
            "status": "not_available",
            "applied": False,
            "plan": plan,
            "reason": plan.get("reason"),
        }

    repaired = copy.deepcopy(script_data)
    applied_actions: list[dict[str, Any]] = []

    for action in plan["actions"]:
        action_type = action["type"]
        location = action["location"]
        block = _get_script_block(repaired, location)

        if action_type == "add_claim_id":
            claim_id = str(action["claim_id"]).upper()
            approved = _approved_claim_ids(qa_data)

            if claim_id not in approved:
                raise FactualRepairError(
                    f"Refusing unapproved claim ID: {claim_id}"
                )

            claim_ids = [
                str(item).strip().upper()
                for item in block.get("claim_ids", [])
                if str(item).strip()
            ]

            if claim_id not in claim_ids:
                claim_ids.append(claim_id)
                block["claim_ids"] = claim_ids
                applied_actions.append(action)

            continue

        narration = str(block.get("narration") or "")
        old_text = str(action.get("old_text") or "")

        if not old_text:
            raise FactualRepairError(
                f"Exact text is missing for action: {action_type}"
            )

        if old_text not in narration:
            if action_type == "remove_exact_text":
                continue

            if (
                action_type == "replace_exact_text"
                and str(action.get("new_text") or "")
                in narration
            ):
                continue

            raise FactualRepairError(
                "Exact factual repair text was not found at "
                f"{location}: {old_text}"
            )

        if action_type == "remove_exact_text":
            revised = narration.replace(old_text, "", 1)
        elif action_type == "replace_exact_text":
            revised = narration.replace(
                old_text,
                str(action.get("new_text") or ""),
                1,
            )
        else:
            raise FactualRepairError(
                f"Unsupported deterministic action: {action_type}"
            )

        revised = _cleanup_narration(revised)

        if not revised:
            raise FactualRepairError(
                f"Deterministic repair would empty narration: {location}"
            )

        block["narration"] = revised
        applied_actions.append(action)

    if not applied_actions:
        return {
            "status": "already_satisfied",
            "applied": False,
            "plan": plan,
            "reason": "all_actions_already_satisfied",
        }

    deterministic = validate_script_claim_references(
        script_data=repaired,
        ledger_data=ledger_data,
    )

    if deterministic.get("approved") is not True:
        raise FactualRepairError(
            "Deterministic factual repair failed claim validation: "
            + "; ".join(
                str(item)
                for item in deterministic.get("errors", [])
            )
        )

    return {
        "status": "applied",
        "applied": True,
        "plan": plan,
        "repaired_script": repaired,
        "applied_action_count": len(applied_actions),
        "applied_actions": applied_actions,
        "deterministic_validation": deterministic,
        "reason": "whitelisted_exact_actions_applied",
    }


def _resolve_reference(
    *,
    project_root: Path,
    context: dict[str, Any],
    key: str,
) -> Path | None:
    reference = context.get("outputs", {}).get(key)

    if not reference:
        reference = context.get("sources", {}).get(key)

    if reference:
        path = Path(str(reference))

        if not path.is_absolute():
            path = project_root / path

        if path.is_file():
            return path

    channel = str(context.get("channel") or "")
    video_id = str(context.get("video_id") or "")
    run_id = str(context.get("run_id") or "")
    fallback_map = {
        "script": (
            project_root / "agents" / "script" / "output"
            / channel / video_id / run_id / "script.json"
        ),
        "claims_ledger": (
            project_root / "agents" / "claims_ledger" / "output"
            / channel / video_id / run_id / "claims_ledger.json"
        ),
        "fact_risk_qa": (
            project_root / "agents" / "fact_risk_qa" / "output"
            / channel / video_id / run_id / "fact_risk_qa.json"
        ),
    }
    fallback = fallback_map.get(key)

    if fallback and fallback.is_file():
        return fallback

    return None


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def evaluate_context_deterministic_factual_repair(
    *,
    project_root: Path,
    context: dict[str, Any],
) -> dict[str, Any]:
    paths = {
        key: _resolve_reference(
            project_root=project_root,
            context=context,
            key=key,
        )
        for key in (
            "script",
            "claims_ledger",
            "fact_risk_qa",
        )
    }
    missing = [
        key
        for key, path in paths.items()
        if path is None
    ]

    if missing:
        return {
            "status": "not_available",
            "available": False,
            "reason": "missing_context_references",
            "missing": missing,
        }

    script_data = _load_json(paths["script"])
    ledger_data = _load_json(paths["claims_ledger"])
    qa_data = _load_json(paths["fact_risk_qa"])
    plan = build_deterministic_factual_repair_plan(
        script_data=script_data,
        qa_data=qa_data,
    )

    if plan.get("available") is not True:
        return {
            "status": "not_available",
            "available": False,
            "reason": plan.get("reason"),
            "plan": plan,
            "paths": {
                key: str(path.relative_to(project_root)).replace("\\", "/")
                for key, path in paths.items()
            },
        }

    try:
        result = apply_deterministic_factual_repair(
            script_data=script_data,
            ledger_data=ledger_data,
            qa_data=qa_data,
            plan=plan,
        )
    except (FactualRepairError, KeyError, TypeError, ValueError) as error:
        return {
            "status": "not_available",
            "available": False,
            "reason": "deterministic_repair_validation_failed",
            "error": str(error),
            "plan": plan,
        }

    return {
        **result,
        "available": result.get("applied") is True,
        "script_data": script_data,
        "ledger_data": ledger_data,
        "qa_data": qa_data,
        "paths": {
            key: str(path.relative_to(project_root)).replace("\\", "/")
            for key, path in paths.items()
        },
    }


def deterministic_factual_repair_available(
    *,
    project_root: Path,
    context: dict[str, Any],
) -> bool:
    result = evaluate_context_deterministic_factual_repair(
        project_root=project_root,
        context=context,
    )
    return result.get("available") is True
