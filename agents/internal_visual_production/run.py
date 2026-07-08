import argparse
import json
from datetime import datetime
from html import escape
from pathlib import Path

from dotenv import load_dotenv
from jsonschema import validate

from output import save_output


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent.parent

DEFAULT_CHANNEL = "hiddenova"
WIDTH = 1920
HEIGHT = 1080


def load_json(file_path: Path) -> dict:
    if not file_path.exists():
        raise FileNotFoundError(f"Required file not found: {file_path}")

    return json.loads(file_path.read_text(encoding="utf-8"))


def load_schema() -> dict:
    return load_json(BASE_DIR / "schema.json")


def get_acquisition_latest_path(channel: str) -> Path:
    return PROJECT_ROOT / "agents" / "visual_asset_acquisition" / "output" / channel.lower() / "latest.json"


def get_relative_path(path: Path) -> str:
    return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")


def create_output_dir(channel: str) -> Path:
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    output_dir = (
        BASE_DIR
        / "output"
        / channel.lower()
        / "assets"
        / timestamp
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def svg_template(title: str, body: str) -> str:
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">
  <title>{escape(title)}</title>
  <rect width="{WIDTH}" height="{HEIGHT}" fill="#101419"/>
  <rect x="0" y="0" width="{WIDTH}" height="{HEIGHT}" fill="url(#bgGradient)" opacity="0.95"/>
  <defs>
    <linearGradient id="bgGradient" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#0b0f14"/>
      <stop offset="55%" stop-color="#141b23"/>
      <stop offset="100%" stop-color="#07090c"/>
    </linearGradient>
    <filter id="softGlow">
      <feGaussianBlur stdDeviation="5" result="blur"/>
      <feMerge>
        <feMergeNode in="blur"/>
        <feMergeNode in="SourceGraphic"/>
      </feMerge>
    </filter>
  </defs>
  {body}
</svg>
'''


def text(x: int, y: int, value: str, size: int = 36, color: str = "#f4f7fb", weight: str = "500", anchor: str = "middle") -> str:
    return (
        f'<text x="{x}" y="{y}" text-anchor="{anchor}" '
        f'font-family="Inter, Arial, sans-serif" font-size="{size}" '
        f'font-weight="{weight}" fill="{color}">{escape(value)}</text>'
    )


def line(x1: int, y1: int, x2: int, y2: int, color: str = "#4aa3ff", width: int = 4, opacity: float = 0.75) -> str:
    return (
        f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
        f'stroke="{color}" stroke-width="{width}" opacity="{opacity}" stroke-linecap="round"/>'
    )


def node(x: int, y: int, label: str, color: str = "#182330", stroke: str = "#4aa3ff") -> str:
    return f'''
  <circle cx="{x}" cy="{y}" r="42" fill="{color}" stroke="{stroke}" stroke-width="3"/>
  <circle cx="{x}" cy="{y}" r="9" fill="#f0a33a" filter="url(#softGlow)"/>
  {text(x, y + 84, label, size=26, color="#dce7f2")}
'''


def box(x: int, y: int, w: int, h: int, label: str, stroke: str = "#4aa3ff") -> str:
    return f'''
  <rect x="{x}" y="{y}" width="{w}" height="{h}" rx="18" fill="#141d26" stroke="{stroke}" stroke-width="3"/>
  {text(x + w // 2, y + h // 2 + 10, label, size=30, color="#f4f7fb")}
'''


def write_svg(path: Path, title: str, body: str) -> dict:
    path.write_text(svg_template(title=title, body=body), encoding="utf-8")

    return {
        "filename": path.name,
        "relative_path": get_relative_path(path),
        "format": "svg"
    }


def create_a002(asset_dir: Path) -> list[dict]:
    files = []

    body_start = f'''
  {text(960, 115, "A RETURN ENTERS THE HIDDEN NETWORK", 44, "#ffffff", "700")}
  {line(420, 520, 760, 520)}
  {line(760, 520, 1040, 360)}
  {line(760, 520, 1040, 520)}
  {line(760, 520, 1040, 680)}
  {node(420, 520, "HOME")}
  {node(760, 520, "CARRIER HUB")}
  {node(1040, 360, "RETURN CENTER")}
  {node(1040, 520, "INSPECTION")}
  {node(1040, 680, "SECONDARY MARKET")}
  {text(960, 950, "Abstract route map — no real addresses, brands, or exact routes", 28, "#8794a3")}
'''
    files.append(write_svg(asset_dir / "a002_reverse_network_start.svg", "A002 reverse network start", body_start))

    body_expanded = f'''
  {text(960, 115, "ONE BOX BECOMES MANY POSSIBLE ROUTES", 44, "#ffffff", "700")}
  {line(330, 520, 650, 520)}
  {line(650, 520, 960, 280)}
  {line(650, 520, 960, 430)}
  {line(650, 520, 960, 580)}
  {line(650, 520, 960, 730)}
  {line(960, 430, 1280, 340)}
  {line(960, 580, 1280, 640)}
  {node(330, 520, "HOME")}
  {node(650, 520, "LOCAL HUB")}
  {node(960, 280, "RESTOCK")}
  {node(960, 430, "REPAIR")}
  {node(960, 580, "LIQUIDATE")}
  {node(960, 730, "RECYCLE")}
  {node(1280, 340, "RESELLER")}
  {node(1280, 640, "NEW CUSTOMER")}
  {text(960, 950, "Reusable Hiddenova map language: charcoal, blue route lines, amber nodes", 28, "#8794a3")}
'''
    files.append(write_svg(asset_dir / "a002_reverse_network_expanded.svg", "A002 reverse network expanded", body_expanded))

    body_loop = f'''
  {text(960, 115, "THE RETURN ECONOMY IS A LOOP", 44, "#ffffff", "700")}
  <path d="M520,540 C600,260 1320,260 1400,540 C1320,820 600,820 520,540" fill="none" stroke="#4aa3ff" stroke-width="5" opacity="0.75"/>
  <path d="M560,560 C670,360 1230,360 1350,560" fill="none" stroke="#f0a33a" stroke-width="3" opacity="0.55"/>
  {node(520, 540, "RETURN")}
  {node(760, 340, "INSPECT")}
  {node(1160, 340, "REFURBISH")}
  {node(1400, 540, "RESELL")}
  {node(1160, 760, "NEW BUYER")}
  {node(760, 760, "RECYCLE")}
  {text(960, 950, "Loop graphic for conclusion and recommerce sections", 28, "#8794a3")}
'''
    files.append(write_svg(asset_dir / "a002_recommerce_loop.svg", "A002 recommerce loop", body_loop))

    return files


def create_a004(asset_dir: Path) -> list[dict]:
    files = []

    cards = [
        ("a004_hook_question.svg", "WHAT HAPPENS NOW...", "Behind every convenient return is a hidden system."),
        ("a004_conclusion_question.svg", "CAN THIS PRODUCT BEGIN AGAIN...", "A returned box enters a maze of decisions."),
        ("a004_cta_card.svg", "THE HIDDEN SYSTEMS BEHIND EVERYDAY LIFE", "Subscribe to Hiddenova.")
    ]

    for filename, headline, subline in cards:
        body = f'''
  <rect x="260" y="330" width="1400" height="310" rx="28" fill="#0d1117" stroke="#263545" stroke-width="2" opacity="0.92"/>
  <line x1="360" y1="690" x2="1560" y2="690" stroke="#4aa3ff" stroke-width="3" opacity="0.6"/>
  {text(960, 465, headline, 58, "#ffffff", "800")}
  {text(960, 550, subline, 34, "#b8c7d9", "400")}
  {text(960, 810, "HIDDENOVA", 28, "#f0a33a", "700")}
'''
        files.append(write_svg(asset_dir / filename, filename.replace(".svg", ""), body))

    return files


def create_a007(asset_dir: Path) -> list[dict]:
    files = []

    body_outcomes = f'''
  {text(960, 105, "WHAT CAN HAPPEN TO A RETURNED PRODUCT...", 44, "#ffffff", "700")}
  {box(760, 230, 400, 90, "RETURNED ITEM", "#f0a33a")}
  {line(960, 320, 460, 500)}
  {line(960, 320, 760, 500)}
  {line(960, 320, 1060, 500)}
  {line(960, 320, 1360, 500)}
  {box(260, 500, 390, 90, "RESTOCK")}
  {box(560, 500, 390, 90, "INSPECT")}
  {box(860, 500, 390, 90, "REPAIR")}
  {box(1160, 500, 390, 90, "LIQUIDATE")}
  {line(760, 590, 560, 760)}
  {line(1060, 590, 960, 760)}
  {line(1360, 590, 1360, 760)}
  {box(360, 760, 390, 90, "RECYCLE")}
  {box(760, 760, 390, 90, "RESELL")}
  {box(1160, 760, 390, 90, "DISPOSE")}
  {text(960, 980, "OUTCOMES VARY BY ITEM, POLICY, AND LOCAL RULES", 28, "#8794a3")}
'''
    files.append(write_svg(asset_dir / "a007_general_outcomes.svg", "A007 general outcomes", body_outcomes))

    body_gate = f'''
  {text(960, 105, "THE RESTOCK GATE", 48, "#ffffff", "700")}
  {box(720, 240, 480, 100, "CAN IT BE SOLD AS NEW...", "#f0a33a")}
  {line(860, 340, 520, 540)}
  {line(1060, 340, 1400, 540)}
  {box(320, 540, 400, 100, "YES: RESTOCK")}
  {box(1200, 540, 400, 100, "NO: INSPECT")}
  {line(1400, 640, 1400, 790)}
  {box(1180, 790, 440, 100, "REPAIR / RESELL / LIQUIDATE")}
  {text(960, 980, "A SIMPLE DECISION CAN CREATE MANY DOWNSTREAM ROUTES", 28, "#8794a3")}
'''
    files.append(write_svg(asset_dir / "a007_restock_gate.svg", "A007 restock gate", body_gate))

    body_unrecoverable = f'''
  {text(960, 105, "WHEN VALUE CANNOT BE RECOVERED", 46, "#ffffff", "700")}
  {box(760, 220, 400, 90, "UNRECOVERABLE ITEM", "#f0a33a")}
  {line(960, 310, 520, 520)}
  {line(960, 310, 820, 520)}
  {line(960, 310, 1120, 520)}
  {line(960, 310, 1420, 520)}
  {box(320, 520, 390, 100, "PARTS")}
  {box(620, 520, 390, 100, "DONATION")}
  {box(920, 520, 390, 100, "RECYCLING")}
  {box(1220, 520, 390, 100, "DISPOSAL")}
  {text(960, 840, "This section should feel slower, heavier, and more reflective.", 30, "#b8c7d9")}
  {text(960, 930, "NO UNSUPPORTED NUMBERS. NO FAKE LABELS. NO BRANDS.", 26, "#8794a3")}
'''
    files.append(write_svg(asset_dir / "a007_unrecoverable_outcomes.svg", "A007 unrecoverable outcomes", body_unrecoverable))

    return files


def get_target_decisions(acquisition_data: dict, all_internal: bool) -> list[dict]:
    decisions = acquisition_data["acquisition_plan"]["decisions"]

    targets = [
        decision for decision in decisions
        if decision["acquisition_status"] == "ready_for_internal_production"
    ]

    if all_internal:
        return targets

    return [
        decision for decision in targets
        if decision["is_first_build"]
    ]


def generate_asset(decision: dict, output_dir: Path) -> dict:
    asset_id = decision["asset_id"]
    asset_dir = output_dir / asset_id
    asset_dir.mkdir(parents=True, exist_ok=True)

    if asset_id == "A002":
        output_files = create_a002(asset_dir)
        production_status = "internal_asset_ready"
    elif asset_id == "A004":
        output_files = create_a004(asset_dir)
        production_status = "internal_asset_ready"
    elif asset_id == "A007":
        output_files = create_a007(asset_dir)
        production_status = "internal_asset_ready"
    else:
        output_files = []
        production_status = "planned_not_generated_in_v0"

    return {
        "asset_id": asset_id,
        "asset_type": decision["asset_type"],
        "production_method": decision["production_method"],
        "production_status": production_status,
        "output_folder": get_relative_path(asset_dir),
        "output_files": output_files,
        "source_manifest_folder": decision["folder"]
    }


def build_output(
    channel: str,
    acquisition_data: dict,
    acquisition_path: Path,
    generated_assets: list[dict]
) -> dict:
    ready_assets = [
        asset for asset in generated_assets
        if asset["production_status"] == "internal_asset_ready"
    ]

    return {
        "agent": "internal_visual_production",
        "version": "1.0",
        "channel": channel,
        "status": "internal_assets_ready" if ready_assets else "blocked",
        "internal_visual_assets": {
            "assets": generated_assets
        },
        "summary": {
            "target_asset_count": len(generated_assets),
            "ready_asset_count": len(ready_assets),
            "next_agent": "internal_visual_qa"
        },
        "source": {
            "source_agents": [
                "visual_asset_acquisition"
            ],
            "visual_asset_acquisition_reference": get_relative_path(acquisition_path)
        },
        "metadata": {
            "next_agent": "internal_visual_qa"
        }
    }


def dry_run(acquisition_data: dict, all_internal: bool) -> None:
    targets = get_target_decisions(
        acquisition_data=acquisition_data,
        all_internal=all_internal
    )

    print("Internal Visual Production Agent dry-run completed.")
    print(f"Channel: {acquisition_data['channel']}")
    print(f"Target internal assets: {len(targets)}")

    for target in targets:
        print(
            f"- {target['asset_id']} | "
            f"{target['asset_type']} | "
            f"{target['production_method']} | "
            f"first_build={target['is_first_build']}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create first internal visual assets from acquisition-ready internal graphic assets."
    )

    parser.add_argument(
        "--channel",
        default=DEFAULT_CHANNEL,
        help="Channel name. Default: hiddenova"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate inputs without creating internal visual files."
    )

    parser.add_argument(
        "--all-internal",
        action="store_true",
        help="Generate all internal-ready assets instead of first-build assets only."
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    load_dotenv(PROJECT_ROOT / ".env")

    acquisition_path = get_acquisition_latest_path(args.channel)
    acquisition_data = load_json(acquisition_path)

    if args.dry_run:
        dry_run(
            acquisition_data=acquisition_data,
            all_internal=args.all_internal
        )
        return

    output_dir = create_output_dir(args.channel)

    targets = get_target_decisions(
        acquisition_data=acquisition_data,
        all_internal=args.all_internal
    )

    generated_assets = [
        generate_asset(
            decision=decision,
            output_dir=output_dir
        )
        for decision in targets
    ]

    final_output = build_output(
        channel=args.channel,
        acquisition_data=acquisition_data,
        acquisition_path=acquisition_path,
        generated_assets=generated_assets
    )

    schema = load_schema()
    validate(instance=final_output, schema=schema)

    latest_path = save_output(
        channel=final_output["channel"],
        data=final_output
    )

    print("Internal Visual Production Agent completed successfully.")
    print(f"Output saved to: {latest_path}")


if __name__ == "__main__":
    main()
