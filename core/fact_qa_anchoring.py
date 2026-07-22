from __future__ import annotations

import json
import re
import unicodedata
from typing import Any


MAIN_SECTION_LOCATION = re.compile(
    r"^main_sections\[(\d+)\]\.narration$"
)


class FactQaAnchoringError(ValueError):
    """Raised when Fact QA reports text outside the evaluated script."""


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


def _normalize(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = text.replace("\u2019", "'").replace("\u2018", "'")
    text = text.replace("\u2013", "-").replace("\u2014", "-")
    return " ".join(text.split()).casefold()


def _narration_at(script_data: dict[str, Any], location: str) -> str | None:
    script = script_data.get("script")

    if not isinstance(script, dict):
        return None

    if location in {
        "hook.narration",
        "introduction.narration",
        "conclusion.narration",
        "call_to_action.narration",
    }:
        block = script.get(location.split(".", 1)[0])
    else:
        match = MAIN_SECTION_LOCATION.fullmatch(location)

        if not match:
            return None

        sections = script.get("main_sections")

        if not isinstance(sections, list):
            return None

        index = int(match.group(1))

        if index >= len(sections):
            return None

        block = sections[index]

    if not isinstance(block, dict):
        return None

    narration = block.get("narration")
    return narration if isinstance(narration, str) else None


def validate_fact_qa_anchors(
    *,
    script_data: dict[str, Any],
    qa_data: dict[str, Any],
) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    anchored_count = 0
    unsupported = qa_data.get("unsupported_statements", [])

    if not isinstance(unsupported, list):
        return {
            "approved": False,
            "anchored_count": 0,
            "unsupported_statement_count": 0,
            "error_count": 1,
            "errors": [{"reason": "unsupported_statements_not_list"}],
        }

    for index, item in enumerate(unsupported):
        if not isinstance(item, dict):
            errors.append({
                "issue_index": index,
                "reason": "unsupported_statement_not_object",
            })
            continue

        location = str(item.get("location") or "").strip()
        statement = _strip_outer_quotes(item.get("statement"))
        narration = _narration_at(script_data, location)

        if narration is None:
            errors.append({
                "issue_index": index,
                "location": location,
                "reason": "location_not_found_in_current_script",
            })
            continue

        if not statement:
            errors.append({
                "issue_index": index,
                "location": location,
                "reason": "statement_missing",
            })
            continue

        if statement in narration or _normalize(statement) in _normalize(narration):
            anchored_count += 1
            continue

        errors.append({
            "issue_index": index,
            "location": location,
            "statement": statement,
            "reason": "statement_not_verbatim_in_current_narration",
        })

    return {
        "approved": not errors,
        "anchored_count": anchored_count,
        "unsupported_statement_count": len(unsupported),
        "error_count": len(errors),
        "errors": errors,
    }


def build_anchor_retry_prompt(
    *,
    base_prompt: str,
    validation: dict[str, Any],
) -> str:
    return (
        base_prompt
        + "\n\nFACT QA OUTPUT CONTRACT CORRECTION:\n"
        + "Your previous response reported unsupported statements that "
        + "were not copied verbatim from the current narration block. "
        + "Re-evaluate the exact SCRIPT above. For every unsupported "
        + "statement, copy one exact contiguous substring from the stated "
        + "location. Do not paraphrase, summarize, use ellipses, or refer "
        + "to any prior draft. If the current script no longer contains the "
        + "issue, omit it. Return the complete JSON object again.\n"
        + "ANCHORING_ERRORS:\n"
        + json.dumps(validation.get("errors", []), ensure_ascii=True, indent=2)
    )
