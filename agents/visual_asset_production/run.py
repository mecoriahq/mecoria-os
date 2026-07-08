import argparse
import json
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from jsonschema import validate

from output import save_output


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent.parent

DEFAULT_CHANNEL = "hiddenova"


def load_json(file_path: Path) -> dict:
    if not file_path.exists():
        raise FileNotFoundError(f"Required file not found: {file_path}")

    return json.loads(file_path.read_text(encoding="utf-8"))


def load_schema() -> dict:
    return load_json(BASE_DIR / "schema.json")


def get_visual_asset_plan_latest_path(channel: str) -> Path:
    return PROJECT_ROOT / "agents" / "visual_asset_plan" / "output" / channel.lower() / "latest.json"


def get_relative_path(path: Path) -> str:
    return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")


def create_manifest_dir(channel: str) -> Path:
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    manifest_dir = (
        BASE_DIR
        / "output"
        / channel.lower()
        / "manifests"
        / timestamp
    )

    manifest_dir.mkdir(parents=True, exist_ok=True)
    return manifest_dir


def write_text(path: Path, content: str) -> None:
    path.write_text(content.strip() + "\n", encoding="utf-8")


def format_list(items: list) -> str:
    if not items:
        return "- None"

    return "\n".join(f"- {item}" for item in items)


def safe_value(value) -> str:
    if value is None:
        return "N/A"

    if isinstance(value, list):
        return format_list(value)

    return str(value)


def create_asset_folder(manifest_dir: Path, asset: dict) -> dict:
    asset_id = asset["asset_id"]
    asset_dir = manifest_dir / "assets" / asset_id
    asset_dir.mkdir(parents=True, exist_ok=True)

    files = {}

    brief_path = asset_dir / "brief.md"
    write_text(
        brief_path,
        f"""
# {asset_id} Production Brief

## Type
{asset["asset_type"]}

## Priority
{asset["priority"]}

## Production Method
{asset["production_method"]}

## Purpose
{asset["purpose"]}

## Creative Brief
{asset["creative_brief"]}

## Scenes Covered
{format_list(asset["scenes_covered"])}
"""
    )
    files["brief"] = brief_path.name

    stock_query_path = asset_dir / "stock_search_query.txt"
    write_text(stock_query_path, safe_value(asset.get("stock_search_query")))
    files["stock_search_query"] = stock_query_path.name

    ai_prompt_path = asset_dir / "ai_image_prompt.txt"
    write_text(ai_prompt_path, safe_value(asset.get("ai_image_prompt")))
    files["ai_image_prompt"] = ai_prompt_path.name

    motion_path = asset_dir / "motion_graphic_instructions.md"
    write_text(motion_path, safe_value(asset.get("motion_graphic_instructions")))
    files["motion_graphic_instructions"] = motion_path.name

    diagram_path = asset_dir / "diagram_instructions.md"
    write_text(diagram_path, safe_value(asset.get("diagram_instructions")))
    files["diagram_instructions"] = diagram_path.name

    editing_path = asset_dir / "editing_notes.md"
    write_text(editing_path, safe_value(asset.get("editing_notes")))
    files["editing_notes"] = editing_path.name

    constraints_path = asset_dir / "quality_constraints.md"
    write_text(constraints_path, safe_value(asset.get("quality_constraints")))
    files["quality_constraints"] = constraints_path.name

    status_path = asset_dir / "status.json"
    status = {
        "asset_id": asset_id,
        "status": "not_started",
        "priority": asset["priority"],
        "asset_type": asset["asset_type"],
        "production_method": asset["production_method"],
        "assigned_to": None,
        "source_file_path": None,
        "final_file_path": None,
        "qa_status": "not_started",
        "notes": []
    }

    status_path.write_text(
        json.dumps(status, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    files["status"] = status_path.name

    return {
        "asset_id": asset_id,
        "asset_type": asset["asset_type"],
        "priority": asset["priority"],
        "production_method": asset["production_method"],
        "folder": get_relative_path(asset_dir),
        "files": files,
        "status": "not_started"
    }


def build_manifest(
    channel: str,
    plan_data: dict,
    plan_path: Path
) -> tuple[dict, Path]:
    manifest_dir = create_manifest_dir(channel)

    reusable_assets = plan_data["asset_plan"]["reusable_assets"]
    scene_asset_map = plan_data["asset_plan"]["scene_asset_map"]

    asset_entries = [
        create_asset_folder(
            manifest_dir=manifest_dir,
            asset=asset
        )
        for asset in reusable_assets
    ]

    manifest = {
        "channel": channel,
        "manifest_type": "visual_asset_production",
        "version": "1.0",
        "source_visual_asset_plan": get_relative_path(plan_path),
        "asset_count": len(asset_entries),
        "scene_count": plan_data["summary"]["storyboard_scene_count"],
        "mapped_scene_count": plan_data["summary"]["mapped_scene_count"],
        "assets": asset_entries,
        "scene_asset_map": scene_asset_map,
        "first_assets_to_create": plan_data["asset_plan"]["next_steps"]["first_assets_to_create"],
        "manual_assets_needed": plan_data["asset_plan"]["next_steps"]["manual_assets_needed"]
    }

    manifest_path = manifest_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    return manifest, manifest_path


def build_output(
    channel: str,
    plan_data: dict,
    plan_path: Path,
    manifest: dict,
    manifest_path: Path
) -> dict:
    high_priority_count = sum(
        1 for asset in manifest["assets"]
        if asset["priority"] == "high"
    )

    return {
        "agent": "visual_asset_production",
        "version": "1.0",
        "channel": channel,
        "status": "manifest_ready",
        "production_manifest": {
            "manifest_path": get_relative_path(manifest_path),
            "asset_count": manifest["asset_count"],
            "scene_count": manifest["scene_count"],
            "mapped_scene_count": manifest["mapped_scene_count"],
            "first_assets_to_create": manifest["first_assets_to_create"],
            "manual_assets_needed": manifest["manual_assets_needed"],
            "assets": manifest["assets"]
        },
        "summary": {
            "asset_count": manifest["asset_count"],
            "high_priority_asset_count": high_priority_count,
            "first_build_asset_count": len(manifest["first_assets_to_create"]),
            "next_agent": "visual_asset_acquisition"
        },
        "source": {
            "source_agents": [
                "visual_asset_plan"
            ],
            "visual_asset_plan_reference": get_relative_path(plan_path)
        },
        "metadata": {
            "next_agent": "visual_asset_acquisition"
        }
    }


def dry_run(plan_data: dict) -> None:
    assets = plan_data["asset_plan"]["reusable_assets"]
    first_assets = plan_data["asset_plan"]["next_steps"]["first_assets_to_create"]

    print("Visual Asset Production Manifest Agent dry-run completed.")
    print(f"Channel: {plan_data['channel']}")
    print(f"Reusable assets: {len(assets)}")
    print(f"Mapped scenes: {plan_data['summary']['mapped_scene_count']}")
    print(f"First assets to create: {', '.join(first_assets)}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create production manifest files from Visual Asset Plan output."
    )

    parser.add_argument(
        "--channel",
        default=DEFAULT_CHANNEL,
        help="Channel name. Default: hiddenova"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate inputs without creating manifest files."
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    load_dotenv(PROJECT_ROOT / ".env")

    plan_path = get_visual_asset_plan_latest_path(args.channel)
    plan_data = load_json(plan_path)

    if args.dry_run:
        dry_run(plan_data)
        return

    manifest, manifest_path = build_manifest(
        channel=args.channel,
        plan_data=plan_data,
        plan_path=plan_path
    )

    final_output = build_output(
        channel=args.channel,
        plan_data=plan_data,
        plan_path=plan_path,
        manifest=manifest,
        manifest_path=manifest_path
    )

    schema = load_schema()
    validate(instance=final_output, schema=schema)

    latest_path = save_output(
        channel=final_output["channel"],
        data=final_output
    )

    print("Visual Asset Production Manifest Agent completed successfully.")
    print(f"Manifest saved to: {manifest_path}")
    print(f"Output saved to: {latest_path}")


if __name__ == "__main__":
    main()
