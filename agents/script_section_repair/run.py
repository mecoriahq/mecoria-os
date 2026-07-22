from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from jsonschema import ValidationError, validate
from openai import OpenAI


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.channel_content_policy import (
    load_editorial_profile,
)
from core.content_stabilization import (
    apply_safe_word_budget_recovery,
    word_budget_report,
)
from core.factuality import (
    validate_script_claim_references,
)
from core.script_candidate_manager import (
    extract_repair_targets,
    get_script_block,
    merge_script_repairs,
    resolve_repair_targets_for_script,
)
from core.script_preflight import (
    assert_script_preflight,
)
from core.model_pause import record_model_retry_pause
from core.openai_resilience import (
    OpenAIRetryExhausted,
    RetryPolicy,
    call_with_retry,
    require_nonempty_text,
)
from core.video_run_context import (
    load_context,
    register_output,
    resolve_output,
    resolve_source,
    save_context,
    set_status,
)


DEFAULT_MODEL = "gpt-5.5"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Repair only the factual narration blocks rejected "
            "by Fact Risk QA."
        )
    )
    parser.add_argument(
        "--channel",
        default="rise_dossier",
    )
    parser.add_argument(
        "--video-id",
        required=True,
    )
    parser.add_argument(
        "--model",
        default=os.getenv(
            "OPENAI_SCRIPT_REPAIR_MODEL",
            DEFAULT_MODEL,
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
    )
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(
            f"Required file not found: {path}"
        )

    return json.loads(
        path.read_text(encoding="utf-8-sig")
    )


def relative_path(path: Path) -> str:
    return str(
        path.relative_to(PROJECT_ROOT)
    ).replace("\\", "/")


def approved_claims(
    ledger_data: dict[str, Any],
) -> list[dict[str, Any]]:
    return [
        item
        for item in ledger_data.get("claims", [])
        if item.get("verification_status") == "approved"
    ]


def build_prompt(
    *,
    context: dict[str, Any],
    profile: dict[str, Any],
    script_data: dict[str, Any],
    qa_data: dict[str, Any],
    ledger_data: dict[str, Any],
    repair_targets: list[dict[str, Any]],
    repair_mode: str,
) -> str:
    target_payload = []

    for target in repair_targets:
        location = target["location"]
        block = get_script_block(
            script_data,
            location,
        )
        narration = str(
            block.get("narration", "")
        )
        target_payload.append({
            "location": location,
            "current_block": block,
            "current_word_count": len(
                narration.split()
            ),
            "issues": target["issues"],
        })

    budget = word_budget_report(
        script_data=script_data,
        profile=profile,
    )

    mode_rules = (
        """
EDITORIAL REPAIR MODE:
- Improve only the editorial objectives listed for each block.
- Preserve every factual sentence that already passed Fact/Risk QA.
- Do not change title, section order, chronology, or non-target blocks.
- Improve hook tension, hook/intro distinction, specificity, narrative
  connection, or repetition only through approved claim detail.
""".strip()
        if repair_mode == "editorial"
        else """
FACT/RISK REPAIR MODE:
- Remove every flagged unsupported statement and equivalent implication.
- Preserve the block's factual scope and attribution.
""".strip()
    )

    return f"""
You are the Script Section Repair Agent for
{profile["display_name"]}.

Repair ONLY the narration blocks listed below. Do not rewrite or
return any other part of the script.

CHANNEL:
{profile["display_name"]}

TOPIC:
{context["topic_title"]}

REPAIR ATTEMPT:
{context.get("quality_gates", {}).get(
    "fact_risk_section_repair_count",
    0,
)}

APPROVED CLAIMS:
{json.dumps(
    approved_claims(ledger_data),
    ensure_ascii=True,
    indent=2,
)}

CURRENT TARGET BLOCKS AND QA ISSUES:
{json.dumps(
    target_payload,
    ensure_ascii=True,
    indent=2,
)}

{mode_rules}

STRICT REPAIR RULES:
- Return exactly one repair for every requested location, in the same
  order. Return no additional locations.
- Rewrite only narration and claim_ids for the requested block.
- Preserve the block's function in the chronology and narrative spine.
- Remove every flagged statement and every equivalent unsupported
  implication.
- Use only approved claims from the ledger.
- Every factual sentence must stay within the wording, scope,
  attribution, and certainty of claim IDs attached to that block.
- Allegations must remain explicitly attributed.
- Do not add general medical, legal, scientific, startup, business,
  psychological, or public-memory explanation unless it is an approved
  claim.
- Do not add motive, secrecy, collapse, myth, credibility effects,
  causation, investor impact, or legal conclusions beyond approved
  wording.
- Preserve approximately the current narration length for each block.
  Keep each repaired block between 90 and 115 percent of its current
  word count unless removing unsupported language requires a smaller
  block.
- The current full script has {budget["current_word_count"]} narration
  words. The production target is {budget["minimum_word_count"]} to
  {budget["maximum_word_count"]}. Do not shorten the repaired script
  below the production minimum. If factual cleanup removes words,
  preserve equivalent approved detail elsewhere inside the requested
  blocks.
- If the current block needs a claim that is approved but not currently
  attached, add that approved claim ID.
- Do not use quarantined or blocked claims.
- Do not mention the QA process, claims ledger, sources, or production
  system in the narration.
- Return JSON only.
""".strip()


def call_model(
    *,
    prompt: str,
    model: str,
    schema: dict[str, Any],
) -> dict[str, Any]:
    client = OpenAI()

    def operation() -> dict[str, Any]:
        response = client.responses.create(
            model=model,
            input=prompt,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "rise_dossier_script_section_repair",
                    "strict": True,
                    "schema": schema,
                }
            },
        )
        output_text = require_nonempty_text(
            response.output_text,
            label="Script Section Repair",
        )
        return json.loads(output_text)

    return call_with_retry(
        operation,
        operation_name="script_section_repair",
        policy=RetryPolicy(max_attempts=3),
        on_retry=lambda attempt, maximum, error, delay: print(
            "OPENAI_RETRY: "
            f"script_section_repair attempt={attempt + 1}/{maximum} "
            f"delay={delay}s error={type(error).__name__}"
        ),
    )


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

    sources = context.get("sources", {})
    repair_mode = "fact_risk"
    source_key = "fact_risk_section_repair_brief"

    if "editorial_section_repair_brief" in sources:
        repair_mode = "editorial"
        source_key = "editorial_section_repair_brief"
        brief_path = resolve_source(
            context=context,
            key=source_key,
        )
        brief_data = load_json(brief_path)
        qa_data = brief_data["editorial_qa"]
        attempt = int(brief_data["attempt"])
        extracted_targets = brief_data.get(
            "repair_targets",
            [],
        )
    elif source_key in sources:
        brief_path = resolve_source(
            context=context,
            key=source_key,
        )
        brief_data = load_json(brief_path)
        qa_data = brief_data["fact_risk_qa"]
        attempt = int(brief_data["attempt"])
        extracted_targets = extract_repair_targets(
            qa_data
        )
    else:
        qa_path = resolve_output(
            context=context,
            key="fact_risk_qa",
        )
        qa_data = load_json(qa_path)
        attempt = int(
            context.get(
                "quality_gates",
                {},
            ).get(
                "fact_risk_section_repair_count",
                1,
            )
        )
        extracted_targets = extract_repair_targets(
            qa_data
        )

    script_data = load_json(script_path)
    ledger_data = load_json(ledger_path)
    target_resolution = (
        resolve_repair_targets_for_script(
            script_data=script_data,
            repair_targets=extracted_targets,
        )
    )
    repair_targets = target_resolution["targets"]
    stale_issues = target_resolution["stale_issues"]
    relocated_issues = target_resolution[
        "relocated_issues"
    ]

    print(
        "STALE_REPAIR_TARGET_COUNT: "
        f"{len(stale_issues)}"
    )
    print(
        "RELOCATED_REPAIR_TARGET_COUNT: "
        f"{len(relocated_issues)}"
    )

    if not repair_targets:
        context.get("sources", {}).pop(
            source_key,
            None,
        )
        if repair_mode == "editorial":
            context = set_status(
                context=context,
                status="founder_editorial_review_required",
                next_agent="founder_editorial_review",
            )
        else:
            context = set_status(
                context=context,
                status="script_repaired",
                next_agent="fact_risk_qa",
            )
        save_context(context)
        print(
            "SCRIPT_SECTION_REPAIR_STATUS: "
            "no_actionable_targets"
        )
        print("MODEL_CALLED: false")
        return

    target_locations = [
        item["location"]
        for item in repair_targets
    ]

    print(f"CHANNEL: {channel}")
    print(f"VIDEO_CONTEXT_ID: {video_id}")
    print(f"RUN_ID: {context['run_id']}")
    print(f"REPAIR_MODE: {repair_mode}")
    print(f"REPAIR_ATTEMPT: {attempt}")
    print(
        "TARGET_LOCATION_COUNT: "
        f"{len(target_locations)}"
    )
    print(
        "TARGET_LOCATIONS: "
        + ",".join(target_locations)
    )

    if args.dry_run:
        print("STATUS: script_section_repair_dry_run_ready")
        print("MODEL_CALLED: false")
        return

    if not os.getenv("OPENAI_API_KEY"):
        raise ValueError("OpenAI API Key not found.")

    try:
        raw = call_model(
            prompt=build_prompt(
                context=context,
                profile=profile,
                script_data=script_data,
                qa_data=qa_data,
                ledger_data=ledger_data,
                repair_targets=repair_targets,
                repair_mode=repair_mode,
            ),
            model=args.model,
            schema=load_json(
                BASE_DIR / "payload_schema.json"
            ),
        )
    except OpenAIRetryExhausted as error:
        record_model_retry_pause(
            context=context,
            agent="script_section_repair",
            error=error,
        )
        return
    try:
        validate(
            instance=raw,
            schema=load_json(
                BASE_DIR / "payload_schema.json"
            ),
        )

        repaired_script = merge_script_repairs(
            script_data=script_data,
            repairs=raw["repairs"],
            required_locations=target_locations,
        )
        (
            repaired_script,
            word_budget_recovery,
        ) = apply_safe_word_budget_recovery(
            script_data=repaired_script,
            profile=profile,
        )
        deterministic = (
            validate_script_claim_references(
                script_data=repaired_script,
                ledger_data=ledger_data,
            )
        )

        if not deterministic["approved"]:
            raise ValueError(
                "Section repair failed deterministic claim "
                "validation: "
                + "; ".join(
                    deterministic["errors"]
                )
            )

        script_policy = profile["script"]
        gates = context.get("quality_gates", {})
        preflight = assert_script_preflight(
            script_data=repaired_script,
            target_minimum=int(
                gates.get(
                    "target_script_word_count_min",
                    script_policy["word_count_min"],
                )
            ),
            target_maximum=int(
                gates.get(
                    "target_script_word_count_max",
                    script_policy["word_count_max"],
                )
            ),
            absolute_floor=int(
                script_policy.get(
                    "pre_audio_word_floor",
                    1100,
                )
            ),
            minimum_ratio=float(
                script_policy.get(
                    "pre_audio_minimum_ratio",
                    0.85,
                )
            ),
            audio_duration_authoritative=bool(
                script_policy.get(
                    "audio_duration_authoritative",
                    True,
                )
            ),
        )
        repaired_script.setdefault(
            "quality",
            {},
        )["pre_audio_gate"] = preflight
        repaired_script["quality"][
            "actual_audio_duration_pending"
        ] = True

        validate(
            instance=repaired_script,
            schema=load_json(
                PROJECT_ROOT
                / "agents"
                / "script"
                / "schema.json"
            ),
        )
    except (
        ValidationError,
        ValueError,
        KeyError,
        IndexError,
        TypeError,
    ) as error:
        record_model_retry_pause(
            context=context,
            agent="script_section_repair",
            error=error,
        )
        print(
            "SECTION_REPAIR_VALIDATION_PAUSE: true"
        )
        return

    canonical_script_path = (
        PROJECT_ROOT
        / "agents"
        / "script"
        / "output"
        / channel
        / video_id
        / context["run_id"]
        / "script.json"
    )
    canonical_script_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    canonical_script_path.write_text(
        json.dumps(
            repaired_script,
            indent=2,
            ensure_ascii=True,
        )
        + "\n",
        encoding="utf-8",
    )

    output_dir = (
        BASE_DIR
        / "output"
        / channel
        / video_id
        / context["run_id"]
        / f"attempt_{attempt:02d}"
    )
    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )
    repair_path = output_dir / "repair.json"
    final_output = {
        "agent": "script_section_repair",
        "version": "1.1",
        "repair_mode": repair_mode,
        "channel": channel,
        "video_id": video_id,
        "run_id": context["run_id"],
        "status": "repair_ready",
        "attempt": attempt,
        "target_locations": target_locations,
        "repairs": raw["repairs"],
        "summary": raw["summary"],
        "script_reference": relative_path(
            canonical_script_path
        ),
        "quality": {
            "deterministic_claim_validation": (
                deterministic
            ),
            "pre_audio_gate": preflight,
            "automatic_word_budget_recovery": (
                word_budget_recovery
            ),
        },
        "metadata": {
            "model": args.model,
            "source_agents": (
                [
                    "script",
                    "claims_ledger",
                    "qa",
                ]
                if repair_mode == "editorial"
                else [
                    "script",
                    "claims_ledger",
                    "fact_risk_qa",
                ]
            ),
            "next_agent": "seo",
        },
    }
    validate(
        instance=final_output,
        schema=load_json(
            BASE_DIR / "schema.json"
        ),
    )
    repair_path.write_text(
        json.dumps(
            final_output,
            indent=2,
            ensure_ascii=True,
        )
        + "\n",
        encoding="utf-8",
    )

    context = register_output(
        context=context,
        agent="script",
        reference=relative_path(
            canonical_script_path
        ),
        status="script_ready",
    )
    context = register_output(
        context=context,
        agent="script_section_repair",
        reference=relative_path(repair_path),
        status="repair_ready",
    )
    context.get("sources", {}).pop(
        source_key,
        None,
    )
    context = set_status(
        context=context,
        status="script_repaired",
        next_agent="seo",
    )
    save_context(context)

    print("SCRIPT_SECTION_REPAIR_STATUS: repair_ready")
    print(
        "REPAIRED_LOCATION_COUNT: "
        f"{len(target_locations)}"
    )
    print(
        "SCRIPT_PREFLIGHT_STATUS: "
        f"{preflight['status']}"
    )
    print(
        "SCRIPT_WORD_COUNT: "
        f"{preflight['word_count']}"
    )
    print(
        "AUTOMATIC_WORD_BUDGET_RECOVERY: "
        f"{str(word_budget_recovery.get('applied', False)).lower()}"
    )
    print(
        "OUTPUT_SAVED: "
        f"{relative_path(repair_path)}"
    )


if __name__ == "__main__":
    main()
