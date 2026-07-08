import argparse
import json
from pathlib import Path

from dotenv import load_dotenv
from jsonschema import validate

from output import save_output


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent.parent

DEFAULT_CHANNEL = "hiddenova"

COMMON_NEGATIVE_PROMPT = (
    "no logos, no readable labels, no barcodes, no QR codes, no brand names, "
    "no visible addresses, no fake UI, no distorted hands, no unnatural faces, "
    "no cartoon style, no glossy corporate advertisement look, no text overlays"
)


def load_json(file_path: Path) -> dict:
    if not file_path.exists():
        raise FileNotFoundError(f"Required file not found: {file_path}")

    return json.loads(file_path.read_text(encoding="utf-8-sig"))


def load_schema() -> dict:
    return load_json(BASE_DIR / "schema.json")


def get_stock_manifest_path(channel: str) -> Path:
    return PROJECT_ROOT / "records" / "assets" / channel.lower() / "stock_footage_manifest.json"


def get_publisher_latest_path(channel: str) -> Path:
    return PROJECT_ROOT / "agents" / "publisher" / "output" / channel.lower() / "latest.json"


def get_relative_path(path: Path) -> str:
    return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")


def count_usable_stock_clips(stock_manifest_data: dict) -> int:
    count = 0

    for item in stock_manifest_data.get("items", []):
        status = item.get("status", "")

        if status.startswith("rejected"):
            continue

        if item.get("relative_path"):
            count += 1

    return count


def get_video_title(publisher_data: dict | None, stock_manifest_data: dict) -> str:
    if publisher_data:
        try:
            return publisher_data["publishing_package"]["video_metadata"]["title"]
        except KeyError:
            pass

    return stock_manifest_data.get(
        "video_title",
        "What Really Happens to Your Online Returns? The Hidden Reverse Logistics Network"
    )


def build_insert_items() -> list[dict]:
    raw_items = [
        (
            "AI-001",
            "hook",
            4,
            "cinematic_hook_insert",
            "Use within first 20 seconds between home box footage and warehouse footage.",
            "A cinematic documentary-style close-up of a plain unbranded cardboard box sitting on a dark conveyor belt inside a large logistics warehouse, moody lighting, shallow depth of field, realistic texture, anonymous, no readable labels, no logos, high-end documentary look, 16:9 frame"
        ),
        (
            "AI-002",
            "reverse logistics network",
            5,
            "system_bridge_insert",
            "Use after aerial distribution center footage to connect scale with hidden routing.",
            "A realistic cinematic visualization of unbranded packages moving through a vast dark logistics network, conveyor lines stretching into the distance, subtle glowing route paths, documentary realism, industrial atmosphere, no logos, no text, no readable labels, 16:9 frame"
        ),
        (
            "AI-003",
            "warehouse automation",
            4,
            "automation_insert",
            "Use between conveyor footage and warehouse aisle footage.",
            "A dark realistic warehouse automation scene with anonymous cardboard boxes passing under soft scanner lights on a conveyor belt, cinematic shadows, industrial documentary style, no company branding, no readable labels, 16:9 frame"
        ),
        (
            "AI-004",
            "inspection",
            5,
            "inspection_insert",
            "Use before or after scanning / inspection footage.",
            "A realistic documentary macro shot of anonymous gloved hands inspecting a generic returned product on a clean industrial inspection table, cardboard boxes in soft background, moody controlled lighting, no logos, no labels, no text, high realism, 16:9 frame"
        ),
        (
            "AI-005",
            "value decision",
            5,
            "decision_moment_insert",
            "Use near decision diagram as cinematic setup before graphic explanation.",
            "A cinematic close-up of a returned item on a dark inspection table with multiple unbranded sorting bins in the background, atmosphere of decision and evaluation, documentary lighting, realistic warehouse environment, no text, no logos, no readable labels, 16:9 frame"
        ),
        (
            "AI-006",
            "liquidation",
            5,
            "liquidation_insert",
            "Use when narration mentions liquidation pallets or resale channels.",
            "A realistic documentary-style warehouse corner filled with unbranded liquidation pallets and plain cardboard boxes stacked under moody industrial lighting, subtle dust in air, no logos, no readable labels, no people facing camera, 16:9 frame"
        ),
        (
            "AI-007",
            "resale",
            4,
            "resale_insert",
            "Use between warehouse b-roll and closing section.",
            "A cinematic realistic shot of a plain refurbished product being packed into an unbranded cardboard box on a minimal workbench, soft warehouse background, premium documentary lighting, no logos, no labels, no text, 16:9 frame"
        ),
        (
            "AI-008",
            "unrecoverable goods",
            5,
            "waste_recovery_insert",
            "Use when narration discusses discarded or unrecoverable items.",
            "A realistic documentary scene of anonymous damaged returned goods in plain bins at a recycling or recovery facility, dark industrial lighting, serious investigative tone, no logos, no readable labels, no gore, no text, 16:9 frame"
        ),
        (
            "AI-009",
            "data layer",
            4,
            "data_layer_insert",
            "Use as bridge before graph or decision diagram.",
            "A realistic dark logistics control room atmosphere with blurred anonymous screens and abstract package route lights, no readable text, no fake dashboards, no logos, cinematic documentary style, subtle data network feeling, 16:9 frame"
        ),
        (
            "AI-010",
            "night logistics",
            5,
            "night_transition_insert",
            "Use before or after truck/loading dock footage.",
            "A realistic cinematic night shot of an anonymous logistics warehouse with loading docks, plain trucks, soft rain reflections, moody lighting, documentary atmosphere, no company logos, no readable signs, no text, 16:9 frame"
        ),
        (
            "AI-011",
            "hidden system",
            5,
            "hidden_system_insert",
            "Use as mid-video reset when stock footage starts to repeat.",
            "A cinematic documentary wide shot inside a massive anonymous warehouse where hundreds of plain boxes move through dimly lit conveyor paths, hidden infrastructure mood, realistic industrial scale, no logos, no text, no readable labels, 16:9 frame"
        ),
        (
            "AI-012",
            "closing",
            5,
            "closing_insert",
            "Use in final 60 seconds before CTA or final line.",
            "A cinematic final shot of a plain unbranded cardboard box resting alone on a warehouse floor under a single soft overhead light, dark documentary atmosphere, quiet and mysterious, no logos, no labels, no text, 16:9 frame"
        )
    ]

    items = []

    for index, item in enumerate(raw_items, start=1):
        insert_id, section_hint, duration, visual_role, placement_strategy, prompt = item

        items.append({
            "insert_id": insert_id,
            "sequence": index,
            "section_hint": section_hint,
            "purpose": f"Support the {section_hint} part of the video with a short cinematic AI visual insert.",
            "target_duration_seconds": duration,
            "visual_role": visual_role,
            "placement_strategy": placement_strategy,
            "prompt": prompt,
            "negative_prompt": COMMON_NEGATIVE_PROMPT,
            "status": "planned"
        })

    return items


def build_output(channel: str, publisher_data: dict | None, stock_manifest_data: dict, stock_manifest_path: Path, publisher_path: Path) -> dict:
    items = build_insert_items()
    target_total_seconds = sum(item["target_duration_seconds"] for item in items)

    source_files = [
        get_relative_path(stock_manifest_path)
    ]

    if publisher_data:
        source_files.append(get_relative_path(publisher_path))

    return {
        "agent": "ai_visual_insert_plan",
        "version": "1.0",
        "channel": channel,
        "status": "plan_ready",
        "summary": {
            "insert_count": len(items),
            "target_total_insert_seconds": target_total_seconds,
            "recommended_visual_role": "Use AI visuals as short cinematic inserts between real stock clips, not as the main video backbone.",
            "next_agent": "ai_visual_generation"
        },
        "ai_visual_insert_plan": {
            "style_rules": [
                "realistic documentary look",
                "dark Hiddenova atmosphere",
                "anonymous environments",
                "unbranded objects",
                "no readable private information",
                "AI inserts should be short, usually 4-5 seconds",
                "AI visuals should support real stock footage, not replace it"
            ],
            "negative_rules": [
                "no logos",
                "no readable labels",
                "no barcodes",
                "no QR codes",
                "no fake dashboards",
                "no cartoon style",
                "no glossy corporate ad style",
                "no strange hands or faces",
                "no obvious AI surrealism"
            ],
            "items": items
        },
        "source": {
            "source_files": source_files,
            "video_title": get_video_title(publisher_data, stock_manifest_data),
            "stock_clip_count": count_usable_stock_clips(stock_manifest_data)
        },
        "metadata": {
            "next_agent": "ai_visual_generation"
        }
    }


def dry_run(final_output: dict) -> None:
    print("AI Visual Insert Plan Agent dry-run completed.")
    print(f"Channel: {final_output['channel']}")
    print(f"Status: {final_output['status']}")
    print(f"Insert count: {final_output['summary']['insert_count']}")
    print(f"Target insert seconds: {final_output['summary']['target_total_insert_seconds']}")
    print(f"Stock clip count: {final_output['source']['stock_clip_count']}")
    print("Planned inserts:")

    for item in final_output["ai_visual_insert_plan"]["items"]:
        print(
            f"- {item['insert_id']} | {item['section_hint']} | "
            f"{item['target_duration_seconds']}s | {item['visual_role']}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plan AI cinematic visual inserts for Hiddenova stock-based video assembly."
    )

    parser.add_argument(
        "--channel",
        default=DEFAULT_CHANNEL,
        help="Channel name. Default: hiddenova"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate output without saving."
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    channel = args.channel.lower()

    load_dotenv(PROJECT_ROOT / ".env")

    stock_manifest_path = get_stock_manifest_path(channel)
    publisher_path = get_publisher_latest_path(channel)

    stock_manifest_data = load_json(stock_manifest_path)
    publisher_data = load_json(publisher_path) if publisher_path.exists() else None

    final_output = build_output(
        channel=channel,
        publisher_data=publisher_data,
        stock_manifest_data=stock_manifest_data,
        stock_manifest_path=stock_manifest_path,
        publisher_path=publisher_path
    )

    schema = load_schema()
    validate(instance=final_output, schema=schema)

    if args.dry_run:
        dry_run(final_output)
        return

    latest_path = save_output(
        channel=final_output["channel"],
        data=final_output
    )

    print("AI Visual Insert Plan Agent completed successfully.")
    print(f"Output saved to: {latest_path}")


if __name__ == "__main__":
    main()
