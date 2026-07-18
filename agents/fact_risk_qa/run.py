from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from jsonschema import validate
from openai import OpenAI


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.channel_content_policy import load_editorial_profile
from core.factuality import validate_script_claim_references
from core.video_run_context import (
    load_context,
    register_output,
    resolve_output,
    save_context,
    set_status,
)


DEFAULT_MODEL = "gpt-5.5"


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Required file not found: {path}")

    return json.loads(path.read_text(encoding="utf-8-sig"))


def relative_path(path: Path) -> str:
    return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Verify a script against the claims ledger and "
            "run factual and reputational risk review."
        )
    )
    parser.add_argument("--channel", default="rise_dossier")
    parser.add_argument("--video-id", required=True)
    parser.add_argument(
        "--model",
        default=os.getenv(
            "OPENAI_FACT_QA_MODEL",
            DEFAULT_MODEL,
        ),
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def build_prompt(
    context: dict[str, Any],
    profile: dict[str, Any],
    script_data: dict[str, Any],
    ledger_data: dict[str, Any],
) -> str:
    approved_claims = [
        item
        for item in ledger_data.get("claims", [])
        if item.get("verification_status") == "approved"
    ]

    return f"""
You are the Factual QA and Risk Review Agent for
{profile["display_name"]}.

Evaluate the complete documentary script against the approved
claims ledger. Do not add new facts and do not rewrite the script.

CHANNEL:
{profile["display_name"]}

TOPIC:
{context["topic_title"]}

APPROVED CLAIMS LEDGER:
{json.dumps(approved_claims, indent=2, ensure_ascii=True)}

SCRIPT:
{json.dumps(script_data["script"], indent=2, ensure_ascii=True)}

STRICT RULES:
- Every concrete factual statement must be supported by the claim IDs
  attached to its narration block.
- Reject any statement that goes beyond the wording or certainty of the
  approved ledger.
- Allegations must remain attributed and must never become established fact.
- Do not allow invented dialogue, motive, private conversation, quotation,
  legal conclusion, health claim, criminal implication, or exact number.
- Distinguish company failure, controversy, allegation, and proven wrongdoing.
- Reject misleading certainty or emotional language that changes the facts.
- Low-risk narrative transitions are allowed only when they add no new fact.
- factual_grounding_score must be 100 for approval.
- risk_compliance_score must be 100 for approval.
- Any unsupported statement or high-severity risk issue requires rejection.
- Return JSON only.
""".strip()


def call_model(
    prompt: str,
    model: str,
    schema: dict[str, Any],
) -> dict[str, Any]:
    client = OpenAI()
    response = client.responses.create(
        model=model,
        input=prompt,
        text={
            "format": {
                "type": "json_schema",
                "name": "rise_dossier_fact_risk_qa",
                "strict": True,
                "schema": schema,
            }
        },
    )

    if not response.output_text:
        raise ValueError(
            "Fact Risk QA returned an empty response."
        )

    return json.loads(response.output_text)


def save_output(
    output_dir: Path,
    filename: str,
    data: dict[str, Any],
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / filename
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    return path


def main() -> None:
    args = parse_args()
    channel = args.channel.lower()
    video_id = args.video_id.lower()

    load_dotenv(PROJECT_ROOT / ".env")

    context = load_context(
        channel=channel,
        video_id=video_id,
    )
    profile = load_editorial_profile(channel)
    script_path = resolve_output(
        context=context,
        key="script",
    )
    ledger_path = resolve_output(
        context=context,
        key="claims_ledger",
    )
    research_path = resolve_output(
        context=context,
        key="factual_research",
    )
    script_data = load_json(script_path)
    ledger_data = load_json(ledger_path)
    research_data = load_json(research_path)

    if ledger_data.get("status") != "approved":
        raise ValueError(
            "Claims ledger must be approved before Fact Risk QA."
        )

    deterministic = validate_script_claim_references(
        script_data=script_data,
        ledger_data=ledger_data,
    )

    print(f"CHANNEL: {channel}")
    print(f"VIDEO_CONTEXT_ID: {video_id}")
    print(f"RUN_ID: {context['run_id']}")
    print(f"SCRIPT_SOURCE: {relative_path(script_path)}")
    print(f"CLAIMS_LEDGER_SOURCE: {relative_path(ledger_path)}")
    print(f"FACTUAL_RESEARCH_SOURCE: {relative_path(research_path)}")
    print(
        "SCRIPT_CLAIM_REFERENCE_GATE: "
        f"{deterministic['status']}"
    )

    if args.dry_run:
        print("STATUS: fact_risk_qa_dry_run_ready")
        print("MODEL_CALLED: false")
        return

    if not deterministic["approved"]:
        raw = {
            "factual_grounding_score": 0,
            "risk_compliance_score": 0,
            "unsupported_statements": [
                {
                    "location": "script",
                    "statement": "",
                    "reason": error,
                    "suggested_action": (
                        "Regenerate the affected narration block "
                        "with approved claim IDs."
                    ),
                }
                for error in deterministic["errors"]
            ],
            "risk_issues": [],
            "approved_claim_ids": [],
            "summary": (
                "Deterministic claim-reference validation failed."
            ),
        }
    else:
        if not os.getenv("OPENAI_API_KEY"):
            raise ValueError("OpenAI API Key not found.")

        raw = call_model(
            prompt=build_prompt(
                context=context,
                profile=profile,
                script_data=script_data,
                ledger_data=ledger_data,
            ),
            model=args.model,
            schema=load_json(
                BASE_DIR / "payload_schema.json"
            ),
        )

    high_risk_issues = [
        item
        for item in raw["risk_issues"]
        if item["severity"] == "high"
    ]
    approved = (
        deterministic["approved"]
        and raw["factual_grounding_score"] == 100
        and raw["risk_compliance_score"] == 100
        and not raw["unsupported_statements"]
        and not high_risk_issues
    )
    status = "approved" if approved else "rejected"

    final_output = {
        "agent": "fact_risk_qa",
        "version": "1.0",
        "channel": channel,
        "video_id": video_id,
        "run_id": context["run_id"],
        "status": status,
        **raw,
        "deterministic_validation": deterministic,
        "metadata": {
            "model": args.model,
            "source_agents": [
                "factual_research",
                "claims_ledger",
                "script",
            ],
            "next_agent": "qa" if approved else "script",
        },
    }

    validate(
        instance=final_output,
        schema=load_json(BASE_DIR / "schema.json"),
    )

    output_dir = (
        BASE_DIR
        / "output"
        / channel
        / video_id
        / context["run_id"]
    )

    fact_qa = {
        "agent": "fact_qa",
        "version": "1.0",
        "channel": channel,
        "video_id": video_id,
        "run_id": context["run_id"],
        "status": status,
        "factual_grounding_score": raw[
            "factual_grounding_score"
        ],
        "unsupported_statements": raw[
            "unsupported_statements"
        ],
        "approved_claim_ids": raw[
            "approved_claim_ids"
        ],
        "deterministic_validation": deterministic,
        "source_reference": relative_path(research_path),
    }
    risk_review = {
        "agent": "risk_review",
        "version": "1.0",
        "channel": channel,
        "video_id": video_id,
        "run_id": context["run_id"],
        "status": status,
        "risk_compliance_score": raw[
            "risk_compliance_score"
        ],
        "risk_issues": raw["risk_issues"],
        "summary": raw["summary"],
    }

    fact_path = save_output(
        output_dir,
        "fact_qa.json",
        fact_qa,
    )
    risk_path = save_output(
        output_dir,
        "risk_review.json",
        risk_review,
    )
    combined_path = save_output(
        output_dir,
        "fact_risk_qa.json",
        final_output,
    )

    context = register_output(
        context=context,
        agent="fact_qa",
        reference=relative_path(fact_path),
        status=status,
    )
    context = register_output(
        context=context,
        agent="risk_review",
        reference=relative_path(risk_path),
        status=status,
    )
    context = register_output(
        context=context,
        agent="fact_risk_qa",
        reference=relative_path(combined_path),
        status=status,
    )
    context = set_status(
        context=context,
        status=(
            "fact_risk_qa_ready"
            if approved
            else "content_revision_required"
        ),
        next_agent="qa" if approved else "script",
    )
    save_context(context)

    print(f"FACT_QA_STATUS: {status}")
    print(f"RISK_REVIEW_STATUS: {status}")
    print(
        "FACTUAL_GROUNDING_SCORE: "
        f"{raw['factual_grounding_score']}"
    )
    print(
        "RISK_COMPLIANCE_SCORE: "
        f"{raw['risk_compliance_score']}"
    )
    print(
        "UNSUPPORTED_STATEMENT_COUNT: "
        f"{len(raw['unsupported_statements'])}"
    )
    print(f"HIGH_RISK_ISSUE_COUNT: {len(high_risk_issues)}")
    print(f"OUTPUT_SAVED: {relative_path(combined_path)}")


if __name__ == "__main__":
    main()
