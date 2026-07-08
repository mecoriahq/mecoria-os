import argparse
import json
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from jsonschema import validate
from PIL import Image, ImageDraw, ImageFont

from output import save_output


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent.parent

DEFAULT_CHANNEL = "hiddenova"
WIDTH = 1920
HEIGHT = 1080


COLORS = {
    "bg": (12, 16, 21),
    "panel": (20, 29, 38),
    "panel_alt": (15, 21, 28),
    "white": (244, 247, 251),
    "muted": (140, 153, 170),
    "blue": (74, 163, 255),
    "amber": (240, 163, 58),
    "green": (95, 210, 145),
    "red": (230, 90, 90)
}


def load_json(file_path: Path) -> dict:
    if not file_path.exists():
        raise FileNotFoundError(f"Required file not found: {file_path}")

    return json.loads(file_path.read_text(encoding="utf-8"))


def load_schema() -> dict:
    return load_json(BASE_DIR / "schema.json")


def get_internal_visual_production_latest_path(channel: str) -> Path:
    return PROJECT_ROOT / "agents" / "internal_visual_production" / "output" / channel.lower() / "latest.json"


def get_internal_visual_qa_latest_path(channel: str) -> Path:
    return PROJECT_ROOT / "agents" / "internal_visual_qa" / "output" / channel.lower() / "latest.json"


def get_relative_path(path: Path) -> str:
    return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")


def create_output_dir(channel: str) -> Path:
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    output_dir = (
        BASE_DIR
        / "output"
        / channel.lower()
        / "renders"
        / timestamp
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def get_font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    font_candidates = []

    if bold:
        font_candidates.extend([
            Path("C:/Windows/Fonts/arialbd.ttf"),
            Path("C:/Windows/Fonts/segoeuib.ttf")
        ])

    font_candidates.extend([
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/segoeui.ttf")
    ])

    for font_path in font_candidates:
        if font_path.exists():
            return ImageFont.truetype(str(font_path), size=size)

    return ImageFont.load_default()


def new_canvas() -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT), COLORS["bg"])
    draw = ImageDraw.Draw(image)

    for y in range(HEIGHT):
        shade = int(10 + (y / HEIGHT) * 18)
        draw.line([(0, y), (WIDTH, y)], fill=(shade, shade + 4, shade + 9))

    return image


def draw_center_text(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, size: int, fill=None, bold: bool = False) -> None:
    fill = fill or COLORS["white"]
    font = get_font(size, bold=bold)
    bbox = draw.textbbox((0, 0), text, font=font)
    width = bbox[2] - bbox[0]
    draw.text((xy[0] - width // 2, xy[1]), text, font=font, fill=fill)


def draw_node(draw: ImageDraw.ImageDraw, x: int, y: int, label: str) -> None:
    draw.ellipse((x - 44, y - 44, x + 44, y + 44), fill=COLORS["panel"], outline=COLORS["blue"], width=4)
    draw.ellipse((x - 11, y - 11, x + 11, y + 11), fill=COLORS["amber"])
    draw_center_text(draw, (x, y + 62), label, 26, COLORS["white"])


def draw_line(draw: ImageDraw.ImageDraw, start: tuple[int, int], end: tuple[int, int], fill=None, width: int = 5) -> None:
    fill = fill or COLORS["blue"]
    draw.line([start, end], fill=fill, width=width)


def draw_box(draw: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int, label: str, outline=None) -> None:
    outline = outline or COLORS["blue"]
    draw.rounded_rectangle((x, y, x + w, y + h), radius=18, fill=COLORS["panel"], outline=outline, width=4)
    draw_center_text(draw, (x + w // 2, y + h // 2 - 16), label, 30, COLORS["white"], bold=True)


def save_png(image: Image.Image, path: Path) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG", optimize=True)

    return {
        "filename": path.name,
        "relative_path": get_relative_path(path),
        "format": "png",
        "size_bytes": path.stat().st_size,
        "resolution": f"{WIDTH}x{HEIGHT}"
    }


def render_a002(filename: str, output_path: Path) -> dict:
    image = new_canvas()
    draw = ImageDraw.Draw(image)

    if "expanded" in filename:
        draw_center_text(draw, (960, 105), "ONE BOX BECOMES MANY POSSIBLE ROUTES", 48, bold=True)
        draw_line(draw, (330, 520), (650, 520))
        for point in [(960, 280), (960, 430), (960, 580), (960, 730)]:
            draw_line(draw, (650, 520), point)
        draw_line(draw, (960, 430), (1280, 340), COLORS["amber"], 4)
        draw_line(draw, (960, 580), (1280, 640), COLORS["amber"], 4)

        nodes = [
            (330, 520, "HOME"),
            (650, 520, "LOCAL HUB"),
            (960, 280, "RESTOCK"),
            (960, 430, "REPAIR"),
            (960, 580, "LIQUIDATE"),
            (960, 730, "RECYCLE"),
            (1280, 340, "RESELLER"),
            (1280, 640, "NEW CUSTOMER")
        ]
    elif "loop" in filename:
        draw_center_text(draw, (960, 105), "THE RETURN ECONOMY IS A LOOP", 50, bold=True)
        draw.ellipse((520, 260, 1400, 820), outline=COLORS["blue"], width=6)
        draw.arc((600, 340, 1320, 760), start=190, end=350, fill=COLORS["amber"], width=5)

        nodes = [
            (520, 540, "RETURN"),
            (760, 340, "INSPECT"),
            (1160, 340, "REFURBISH"),
            (1400, 540, "RESELL"),
            (1160, 760, "NEW BUYER"),
            (760, 760, "RECYCLE")
        ]
    else:
        draw_center_text(draw, (960, 105), "A RETURN ENTERS THE HIDDEN NETWORK", 48, bold=True)
        draw_line(draw, (420, 520), (760, 520))
        draw_line(draw, (760, 520), (1040, 360))
        draw_line(draw, (760, 520), (1040, 520))
        draw_line(draw, (760, 520), (1040, 680))

        nodes = [
            (420, 520, "HOME"),
            (760, 520, "CARRIER HUB"),
            (1040, 360, "RETURN CENTER"),
            (1040, 520, "INSPECTION"),
            (1040, 680, "SECONDARY MARKET")
        ]

    for x, y, label in nodes:
        draw_node(draw, x, y, label)

    draw_center_text(draw, (960, 945), "Abstract route map - no real addresses, brands, or exact routes", 28, COLORS["muted"])

    return save_png(image, output_path)


def render_a004(filename: str, output_path: Path) -> dict:
    image = new_canvas()
    draw = ImageDraw.Draw(image)

    cards = {
        "hook": ("WHAT HAPPENS NOW?", "Behind every convenient return is a hidden system."),
        "conclusion": ("CAN THIS PRODUCT BEGIN AGAIN?", "A returned box enters a maze of decisions."),
        "cta": ("THE HIDDEN SYSTEMS BEHIND EVERYDAY LIFE", "Subscribe to Hiddenova.")
    }

    key = "hook"

    if "conclusion" in filename:
        key = "conclusion"
    elif "cta" in filename:
        key = "cta"

    headline, subline = cards[key]

    draw.rounded_rectangle((260, 330, 1660, 640), radius=30, fill=COLORS["panel_alt"], outline=(38, 53, 69), width=3)
    draw.line((360, 690, 1560, 690), fill=COLORS["blue"], width=4)
    draw_center_text(draw, (960, 455), headline, 60, COLORS["white"], bold=True)
    draw_center_text(draw, (960, 545), subline, 34, (184, 199, 217))
    draw_center_text(draw, (960, 805), "HIDDENOVA", 30, COLORS["amber"], bold=True)

    return save_png(image, output_path)


def render_a007(filename: str, output_path: Path) -> dict:
    image = new_canvas()
    draw = ImageDraw.Draw(image)

    if "restock" in filename:
        draw_center_text(draw, (960, 105), "THE RESTOCK GATE", 52, bold=True)
        draw_box(draw, 720, 240, 480, 100, "CAN IT BE SOLD AS NEW?", COLORS["amber"])
        draw_line(draw, (860, 340), (520, 540))
        draw_line(draw, (1060, 340), (1400, 540))
        draw_box(draw, 320, 540, 400, 100, "YES: RESTOCK", COLORS["green"])
        draw_box(draw, 1200, 540, 400, 100, "NO: INSPECT", COLORS["red"])
        draw_line(draw, (1400, 640), (1400, 790))
        draw_box(draw, 1180, 790, 440, 100, "REPAIR / RESELL / LIQUIDATE", COLORS["blue"])
        draw_center_text(draw, (960, 960), "A SIMPLE DECISION CAN CREATE MANY DOWNSTREAM ROUTES", 28, COLORS["muted"])
    elif "unrecoverable" in filename:
        draw_center_text(draw, (960, 105), "WHEN VALUE CANNOT BE RECOVERED", 50, bold=True)
        draw_box(draw, 760, 220, 400, 90, "UNRECOVERABLE ITEM", COLORS["amber"])
        for point in [(520, 520), (820, 520), (1120, 520), (1420, 520)]:
            draw_line(draw, (960, 310), point)
        draw_box(draw, 320, 520, 390, 100, "PARTS")
        draw_box(draw, 620, 520, 390, 100, "DONATION")
        draw_box(draw, 920, 520, 390, 100, "RECYCLING")
        draw_box(draw, 1220, 520, 390, 100, "DISPOSAL")
        draw_center_text(draw, (960, 840), "This section should feel slower, heavier, and more reflective.", 30, (184, 199, 217))
        draw_center_text(draw, (960, 930), "NO UNSUPPORTED NUMBERS. NO FAKE LABELS. NO BRANDS.", 26, COLORS["muted"])
    else:
        draw_center_text(draw, (960, 105), "WHAT CAN HAPPEN TO A RETURNED PRODUCT?", 48, bold=True)
        draw_box(draw, 760, 230, 400, 90, "RETURNED ITEM", COLORS["amber"])
        for point in [(460, 500), (760, 500), (1060, 500), (1360, 500)]:
            draw_line(draw, (960, 320), point)
        draw_box(draw, 260, 500, 390, 90, "RESTOCK")
        draw_box(draw, 560, 500, 390, 90, "INSPECT")
        draw_box(draw, 860, 500, 390, 90, "REPAIR")
        draw_box(draw, 1160, 500, 390, 90, "LIQUIDATE")
        draw_line(draw, (760, 590), (560, 760))
        draw_line(draw, (1060, 590), (960, 760))
        draw_line(draw, (1360, 590), (1360, 760))
        draw_box(draw, 360, 760, 390, 90, "RECYCLE")
        draw_box(draw, 760, 760, 390, 90, "RESELL")
        draw_box(draw, 1160, 760, 390, 90, "DISPOSE")
        draw_center_text(draw, (960, 960), "OUTCOMES VARY BY ITEM, POLICY, AND LOCAL RULES", 28, COLORS["muted"])

    return save_png(image, output_path)


def render_asset_file(asset_id: str, source_file: dict, output_dir: Path) -> dict:
    source_filename = source_file["filename"]
    png_filename = source_filename.replace(".svg", ".png")
    output_path = output_dir / asset_id / png_filename

    if asset_id == "A002":
        return render_a002(source_filename, output_path)

    if asset_id == "A004":
        return render_a004(source_filename, output_path)

    if asset_id == "A007":
        return render_a007(source_filename, output_path)

    raise ValueError(f"Unsupported internal visual asset: {asset_id}")


def render_assets(production_data: dict, output_dir: Path) -> list[dict]:
    rendered_assets = []

    for asset in production_data["internal_visual_assets"]["assets"]:
        asset_id = asset["asset_id"]

        rendered_files = [
            render_asset_file(
                asset_id=asset_id,
                source_file=source_file,
                output_dir=output_dir
            )
            for source_file in asset["output_files"]
        ]

        rendered_assets.append({
            "asset_id": asset_id,
            "asset_type": asset["asset_type"],
            "source_output_folder": asset["output_folder"],
            "rendered_output_folder": get_relative_path(output_dir / asset_id),
            "source_files": asset["output_files"],
            "rendered_files": rendered_files,
            "status": "rendered"
        })

    return rendered_assets


def build_output(
    channel: str,
    production_data: dict,
    production_path: Path,
    visual_qa_data: dict,
    visual_qa_path: Path,
    rendered_assets: list[dict]
) -> dict:
    rendered_file_count = sum(
        len(asset["rendered_files"])
        for asset in rendered_assets
    )

    return {
        "agent": "internal_visual_render",
        "version": "1.0",
        "channel": channel,
        "status": "renders_ready",
        "rendered_visual_assets": {
            "assets": rendered_assets
        },
        "summary": {
            "asset_count": len(rendered_assets),
            "rendered_file_count": rendered_file_count,
            "next_agent": "internal_visual_render_qa"
        },
        "source": {
            "source_agents": [
                "internal_visual_production",
                "internal_visual_qa"
            ],
            "internal_visual_production_reference": get_relative_path(production_path),
            "internal_visual_qa_reference": get_relative_path(visual_qa_path),
            "internal_visual_qa_status": visual_qa_data["status"]
        },
        "metadata": {
            "next_agent": "internal_visual_render_qa"
        }
    }


def dry_run(production_data: dict, visual_qa_data: dict) -> None:
    if visual_qa_data.get("status") != "approved":
        raise ValueError("Internal Visual QA is not approved.")

    assets = production_data["internal_visual_assets"]["assets"]
    file_count = sum(len(asset["output_files"]) for asset in assets)

    print("Internal Visual Render Agent dry-run completed.")
    print(f"Channel: {production_data['channel']}")
    print(f"Assets to render: {len(assets)}")
    print(f"SVG files to render as PNG: {file_count}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render internal visual assets into PNG files."
    )

    parser.add_argument(
        "--channel",
        default=DEFAULT_CHANNEL,
        help="Channel name. Default: hiddenova"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate inputs without rendering PNG files."
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    load_dotenv(PROJECT_ROOT / ".env")

    production_path = get_internal_visual_production_latest_path(args.channel)
    visual_qa_path = get_internal_visual_qa_latest_path(args.channel)

    production_data = load_json(production_path)
    visual_qa_data = load_json(visual_qa_path)

    if visual_qa_data.get("status") != "approved":
        raise ValueError("Internal Visual QA is not approved.")

    if args.dry_run:
        dry_run(
            production_data=production_data,
            visual_qa_data=visual_qa_data
        )
        return

    output_dir = create_output_dir(args.channel)

    rendered_assets = render_assets(
        production_data=production_data,
        output_dir=output_dir
    )

    final_output = build_output(
        channel=args.channel,
        production_data=production_data,
        production_path=production_path,
        visual_qa_data=visual_qa_data,
        visual_qa_path=visual_qa_path,
        rendered_assets=rendered_assets
    )

    schema = load_schema()
    validate(instance=final_output, schema=schema)

    latest_path = save_output(
        channel=final_output["channel"],
        data=final_output
    )

    print("Internal Visual Render Agent completed successfully.")
    print(f"Output saved to: {latest_path}")


if __name__ == "__main__":
    main()
