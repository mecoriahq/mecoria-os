from __future__ import annotations

import re
from urllib.parse import urlparse
from typing import Any


SOURCE_ID_PATTERN = re.compile(r"^S\d{2,}$")
CLAIM_ID_PATTERN = re.compile(r"^C\d{2,}$")

HIGH_RISK_CLAIM_TYPES = {
    "criminal_allegation",
    "fraud_allegation",
    "misconduct_allegation",
    "private_motive",
    "health_claim",
    "legal_conclusion",
}

ATTRIBUTION_REQUIRED_TYPES = {
    "allegation",
    "criminal_allegation",
    "fraud_allegation",
    "misconduct_allegation",
    "quote",
    "interpretation",
    "private_motive",
    "legal_conclusion",
}


def normalize_url(value: str) -> str:
    url = str(value).strip()
    parsed = urlparse(url)

    if parsed.scheme not in {"http", "https"}:
        raise ValueError(f"Source URL must use http or https: {url}")

    if not parsed.netloc:
        raise ValueError(f"Source URL is missing a host: {url}")

    return url


def source_map(dossier: dict[str, Any]) -> dict[str, dict[str, Any]]:
    sources = dossier.get("sources", [])

    if not isinstance(sources, list):
        raise TypeError("Research dossier sources must be a list.")

    result: dict[str, dict[str, Any]] = {}

    for source in sources:
        source_id = str(source.get("source_id", "")).strip()

        if not SOURCE_ID_PATTERN.fullmatch(source_id):
            raise ValueError(f"Invalid source_id: {source_id}")

        if source_id in result:
            raise ValueError(f"Duplicate source_id: {source_id}")

        normalized = dict(source)
        normalized["url"] = normalize_url(
            str(source.get("url", ""))
        )
        result[source_id] = normalized

    return result


def validate_research_dossier(
    dossier: dict[str, Any],
    minimum_sources: int,
    minimum_primary_sources: int,
    cited_urls: set[str] | None = None,
) -> dict[str, Any]:
    sources = source_map(dossier)
    claims = dossier.get("candidate_claims", [])

    if not isinstance(claims, list):
        raise TypeError("candidate_claims must be a list.")

    primary_count = sum(
        1
        for source in sources.values()
        if source.get("source_type") == "primary"
    )

    errors: list[str] = []

    if len(sources) < int(minimum_sources):
        errors.append(
            f"source_count={len(sources)} minimum={minimum_sources}"
        )

    if primary_count < int(minimum_primary_sources):
        errors.append(
            "primary_source_count="
            f"{primary_count} minimum={minimum_primary_sources}"
        )

    seen_claim_ids: set[str] = set()

    for claim in claims:
        claim_id = str(claim.get("claim_id", "")).strip()

        if not CLAIM_ID_PATTERN.fullmatch(claim_id):
            errors.append(f"invalid_claim_id={claim_id}")
            continue

        if claim_id in seen_claim_ids:
            errors.append(f"duplicate_claim_id={claim_id}")
            continue

        seen_claim_ids.add(claim_id)
        claim_sources = claim.get("source_ids", [])

        if not isinstance(claim_sources, list) or not claim_sources:
            errors.append(f"claim_without_sources={claim_id}")
            continue

        unknown = sorted(
            set(map(str, claim_sources)) - set(sources)
        )

        if unknown:
            errors.append(
                f"claim_unknown_sources={claim_id}:{','.join(unknown)}"
            )

    if cited_urls is not None:
        normalized_cited = {
            normalize_url(url)
            for url in cited_urls
        }

        uncited = sorted(
            source["url"]
            for source in sources.values()
            if source["url"] not in normalized_cited
        )

        if uncited:
            errors.append(
                "sources_not_confirmed_by_web_search="
                + ",".join(uncited)
            )

    return {
        "approved": not errors,
        "status": "pass" if not errors else "fail",
        "source_count": len(sources),
        "primary_source_count": primary_count,
        "claim_count": len(claims),
        "errors": errors,
    }


def build_claims_ledger(
    dossier: dict[str, Any],
    minimum_sources_per_high_risk_claim: int,
) -> dict[str, Any]:
    sources = source_map(dossier)
    ledger: list[dict[str, Any]] = []
    blocked_count = 0

    for candidate in dossier.get("candidate_claims", []):
        claim_id = str(candidate["claim_id"])
        claim_type = str(
            candidate.get("claim_type", "fact")
        )
        sensitivity = str(
            candidate.get("sensitivity", "low")
        )
        source_ids = list(dict.fromkeys(
            map(str, candidate.get("source_ids", []))
        ))
        source_records = [
            sources[source_id]
            for source_id in source_ids
            if source_id in sources
        ]
        primary_count = sum(
            1
            for source in source_records
            if source.get("source_type") == "primary"
        )
        high_risk = (
            sensitivity == "high"
            or claim_type in HIGH_RISK_CLAIM_TYPES
        )
        minimum_sources = (
            int(minimum_sources_per_high_risk_claim)
            if high_risk
            else 1
        )
        reasons: list[str] = []

        if len(source_records) < minimum_sources:
            reasons.append(
                "insufficient_independent_sources"
            )

        if claim_type == "quote" and primary_count < 1:
            reasons.append(
                "quote_requires_primary_source"
            )

        if any(
            source.get("reliability") == "low"
            for source in source_records
        ):
            reasons.append("low_reliability_source")

        status = "blocked" if reasons else "approved"

        if status == "blocked":
            blocked_count += 1

        attribution_required = (
            high_risk
            or claim_type in ATTRIBUTION_REQUIRED_TYPES
        )
        allowed_language = (
            "Use explicit attribution and cautious wording."
            if attribution_required
            else "State directly without adding unsupported detail."
        )

        ledger.append({
            "claim_id": claim_id,
            "claim": str(candidate.get("claim", "")).strip(),
            "claim_type": claim_type,
            "sensitivity": sensitivity,
            "source_ids": source_ids,
            "source_count": len(source_records),
            "primary_source_count": primary_count,
            "high_risk": high_risk,
            "attribution_required": attribution_required,
            "verification_status": status,
            "blocked_reasons": reasons,
            "allowed_language": allowed_language,
            "prohibited_language": (
                "Do not intensify certainty, infer private motive, "
                "or convert an allegation into an established fact."
            ),
        })

    approved_count = len(ledger) - blocked_count

    return {
        "status": (
            "approved"
            if ledger and blocked_count == 0
            else "rejected"
        ),
        "claims": ledger,
        "summary": {
            "total_claim_count": len(ledger),
            "approved_claim_count": approved_count,
            "blocked_claim_count": blocked_count,
            "coverage_rate": (
                round(approved_count / len(ledger), 4)
                if ledger
                else 0.0
            ),
        },
    }


def collect_script_claim_ids(
    script_data: dict[str, Any]
) -> dict[str, list[str]]:
    script = script_data.get("script", script_data)
    result: dict[str, list[str]] = {}

    for key in (
        "hook",
        "introduction",
        "conclusion",
        "call_to_action",
    ):
        block = script.get(key, {})
        result[key] = list(
            dict.fromkeys(map(str, block.get("claim_ids", [])))
        ) if isinstance(block, dict) else []

    for index, section in enumerate(
        script.get("main_sections", []),
        start=1,
    ):
        result[f"main_sections[{index}]"] = list(
            dict.fromkeys(
                map(str, section.get("claim_ids", []))
            )
        )

    return result


def validate_script_claim_references(
    script_data: dict[str, Any],
    ledger_data: dict[str, Any],
) -> dict[str, Any]:
    claims = {
        str(item["claim_id"]): item
        for item in ledger_data.get("claims", [])
    }
    references = collect_script_claim_ids(script_data)
    errors: list[str] = []
    used: set[str] = set()

    for location, claim_ids in references.items():
        narration = (
            script_data.get("script", script_data)
            .get(location, {})
        )

        if location.startswith("main_sections["):
            index = int(
                location.split("[", 1)[1].split("]", 1)[0]
            ) - 1
            sections = (
                script_data.get("script", script_data)
                .get("main_sections", [])
            )
            narration_text = str(
                sections[index].get("narration", "")
            ) if index < len(sections) else ""
        elif isinstance(narration, dict):
            narration_text = str(
                narration.get("narration", "")
            )
        else:
            narration_text = ""

        if (
            location != "call_to_action"
            and narration_text.strip()
            and not claim_ids
        ):
            errors.append(
                f"missing_claim_ids={location}"
            )

        for claim_id in claim_ids:
            used.add(claim_id)

            if claim_id not in claims:
                errors.append(
                    f"unknown_claim_id={location}:{claim_id}"
                )
                continue

            if (
                claims[claim_id].get("verification_status")
                != "approved"
            ):
                errors.append(
                    f"blocked_claim_used={location}:{claim_id}"
                )

    return {
        "approved": not errors,
        "status": "pass" if not errors else "fail",
        "used_claim_ids": sorted(used),
        "location_count": len(references),
        "errors": errors,
    }


def collect_urls_from_response_payload(
    payload: Any,
) -> set[str]:
    urls: set[str] = set()

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            value_type = str(value.get("type", ""))

            if (
                value_type in {
                    "url_citation",
                    "web_search_call",
                }
                or "url" in value
            ):
                raw_url = value.get("url")

                if isinstance(raw_url, str):
                    try:
                        urls.add(normalize_url(raw_url))
                    except ValueError:
                        pass

            for item in value.values():
                visit(item)

        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(payload)
    return urls


def response_used_web_search(payload: Any) -> bool:
    found = False

    def visit(value: Any) -> None:
        nonlocal found

        if found:
            return

        if isinstance(value, dict):
            if value.get("type") == "web_search_call":
                found = True
                return

            for item in value.values():
                visit(item)

        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(payload)
    return found
