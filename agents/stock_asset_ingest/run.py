import argparse
import json
import re
import shutil
from pathlib import Path

from dotenv import load_dotenv
from jsonschema import validate

from output import save_output


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent.parent

DEFAULT_CHANNEL = "hiddenova"
DEFAULT_SOURCE = Path.home() / "Desktop" / "storyblocks"

VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".mkv"}


def load_json(file_path: Path) -> dict:
    if not file_path.exists():
        raise FileNotFoundError(f"Required file not found: {file_path}")

    return json.loads(file_path.read_text(encoding="utf-8-sig"))


def write_json(file_path: Path, data: dict) -> None:
    file_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )


def load_schema() -> dict:
    return load_json(BASE_DIR / "schema.json")


def get_manifest_path(channel: str) -> Path:
    return PROJECT_ROOT / "records" / "assets" / channel.lower() / "stock_footage_manifest.json"


def get_relative_path(path: Path) -> str:
    return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")


def get_storyblocks_id(filename: str) -> str | None:
    match = re.search(r"SBV-\d+", filename, flags=re.IGNORECASE)
    if not match:
        return None

    return match.group(0).upper()


def slugify(value: str) -> str:
    value = value.lower()
    value = re.sub(r"sbv-\d+", "", value)
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = re.sub(r"_+", "_", value)
    value = value.strip("_")

    return value[:60] or "stock_clip"


def classify_file(filename: str) -> dict:
    name = filename.lower()

    rejected_keywords = [
        "tv-broadcast",
        "broadcast-truck",
        "mobile-broadcast",
        "tv-station"
    ]

    home_keywords = [
        "home",
        "household",
        "relocation",
        "packing",
        "removal-box",
        "customer",
        "online-shopping",
        "cardboard-box-at-home"
    ]

    inspection_keywords = [
        "scan",
        "barcode",
        "checking",
        "inspection",
        "quality-control",
        "worker-checking",
        "registering",
        "repackaging",
        "packing-order"
    ]

    logistics_keywords = [
        "warehouse",
        "logistics",
        "conveyor",
        "distribution",
        "parcel",
        "package",
        "packages",
        "boxes",
        "truck-loading",
        "pallet",
        "racks",
        "supply-chain",
        "sorting"
    ]

    if any(keyword in name for keyword in rejected_keywords):
        return {
            "asset_id": "REJECTED",
            "role": "rejected_unrelated",
            "usage_priority": 99,
            "status": "rejected_do_not_use",
            "risk_level": "not_applicable",
            "notes": "Auto-rejected by filename because it appears unrelated to ecommerce returns/logistics."
        }

    non_logistics_industrial_keywords = [
        "corn",
        "seed",
        "food",
        "dairy",
        "harvested",
        "agricultural",
        "cnc",
        "window-fac",
        "production-line",
        "programmable",
        "machine-in-window"
    ]

    if any(keyword in name for keyword in non_logistics_industrial_keywords):
        return {
            "asset_id": "REVIEW",
            "role": "needs_manual_review",
            "usage_priority": 50,
            "status": "needs_review",
            "risk_level": "medium",
            "notes": "Auto-flagged for manual review because filename suggests non-logistics industrial, food, agriculture, or factory footage."
        }

    if any(keyword in name for keyword in home_keywords):
        return {
            "asset_id": "A001",
            "role": "home_return_sequence",
            "usage_priority": 1,
            "status": "downloaded_pending_visual_qa",
            "risk_level": "medium",
            "notes": "Auto-classified as home/customer return b-roll. Needs visual QA for logos, labels, and private information."
        }

    if any(keyword in name for keyword in inspection_keywords):
        return {
            "asset_id": "A012",
            "role": "inspection_scanning_support",
            "usage_priority": 2,
            "status": "downloaded_pending_visual_qa",
            "risk_level": "medium_high",
            "notes": "Auto-classified as inspection/scanning b-roll. Needs careful QA for barcodes, readable labels, fake UI, and logos."
        }

    if any(keyword in name for keyword in logistics_keywords):
        return {
            "asset_id": "A010",
            "role": "logistics_warehouse_support",
            "usage_priority": 2,
            "status": "downloaded_pending_visual_qa",
            "risk_level": "medium",
            "notes": "Auto-classified as logistics/warehouse b-roll. Needs visual QA before public use."
        }

    return {
        "asset_id": "REVIEW",
        "role": "needs_manual_review",
        "usage_priority": 50,
        "status": "needs_review",
        "risk_level": "unknown",
        "notes": "Could not confidently auto-classify from filename."
    }


def get_next_candidate_number(manifest_data: dict, asset_id: str) -> int:
    max_number = 0

    for item in manifest_data.get("items", []):
        candidate_id = item.get("candidate_id", "")
        match = re.match(rf"{asset_id}-C(\d+)", candidate_id)

        if match:
            max_number = max(max_number, int(match.group(1)))

    return max_number + 1


def existing_storyblocks_ids(manifest_data: dict) -> set[str]:
    ids = set()

    for item in manifest_data.get("items", []):
        filename = item.get("filename", "")
        source = item.get("source_filename", "")

        for value in [filename, source]:
            storyblocks_id = get_storyblocks_id(value)
            if storyblocks_id:
                ids.add(storyblocks_id)

    return ids


def existing_filenames(manifest_data: dict) -> set[str]:
    return {
        item.get("filename", "")
        for item in manifest_data.get("items", [])
        if item.get("filename")
    }


def existing_file_sizes(manifest_data: dict) -> set[int]:
    sizes = set()

    for item in manifest_data.get("items", []):
        relative_path = item.get("relative_path")

        if not relative_path:
            continue

        path = PROJECT_ROOT / relative_path

        if path.exists() and path.is_file():
            sizes.add(path.stat().st_size)

    return sizes


def find_source_videos(source_dir: Path) -> list[Path]:
    if not source_dir.exists():
        raise FileNotFoundError(f"Source folder not found: {source_dir}")

    files = [
        path for path in source_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS
    ]

    return sorted(files, key=lambda path: path.name.lower())


def build_target_filename(asset_id: str, candidate_id: str, source_path: Path) -> str:
    storyblocks_id = get_storyblocks_id(source_path.name)
    slug = slugify(source_path.stem)

    if storyblocks_id:
        return f"{candidate_id}_{slug}_{storyblocks_id}.mp4"

    return f"{candidate_id}_{slug}.mp4"


def ingest_videos(channel: str, source_dir: Path, dry_run: bool) -> dict:
    manifest_path = get_manifest_path(channel)
    manifest_data = load_json(manifest_path)

    source_files = find_source_videos(source_dir)
    known_sbv_ids = existing_storyblocks_ids(manifest_data)
    known_filenames = existing_filenames(manifest_data)
    known_file_sizes = existing_file_sizes(manifest_data)

    ingested_items = []
    skipped_items = []

    next_numbers = {
        "A001": get_next_candidate_number(manifest_data, "A001"),
        "A010": get_next_candidate_number(manifest_data, "A010"),
        "A012": get_next_candidate_number(manifest_data, "A012")
    }

    review_number = 1
    rejected_number = 1

    for source_path in source_files:
        storyblocks_id = get_storyblocks_id(source_path.name)

        if storyblocks_id and storyblocks_id in known_sbv_ids:
            skipped_items.append({
                "source_filename": source_path.name,
                "reason": "already_in_manifest_by_storyblocks_id",
                "storyblocks_id": storyblocks_id
            })
            continue

        if source_path.name in known_filenames:
            skipped_items.append({
                "source_filename": source_path.name,
                "reason": "already_in_manifest_by_filename",
                "storyblocks_id": storyblocks_id
            })
            continue

        source_size = source_path.stat().st_size

        if source_size in known_file_sizes:
            skipped_items.append({
                "source_filename": source_path.name,
                "reason": "already_in_manifest_by_file_size",
                "storyblocks_id": storyblocks_id,
                "size_bytes": source_size
            })
            continue

        classification = classify_file(source_path.name)
        asset_id = classification["asset_id"]

        if asset_id in {"A001", "A010", "A012"}:
            candidate_id = f"{asset_id}-C{next_numbers[asset_id]:03d}"
            next_numbers[asset_id] += 1
            target_dir = PROJECT_ROOT / "assets" / "stock" / channel / asset_id
        elif asset_id == "REJECTED":
            candidate_id = f"R{rejected_number:03d}"
            rejected_number += 1
            target_dir = PROJECT_ROOT / "assets" / "stock" / channel / "rejected"
        else:
            candidate_id = f"REVIEW-C{review_number:03d}"
            review_number += 1
            target_dir = PROJECT_ROOT / "assets" / "stock" / channel / "review"

        target_filename = build_target_filename(
            asset_id=asset_id if asset_id in {"A001", "A010", "A012"} else candidate_id,
            candidate_id=candidate_id,
            source_path=source_path
        )

        target_path = target_dir / target_filename

        manifest_item = {
            "asset_id": asset_id,
            "candidate_id": candidate_id,
            "filename": target_filename,
            "source_filename": source_path.name,
            "storyblocks_id": storyblocks_id,
            "relative_path": get_relative_path(target_path),
            "role": classification["role"],
            "usage_priority": classification["usage_priority"],
            "status": classification["status"],
            "risk_level": classification["risk_level"],
            "notes": classification["notes"]
        }

        ingested_items.append(manifest_item)
        known_file_sizes.add(source_path.stat().st_size)

        if not dry_run:
            target_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, target_path)
            manifest_data["items"].append(manifest_item)

    if not dry_run:
        manifest_data["next_step"] = "run_stock_visual_qa_then_hybrid_video_assembly"
        write_json(manifest_path, manifest_data)

    return {
        "agent": "stock_asset_ingest",
        "version": "1.0",
        "channel": channel,
        "status": "dry_run_ready" if dry_run else "ingest_ready",
        "summary": {
            "source_folder": str(source_dir),
            "source_video_count": len(source_files),
            "new_ingested_count": len(ingested_items),
            "skipped_count": len(skipped_items),
            "dry_run": dry_run,
            "manifest_path": get_relative_path(manifest_path),
            "next_agent": "stock_visual_qa"
        },
        "ingested_items": ingested_items,
        "skipped_items": skipped_items,
        "source": {
            "source_folder": str(source_dir),
            "manifest_reference": get_relative_path(manifest_path)
        },
        "metadata": {
            "next_agent": "stock_visual_qa"
        }
    }


def print_summary(output: dict) -> None:
    print("Stock Asset Ingest Agent completed.")
    print(f"Status: {output['status']}")
    print(f"Source videos: {output['summary']['source_video_count']}")
    print(f"New ingested: {output['summary']['new_ingested_count']}")
    print(f"Skipped: {output['summary']['skipped_count']}")

    print("New items:")

    for item in output["ingested_items"]:
        print(
            f"- {item['candidate_id']} | {item['asset_id']} | "
            f"{item['role']} | {item['source_filename']}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest Storyblocks stock footage into Mecoria asset folders and manifest."
    )

    parser.add_argument(
        "--channel",
        default=DEFAULT_CHANNEL,
        help="Channel name. Default: hiddenova"
    )

    parser.add_argument(
        "--source",
        default=str(DEFAULT_SOURCE),
        help="Source folder containing downloaded Storyblocks videos."
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview ingest without copying files or updating manifest."
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    channel = args.channel.lower()
    source_dir = Path(args.source)

    load_dotenv(PROJECT_ROOT / ".env")

    output = ingest_videos(
        channel=channel,
        source_dir=source_dir,
        dry_run=args.dry_run
    )

    schema = load_schema()
    validate(instance=output, schema=schema)

    print_summary(output)

    if not args.dry_run:
        latest_path = save_output(
            channel=output["channel"],
            data=output
        )

        print(f"Output saved to: {latest_path}")


if __name__ == "__main__":
    main()
