import argparse
import json
from pathlib import Path

from dotenv import load_dotenv
from jsonschema import validate

from output import save_output


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent.parent

DEFAULT_CHANNEL = "hiddenova"


INTERNAL_METHODS = {
    "internal_graphic",
    "simple_text_overlay"
}

MANUAL_METHODS = {
    "manual_edit"
}

STOCK_METHODS = {
    "licensed_stock"
}

AI_METHODS = {
    "ai_generated"
}


def load_json(file_path: Path) -> dict:
    if not file_path.exists():
        raise FileNotFoundError(f"Required file not found: {file_path}")

    return json.loads(file_path.read_text(encoding="utf-8"))


def load_schema() -> dict:
    return load_json(BASE_DIR / "schema.json")


def get_visual_asset_production_latest_path(channel: str) -> Path:
    return PROJECT_ROOT / "agents" / "visual_asset_production" / "output" / channel.lower() / "latest.json"


def get_relative_path(path: Path) -> str:
    return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")


def classify_asset(asset: dict) -> tuple[str, str, str]:
    production_method = asset["production_method"]

    if production_method in INTERNAL_METHODS:
        return (
            "ready_for_internal_production",
            "internal",
            "Can be produced inside Mecoria using graphics, diagrams, text overlay, or editing templates."
        )

    if production_method in MANUAL_METHODS:
        return (
            "needs_manual_capture",
            "manual",
            "Requires original/staged footage capture or manual edit preparation before use."
        )

    if production_method in STOCK_METHODS:
        return (
            "needs_stock_sourcing",
            "stock",
            "Requires licensed stock footage sourcing and license review before public use."
        )

    if production_method in AI_METHODS:
        return (
            "ready_for_ai_generation",
            "ai",
            "Can be generated with AI image/video tools after prompt QA."
        )

    return (
        "needs_review",
        "review",
        "Production method is unknown or unsupported and needs manual review."
    )


def queue_priority(asset: dict, first_assets: list[str]) -> tuple[int, int, str]:
    first_rank = first_assets.index(asset["asset_id"]) if asset["asset_id"] in first_assets else 999

    priority_rank = {
        "high": 1,
        "medium": 2,
        "low": 3
    }.get(asset["priority"], 9)

    return (first_rank, priority_rank, asset["asset_id"])


def build_acquisition_decisions(production_data: dict) -> list[dict]:
    first_assets = production_data["production_manifest"]["first_assets_to_create"]

    decisions = []

    for asset in production_data["production_manifest"]["assets"]:
        acquisition_status, acquisition_lane, reason = classify_asset(asset)

        is_first_build = asset["asset_id"] in first_assets

        decisions.append({
            "asset_id": asset["asset_id"],
            "asset_type": asset["asset_type"],
            "priority": asset["priority"],
            "production_method": asset["production_method"],
            "folder": asset["folder"],
            "acquisition_status": acquisition_status,
            "acquisition_lane": acquisition_lane,
            "is_first_build": is_first_build,
            "decision_reason": reason,
            "next_action": get_next_action(
                acquisition_status=acquisition_status,
                asset=asset
            )
        })

    return sorted(
        decisions,
        key=lambda item: queue_priority(item, first_assets)
    )


def get_next_action(acquisition_status: str, asset: dict) -> str:
    if acquisition_status == "ready_for_internal_production":
        return "Create the internal graphic, diagram, map animation, or text overlay from the asset brief files."

    if acquisition_status == "ready_for_ai_generation":
        return "Review the AI prompt, generate the asset, then run visual QA."

    if acquisition_status == "needs_stock_sourcing":
        return "Search for licensed stock footage using the stock query, reject logo/text-heavy clips, and document the license source."

    if acquisition_status == "needs_manual_capture":
        return "Plan staged footage capture or manual edit setup using the production brief."

    return "Review the asset manually and decide the production route."


def filter_queue(decisions: list[dict], status: str) -> list[str]:
    return [
        decision["asset_id"]
        for decision in decisions
        if decision["acquisition_status"] == status
    ]


def build_output(
    channel: str,
    production_data: dict,
    production_path: Path
) -> dict:
    decisions = build_acquisition_decisions(production_data)
    first_build_queue = [
        decision["asset_id"]
        for decision in decisions
        if decision["is_first_build"]
    ]

    ready_internal = filter_queue(decisions, "ready_for_internal_production")
    ready_ai = filter_queue(decisions, "ready_for_ai_generation")
    stock_needed = filter_queue(decisions, "needs_stock_sourcing")
    manual_needed = filter_queue(decisions, "needs_manual_capture")
    review_needed = filter_queue(decisions, "needs_review")

    return {
        "agent": "visual_asset_acquisition",
        "version": "1.0",
        "channel": channel,
        "status": "acquisition_plan_ready",
        "acquisition_plan": {
            "first_build_queue": first_build_queue,
            "ready_for_internal_production": ready_internal,
            "ready_for_ai_generation": ready_ai,
            "needs_stock_sourcing": stock_needed,
            "needs_manual_capture": manual_needed,
            "needs_review": review_needed,
            "decisions": decisions
        },
        "summary": {
            "asset_count": len(decisions),
            "first_build_asset_count": len(first_build_queue),
            "ready_for_internal_production_count": len(ready_internal),
            "ready_for_ai_generation_count": len(ready_ai),
            "needs_stock_sourcing_count": len(stock_needed),
            "needs_manual_capture_count": len(manual_needed),
            "needs_review_count": len(review_needed),
            "next_agent": "internal_visual_production"
        },
        "source": {
            "source_agents": [
                "visual_asset_production"
            ],
            "visual_asset_production_reference": get_relative_path(production_path),
            "production_manifest_path": production_data["production_manifest"]["manifest_path"]
        },
        "metadata": {
            "next_agent": "internal_visual_production"
        }
    }


def dry_run(production_data: dict) -> None:
    decisions = build_acquisition_decisions(production_data)

    print("Visual Asset Acquisition Agent dry-run completed.")
    print(f"Channel: {production_data['channel']}")
    print(f"Assets: {len(decisions)}")
    print("First build queue:")

    for decision in decisions:
        if decision["is_first_build"]:
            print(
                f"- {decision['asset_id']} | "
                f"{decision['asset_type']} | "
                f"{decision['production_method']} | "
                f"{decision['acquisition_status']}"
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Classify visual assets by acquisition route."
    )

    parser.add_argument(
        "--channel",
        default=DEFAULT_CHANNEL,
        help="Channel name. Default: hiddenova"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate inputs without saving acquisition output."
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    load_dotenv(PROJECT_ROOT / ".env")

    production_path = get_visual_asset_production_latest_path(args.channel)
    production_data = load_json(production_path)

    if args.dry_run:
        dry_run(production_data)
        return

    final_output = build_output(
        channel=args.channel,
        production_data=production_data,
        production_path=production_path
    )

    schema = load_schema()
    validate(instance=final_output, schema=schema)

    latest_path = save_output(
        channel=final_output["channel"],
        data=final_output
    )

    print("Visual Asset Acquisition Agent completed successfully.")
    print(f"Output saved to: {latest_path}")


if __name__ == "__main__":
    main()
