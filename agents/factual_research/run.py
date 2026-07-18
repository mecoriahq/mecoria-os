from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from jsonschema import validate
from openai import OpenAI


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.channel_content_policy import (
    factual_pipeline_required,
    load_editorial_profile,
)
from core.factuality import (
    collect_urls_from_response_payload,
    response_used_web_search,
    validate_research_dossier,
)
from core.video_run_context import (
    assert_topic_approved,
    load_context,
    register_output,
    resolve_source,
    save_context,
    set_status,
)


DEFAULT_CHANNEL = "rise_dossier"
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
            "Build a source-backed factual research dossier "
            "for a locked Mecoria Media video context."
        )
    )
    parser.add_argument("--channel", default=DEFAULT_CHANNEL)
    parser.add_argument("--video-id", required=True)
    parser.add_argument(
        "--model",
        default=os.getenv(
            "OPENAI_FACTUAL_RESEARCH_MODEL",
            DEFAULT_MODEL,
        ),
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def build_prompt(
    context: dict[str, Any],
    selected_idea: dict[str, Any],
    profile: dict[str, Any],
) -> str:
    factuality = profile["factuality"]
    topic_strategy = profile["topic_strategy"]

    return f"""
You are the Factual Research Agent for {profile["display_name"]}.

Research the exact approved documentary topic below using web search.
The output will become the only factual source pack available to the
script agent.

CHANNEL:
{profile["display_name"]}

APPROVED TOPIC:
{context["topic_title"]}

SELECTED IDEA:
{json.dumps(selected_idea, indent=2, ensure_ascii=True)}

CHANNEL PROMISE:
{topic_strategy["channel_promise"]}

RESEARCH REQUIREMENTS:
- Use at least {factuality["minimum_sources"]} independent sources.
- Include at least {factuality["minimum_primary_sources"]} primary sources.
- Prefer this source order:
{json.dumps(factuality["source_quality_order"], indent=2)}
- Do not use these as evidence:
{json.dumps(factuality["blocked_source_types"], indent=2)}
- Every timeline event and turning point must cite source IDs.
- Every candidate claim must cite source IDs.
- Separate verified facts, quotations, allegations, interpretations,
  and legal conclusions.
- High-risk allegations must have at least
  {factuality["minimum_sources_per_high_risk_claim"]} independent sources.
- Do not infer private motives.
- Do not invent quotations, dates, numbers, events, or URLs.
- Use public, attributable information only.
- Record unresolved or disputed questions instead of pretending certainty.
- The source URL in the JSON must be the exact page used by web search.
- Use stable IDs: S01, S02... and C01, C02...
- Write in English.
- Return JSON only.
""".strip()


def call_research_model(
    prompt: str,
    model: str,
    payload_schema: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    client = OpenAI()

    response = client.responses.create(
        model=model,
        include=[
            "web_search_call.action.sources",
        ],
        tools=[
            {
                "type": "web_search",
                "search_context_size": "high",
            }
        ],
        input=prompt,
        text={
            "format": {
                "type": "json_schema",
                "name": "rise_dossier_factual_research",
                "strict": True,
                "schema": payload_schema,
            }
        },
    )

    text = response.output_text

    if not text:
        raise ValueError(
            "Factual Research Agent returned an empty response."
        )

    payload = json.loads(text)
    response_payload = response.model_dump()
    return payload, response_payload


def main() -> None:
    args = parse_args()
    channel = args.channel.lower()
    video_id = args.video_id.lower()

    load_dotenv(PROJECT_ROOT / ".env")

    context = load_context(
        channel=channel,
        video_id=video_id,
    )
    assert_topic_approved(context)

    profile = load_editorial_profile(channel)

    if not factual_pipeline_required(profile):
        raise ValueError(
            f"Factual research is not required for channel: {channel}"
        )

    selection_path = resolve_source(
        context=context,
        key="idea_selection",
    )
    selection = load_json(selection_path)
    selected_idea = selection.get("selected_idea")

    if not isinstance(selected_idea, dict):
        raise ValueError(
            "Idea selection has no selected_idea object."
        )

    print(f"CHANNEL: {channel}")
    print(f"VIDEO_CONTEXT_ID: {video_id}")
    print(f"RUN_ID: {context['run_id']}")
    print(f"TOPIC: {context['topic_title']}")
    print(f"IDEA_SELECTION_SOURCE: {relative_path(selection_path)}")
    print("WEB_SEARCH_REQUIRED: true")
    print(
        "MINIMUM_SOURCES: "
        f"{profile['factuality']['minimum_sources']}"
    )
    print(
        "MINIMUM_PRIMARY_SOURCES: "
        f"{profile['factuality']['minimum_primary_sources']}"
    )

    if args.dry_run:
        print("STATUS: factual_research_dry_run_ready")
        print("WEB_SEARCH_CALLED: false")
        return

    if not os.getenv("OPENAI_API_KEY"):
        raise ValueError("OpenAI API Key not found.")

    payload_schema = load_json(
        BASE_DIR / "payload_schema.json"
    )
    prompt = build_prompt(
        context=context,
        selected_idea=selected_idea,
        profile=profile,
    )
    payload, response_payload = call_research_model(
        prompt=prompt,
        model=args.model,
        payload_schema=payload_schema,
    )

    if not response_used_web_search(response_payload):
        raise ValueError(
            "Factual research completed without a web search call."
        )

    cited_urls = collect_urls_from_response_payload(
        response_payload
    )
    validation = validate_research_dossier(
        dossier=payload,
        minimum_sources=int(
            profile["factuality"]["minimum_sources"]
        ),
        minimum_primary_sources=int(
            profile["factuality"][
                "minimum_primary_sources"
            ]
        ),
        cited_urls=cited_urls,
    )

    final_output = {
        "agent": "factual_research",
        "version": "1.0",
        "channel": channel,
        "video_id": video_id,
        "run_id": context["run_id"],
        "status": (
            "approved"
            if validation["approved"]
            else "rejected"
        ),
        **payload,
        "validation": validation,
        "metadata": {
            "model": args.model,
            "web_search_used": True,
            "web_search_cited_url_count": len(cited_urls),
            "researched_at": datetime.now(
                timezone.utc
            ).isoformat(),
            "next_agent": (
                "claims_ledger"
                if validation["approved"]
                else None
            ),
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
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "research_dossier.json"
    output_path.write_text(
        json.dumps(
            final_output,
            indent=2,
            ensure_ascii=True,
        )
        + "\n",
        encoding="utf-8",
    )

    approved = final_output["status"] == "approved"
    context = register_output(
        context=context,
        agent="factual_research",
        reference=relative_path(output_path),
        status=final_output["status"],
    )
    context = set_status(
        context=context,
        status=(
            "factual_research_ready"
            if approved
            else "factual_research_revision_required"
        ),
        next_agent=(
            "claims_ledger"
            if approved
            else "factual_research"
        ),
    )
    save_context(context)

    print(
        "FACTUAL_RESEARCH_STATUS: "
        f"{final_output['status']}"
    )
    print(f"SOURCE_COUNT: {validation['source_count']}")
    print(
        "PRIMARY_SOURCE_COUNT: "
        f"{validation['primary_source_count']}"
    )
    print(f"CLAIM_COUNT: {validation['claim_count']}")
    print(f"OUTPUT_SAVED: {relative_path(output_path)}")


if __name__ == "__main__":
    main()
