import argparse
import json
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


def get_visual_asset_acquisition_latest_path(channel: str) -> Path:
    return PROJECT_ROOT / "agents" / "visual_asset_acquisition" / "output" / channel.lower() / "latest.json"


def get_internal_visual_render_latest_path(channel: str) -> Path:
    return PROJECT_ROOT / "agents" / "internal_visual_render" / "output" / channel.lower() / "latest.json"


def get_internal_visual_render_qa_latest_path(channel: str) -> Path:
    return PROJECT_ROOT / "agents" / "internal_visual_render_qa" / "output" / channel.lower() / "latest.json"


def get_relative_path(path: Path) -> str:
    return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")


def ensure_render_qa_approved(render_qa_data: dict) -> None:
    if render_qa_data.get("status") != "approved":
        raise ValueError("Internal Visual Render QA is not approved.")


def build_rendered_asset_index(render_data: dict) -> dict:
    index = {}

    for asset in render_data["rendered_visual_assets"]["assets"]:
        index[asset["asset_id"]] = {
            "asset_id": asset["asset_id"],
            "asset_type": asset["asset_type"],
            "status": asset["status"],
            "rendered_files": asset["rendered_files"],
            "rendered_output_folder": asset["rendered_output_folder"]
        }

    return index


def build_acquisition_index(acquisition_data: dict) -> dict:
    return {
        decision["asset_id"]: decision
        for decision in acquisition_data["acquisition_plan"]["decisions"]
    }


def choose_primary_rendered_file(asset_id: str, rendered_asset: dict | None) -> str | None:
    if not rendered_asset:
        return None

    rendered_files = rendered_asset.get("rendered_files", [])

    if not rendered_files:
        return None

    if asset_id == "A002":
        preferred_order = [
            "expanded",
            "start",
            "loop"
        ]
    elif asset_id == "A004":
        preferred_order = [
            "hook",
            "conclusion",
            "cta"
        ]
    elif asset_id == "A007":
        preferred_order = [
            "general",
            "restock",
            "unrecoverable"
        ]
    else:
        preferred_order = []

    for keyword in preferred_order:
        for file_data in rendered_files:
            if keyword in file_data["filename"]:
                return file_data["relative_path"]

    return rendered_files[0]["relative_path"]


def get_scene_status(
    primary_asset_id: str,
    rendered_asset_index: dict,
    acquisition_index: dict
) -> tuple[str, list[str], str]:
    rendered_asset = rendered_asset_index.get(primary_asset_id)

    if rendered_asset:
        primary_file = choose_primary_rendered_file(
            asset_id=primary_asset_id,
            rendered_asset=rendered_asset
        )

        if primary_file:
            return (
                "ready_with_internal_render",
                [primary_file],
                "Primary visual asset has approved rendered PNG output."
            )

    acquisition = acquisition_index.get(primary_asset_id)

    if not acquisition:
        return (
            "needs_review",
            [],
            "Primary asset is missing from acquisition plan."
        )

    status = acquisition["acquisition_status"]

    if status == "needs_stock_sourcing":
        return (
            "needs_stock_sourcing",
            [],
            "Primary asset requires licensed stock sourcing."
        )

    if status == "needs_manual_capture":
        return (
            "needs_manual_capture",
            [],
            "Primary asset requires manual capture or staged footage."
        )

    if status == "ready_for_internal_production":
        return (
            "internal_asset_not_rendered",
            [],
            "Primary asset is internal but no rendered PNG is available yet."
        )

    if status == "ready_for_ai_generation":
        return (
            "needs_ai_generation",
            [],
            "Primary asset requires AI generation."
        )

    return (
        "needs_review",
        [],
        "Primary asset requires manual review."
    )


def build_scene_visual_map(
    asset_plan_data: dict,
    rendered_asset_index: dict,
    acquisition_index: dict
) -> list[dict]:
    scene_visual_map = []

    for scene_map in asset_plan_data["asset_plan"]["scene_asset_map"]:
        primary_asset_id = scene_map["primary_asset_id"]

        scene_status, resolved_visual_paths, status_reason = get_scene_status(
            primary_asset_id=primary_asset_id,
            rendered_asset_index=rendered_asset_index,
            acquisition_index=acquisition_index
        )

        scene_visual_map.append({
            "section_sequence": scene_map["section_sequence"],
            "scene_number": scene_map["scene_number"],
            "primary_asset_id": primary_asset_id,
            "supporting_asset_ids": scene_map["supporting_asset_ids"],
            "scene_status": scene_status,
            "resolved_visual_paths": resolved_visual_paths,
            "status_reason": status_reason
        })

    return scene_visual_map


def build_integrated_assets(
    acquisition_index: dict,
    rendered_asset_index: dict
) -> list[dict]:
    integrated_assets = []

    for asset_id, acquisition in acquisition_index.items():
        rendered_asset = rendered_asset_index.get(asset_id)

        if rendered_asset:
            availability_status = "available"
            rendered_files = rendered_asset["rendered_files"]
        else:
            availability_status = acquisition["acquisition_status"]
            rendered_files = []

        integrated_assets.append({
            "asset_id": asset_id,
            "asset_type": acquisition["asset_type"],
            "production_method": acquisition["production_method"],
            "acquisition_status": acquisition["acquisition_status"],
            "availability_status": availability_status,
            "is_first_build": acquisition["is_first_build"],
            "rendered_files": rendered_files,
            "next_action": acquisition["next_action"]
        })

    return sorted(
        integrated_assets,
        key=lambda asset: (
            not asset["is_first_build"],
            asset["asset_id"]
        )
    )


def build_output(
    channel: str,
    asset_plan_data: dict,
    acquisition_data: dict,
    render_data: dict,
    render_qa_data: dict,
    asset_plan_path: Path,
    acquisition_path: Path,
    render_path: Path,
    render_qa_path: Path
) -> dict:
    ensure_render_qa_approved(render_qa_data)

    rendered_asset_index = build_rendered_asset_index(render_data)
    acquisition_index = build_acquisition_index(acquisition_data)

    integrated_assets = build_integrated_assets(
        acquisition_index=acquisition_index,
        rendered_asset_index=rendered_asset_index
    )

    scene_visual_map = build_scene_visual_map(
        asset_plan_data=asset_plan_data,
        rendered_asset_index=rendered_asset_index,
        acquisition_index=acquisition_index
    )

    total_scenes = len(scene_visual_map)
    ready_scenes = sum(
        1 for scene in scene_visual_map
        if scene["scene_status"] == "ready_with_internal_render"
    )

    stock_scenes = sum(
        1 for scene in scene_visual_map
        if scene["scene_status"] == "needs_stock_sourcing"
    )

    manual_scenes = sum(
        1 for scene in scene_visual_map
        if scene["scene_status"] == "needs_manual_capture"
    )

    available_assets = sum(
        1 for asset in integrated_assets
        if asset["availability_status"] == "available"
    )

    return {
        "agent": "visual_asset_integration",
        "version": "1.0",
        "channel": channel,
        "status": "integration_ready",
        "visual_asset_package": {
            "integrated_assets": integrated_assets,
            "scene_visual_map": scene_visual_map
        },
        "summary": {
            "asset_count": len(integrated_assets),
            "available_asset_count": available_assets,
            "scene_count": total_scenes,
            "ready_scene_count": ready_scenes,
            "needs_stock_scene_count": stock_scenes,
            "needs_manual_scene_count": manual_scenes,
            "next_agent": "video_assembly_v1"
        },
        "source": {
            "source_agents": [
                "visual_asset_plan",
                "visual_asset_acquisition",
                "internal_visual_render",
                "internal_visual_render_qa"
            ],
            "visual_asset_plan_reference": get_relative_path(asset_plan_path),
            "visual_asset_acquisition_reference": get_relative_path(acquisition_path),
            "internal_visual_render_reference": get_relative_path(render_path),
            "internal_visual_render_qa_reference": get_relative_path(render_qa_path),
            "internal_visual_render_qa_status": render_qa_data["status"]
        },
        "metadata": {
            "next_agent": "video_assembly_v1"
        }
    }


def dry_run(
    asset_plan_data: dict,
    acquisition_data: dict,
    render_data: dict,
    render_qa_data: dict
) -> None:
    ensure_render_qa_approved(render_qa_data)

    rendered_asset_index = build_rendered_asset_index(render_data)
    acquisition_index = build_acquisition_index(acquisition_data)

    scene_visual_map = build_scene_visual_map(
        asset_plan_data=asset_plan_data,
        rendered_asset_index=rendered_asset_index,
        acquisition_index=acquisition_index
    )

    ready_scenes = sum(
        1 for scene in scene_visual_map
        if scene["scene_status"] == "ready_with_internal_render"
    )

    print("Visual Asset Integration Agent dry-run completed.")
    print(f"Channel: {asset_plan_data['channel']}")
    print(f"Integrated assets: {len(acquisition_index)}")
    print(f"Rendered assets available: {len(rendered_asset_index)}")
    print(f"Mapped scenes: {len(scene_visual_map)}")
    print(f"Ready scenes with internal renders: {ready_scenes}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Integrate rendered internal visuals with visual asset plan scene mapping."
    )

    parser.add_argument(
        "--channel",
        default=DEFAULT_CHANNEL,
        help="Channel name. Default: hiddenova"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate inputs without saving integration output."
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    load_dotenv(PROJECT_ROOT / ".env")

    asset_plan_path = get_visual_asset_plan_latest_path(args.channel)
    acquisition_path = get_visual_asset_acquisition_latest_path(args.channel)
    render_path = get_internal_visual_render_latest_path(args.channel)
    render_qa_path = get_internal_visual_render_qa_latest_path(args.channel)

    asset_plan_data = load_json(asset_plan_path)
    acquisition_data = load_json(acquisition_path)
    render_data = load_json(render_path)
    render_qa_data = load_json(render_qa_path)

    if args.dry_run:
        dry_run(
            asset_plan_data=asset_plan_data,
            acquisition_data=acquisition_data,
            render_data=render_data,
            render_qa_data=render_qa_data
        )
        return

    final_output = build_output(
        channel=args.channel,
        asset_plan_data=asset_plan_data,
        acquisition_data=acquisition_data,
        render_data=render_data,
        render_qa_data=render_qa_data,
        asset_plan_path=asset_plan_path,
        acquisition_path=acquisition_path,
        render_path=render_path,
        render_qa_path=render_qa_path
    )

    schema = load_schema()
    validate(instance=final_output, schema=schema)

    latest_path = save_output(
        channel=final_output["channel"],
        data=final_output
    )

    print("Visual Asset Integration Agent completed successfully.")
    print(f"Output saved to: {latest_path}")


if __name__ == "__main__":
    main()
