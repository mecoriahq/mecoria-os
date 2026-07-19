from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any


LOCATION_ORDER = {
    "hook.narration": (0, 0),
    "introduction.narration": (1, 0),
    "conclusion.narration": (3, 0),
    "call_to_action.narration": (4, 0),
}


def location_sort_key(location: str) -> tuple[int, int]:
    if location in LOCATION_ORDER:
        return LOCATION_ORDER[location]

    match = re.fullmatch(
        r"main_sections\[(\d+)\]\.narration",
        location,
    )

    if match:
        return (2, int(match.group(1)))

    return (99, 0)


def narration_blocks(
    script_data: dict[str, Any],
) -> list[tuple[str, dict[str, Any]]]:
    script = script_data.get("script", {})

    if not isinstance(script, dict):
        raise ValueError("Script output is missing script object.")

    result: list[tuple[str, dict[str, Any]]] = []

    for key in ("hook", "introduction"):
        block = script.get(key)
        if isinstance(block, dict):
            result.append((f"{key}.narration", block))

    sections = script.get("main_sections", [])
    if isinstance(sections, list):
        for index, block in enumerate(sections):
            if isinstance(block, dict):
                result.append(
                    (f"main_sections[{index}].narration", block)
                )

    for key in ("conclusion", "call_to_action"):
        block = script.get(key)
        if isinstance(block, dict):
            result.append((f"{key}.narration", block))

    return result


def _tokens(value: Any) -> list[str]:
    return re.findall(
        r"\b[a-z0-9][a-z0-9'-]*\b",
        str(value or "").lower(),
    )


def _ngrams(tokens: list[str], size: int = 4) -> set[tuple[str, ...]]:
    if len(tokens) < size:
        return set()
    return {
        tuple(tokens[index : index + size])
        for index in range(len(tokens) - size + 1)
    }


def _main_locations(
    script_data: dict[str, Any],
) -> list[str]:
    return [
        location
        for location, _ in narration_blocks(script_data)
        if location.startswith("main_sections[")
    ]


def _lowest_specificity_main_locations(
    script_data: dict[str, Any],
    limit: int = 2,
) -> list[str]:
    scored: list[tuple[float, str]] = []

    for location, block in narration_blocks(script_data):
        if not location.startswith("main_sections["):
            continue

        narration = str(block.get("narration", ""))
        words = _tokens(narration)
        concrete_markers = len(
            re.findall(
                r"\b(?:19|20)\d{2}\b|\b\d+(?:\.\d+)?\b",
                narration,
            )
        )
        claim_count = len(block.get("claim_ids", []))
        density = (
            (concrete_markers * 2 + claim_count)
            / max(1, len(words))
        )
        scored.append((density, location))

    scored.sort(key=lambda item: (item[0], location_sort_key(item[1])))
    return [location for _, location in scored[:limit]]


def _repetition_locations(
    script_data: dict[str, Any],
    limit: int = 2,
) -> list[str]:
    blocks = narration_blocks(script_data)
    gram_locations: dict[tuple[str, ...], list[str]] = defaultdict(list)

    for location, block in blocks:
        for gram in _ngrams(_tokens(block.get("narration", ""))):
            gram_locations[gram].append(location)

    repeated = {
        gram: locations
        for gram, locations in gram_locations.items()
        if len(set(locations)) > 1
    }

    location_counts: Counter[str] = Counter()
    for locations in repeated.values():
        ordered = sorted(set(locations), key=location_sort_key)
        for location in ordered[1:]:
            location_counts[location] += 1

    if location_counts:
        return [
            location
            for location, _ in sorted(
                location_counts.items(),
                key=lambda item: (-item[1], location_sort_key(item[0])),
            )[:limit]
        ]

    main = _main_locations(script_data)
    if len(main) <= 1:
        return main

    # Deterministic fallback: repair the two latest exposition blocks,
    # where summary repetition most often accumulates.
    return main[-limit:]


def _issue_location(issue: dict[str, Any]) -> str | None:
    raw = str(
        issue.get("location")
        or issue.get("field")
        or ""
    ).lower()

    if "hook" in raw:
        return "hook.narration"
    if "introduction" in raw or "intro" in raw:
        return "introduction.narration"
    if "conclusion" in raw:
        return "conclusion.narration"
    if "call_to_action" in raw or "cta" in raw:
        return "call_to_action.narration"

    match = re.search(r"main_sections\[(\d+)\]", raw)
    if match:
        return f"main_sections[{int(match.group(1))}].narration"

    return None


def build_editorial_repair_targets(
    *,
    script_data: dict[str, Any],
    qa_data: dict[str, Any],
    gate_result: dict[str, Any],
    maximum_targets: int = 6,
) -> list[dict[str, Any]]:
    if maximum_targets < 1:
        raise ValueError("maximum_targets must be at least 1.")

    valid_locations = {
        location
        for location, _ in narration_blocks(script_data)
    }
    objectives: dict[str, list[dict[str, Any]]] = defaultdict(list)

    failures = gate_result.get("failures", [])
    if not isinstance(failures, list):
        failures = []

    checks = qa_data.get("checks", {})
    if not isinstance(checks, dict):
        checks = {}

    def add(
        location: str,
        *,
        check: str,
        objective: str,
    ) -> None:
        if location not in valid_locations:
            return

        score = checks.get(check, {}).get("score")
        minimum = None
        for failure in failures:
            if isinstance(failure, dict) and failure.get("check") == check:
                minimum = failure.get("minimum")
                break

        record = {
            "check": check,
            "score": score,
            "minimum": minimum,
            "objective": objective,
        }
        if record not in objectives[location]:
            objectives[location].append(record)

    failed_checks = {
        str(item.get("check"))
        for item in failures
        if isinstance(item, dict) and item.get("check")
    }

    if "hook_strength" in failed_checks:
        add(
            "hook.narration",
            check="hook_strength",
            objective=(
                "Open with a concrete approved tension, decision, or "
                "consequence without adding unsupported drama."
            ),
        )

    if "hook_intro_distinctness" in failed_checks:
        add(
            "hook.narration",
            check="hook_intro_distinctness",
            objective="Make the hook pose the central tension only.",
        )
        add(
            "introduction.narration",
            check="hook_intro_distinctness",
            objective=(
                "Advance chronology and context instead of repeating "
                "the hook."
            ),
        )

    if "narrative_spine" in failed_checks:
        for location in (
            "introduction.narration",
            *(_main_locations(script_data)[:1]),
            "conclusion.narration",
        ):
            add(
                location,
                check="narrative_spine",
                objective=(
                    "Clarify the cause-and-effect connection to the "
                    "next documented turning point."
                ),
            )

    if "specificity" in failed_checks:
        for location in _lowest_specificity_main_locations(script_data):
            add(
                location,
                check="specificity",
                objective=(
                    "Replace abstract phrasing with approved dates, "
                    "actions, attribution, and consequences already "
                    "present in the claims ledger."
                ),
            )

    if "repetition_risk" in failed_checks:
        for location in _repetition_locations(script_data):
            add(
                location,
                check="repetition_risk",
                objective=(
                    "Remove repeated framing and make this block perform "
                    "one distinct narrative job."
                ),
            )

    if "standard_cta" in failed_checks:
        add(
            "call_to_action.narration",
            check="standard_cta",
            objective="Ask viewers to comment, like, and subscribe concisely.",
        )

    if "hiddenova_brand_intro" in failed_checks:
        add(
            "introduction.narration",
            check="hiddenova_brand_intro",
            objective="Include the required brand introduction line.",
        )

    issues = qa_data.get("issues", [])
    if isinstance(issues, list):
        for issue in issues:
            if not isinstance(issue, dict):
                continue
            location = _issue_location(issue)
            if not location or location not in valid_locations:
                continue
            record = {
                "check": "model_issue",
                "score": None,
                "minimum": None,
                "objective": str(
                    issue.get("message")
                    or issue.get("suggestion")
                    or "Resolve the editorial issue without adding facts."
                ),
            }
            if record not in objectives[location]:
                objectives[location].append(record)

    ordered_locations = sorted(objectives, key=location_sort_key)
    ordered_locations = ordered_locations[:maximum_targets]

    return [
        {
            "location": location,
            "issues": objectives[location],
        }
        for location in ordered_locations
    ]
