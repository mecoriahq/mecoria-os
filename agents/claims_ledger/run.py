from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from jsonschema import validate


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.channel_content_policy import load_editorial_profile
from core.factuality import build_claims_ledger
from core.video_run_context import (
    load_context,
    register_output,
    resolve_output,
    save_context,
    set_status,
)


def load_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Required file not found: {path}")

    return json.loads(path.read_text(encoding="utf-8-sig"))


def relative_path(path: Path) -> str:
    return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a deterministic claims ledger from a "
            "source-backed factual research dossier."
        )
    )
    parser.add_argument("--channel", default="rise_dossier")
    parser.add_argument("--video-id", required=True)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    channel = args.channel.lower()
    video_id = args.video_id.lower()

    context = load_context(
        channel=channel,
        video_id=video_id,
    )
    profile = load_editorial_profile(channel)
    research_path = resolve_output(
        context=context,
        key="factual_research",
    )
    dossier = load_json(research_path)

    if dossier.get("status") != "approved":
        raise ValueError(
            "Factual research must be approved before claims ledger."
        )

    print(f"CHANNEL: {channel}")
    print(f"VIDEO_CONTEXT_ID: {video_id}")
    print(f"RUN_ID: {context['run_id']}")
    print(f"FACTUAL_RESEARCH_SOURCE: {relative_path(research_path)}")
    print(
        "HIGH_RISK_MINIMUM_SOURCES: "
        f"{profile['factuality']['minimum_sources_per_high_risk_claim']}"
    )
    print(
        "MINIMUM_APPROVED_CLAIMS: "
        f"{profile['factuality']['minimum_approved_claims_for_script']}"
    )
    print(
        "MINIMUM_CLAIM_COVERAGE_RATE: "
        f"{profile['factuality']['minimum_claim_coverage_rate']}"
    )

    if args.dry_run:
        print("STATUS: claims_ledger_dry_run_ready")
        return

    ledger = build_claims_ledger(
        dossier=dossier,
        minimum_sources_per_high_risk_claim=int(
            profile["factuality"][
                "minimum_sources_per_high_risk_claim"
            ]
        ),
        minimum_approved_claims=int(
            profile["factuality"][
                "minimum_approved_claims_for_script"
            ]
        ),
        minimum_coverage_rate=float(
            profile["factuality"][
                "minimum_claim_coverage_rate"
            ]
        ),
    )

    final_output = {
        "agent": "claims_ledger",
        "version": "1.1",
        "channel": channel,
        "video_id": video_id,
        "run_id": context["run_id"],
        **ledger,
        "metadata": {
            "source_agent": "factual_research",
            "source_reference": relative_path(research_path),
            "next_agent": (
                "script"
                if ledger["status"] == "approved"
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
    output_path = output_dir / "claims_ledger.json"
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
        agent="claims_ledger",
        reference=relative_path(output_path),
        status=final_output["status"],
    )
    context = set_status(
        context=context,
        status=(
            "claims_ledger_ready"
            if approved
            else "factual_research_revision_required"
        ),
        next_agent=(
            "script"
            if approved
            else "factual_research"
        ),
    )

    save_context(context)

    print(f"CLAIMS_LEDGER_STATUS: {final_output['status']}")
    print(
        "TOTAL_CLAIM_COUNT: "
        f"{final_output['summary']['total_claim_count']}"
    )
    print(
        "BLOCKED_CLAIM_COUNT: "
        f"{final_output['summary']['blocked_claim_count']}"
    )
    print(
        "QUARANTINED_CLAIM_COUNT: "
        f"{final_output['summary']['quarantined_claim_count']}"
    )
    print(
        "CONTINUATION_ELIGIBLE: "
        f"{str(final_output['summary']['continuation_eligible']).lower()}"
    )
    print(f"OUTPUT_SAVED: {relative_path(output_path)}")


if __name__ == "__main__":
    main()
