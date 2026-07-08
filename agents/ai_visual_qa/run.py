import argparse
import json
from pathlib import Path

from dotenv import load_dotenv
from jsonschema import validate
from PIL import Image

from output import save_output


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent.parent

DEFAULT_CHANNEL = "hiddenova"
MIN_WIDTH = 1024
MIN_HEIGHT = 768
MIN_SIZE_BYTES = 50000
TARGET_VIDEO_ASPECT_RATIO = 16 / 9


def load_json(file_path: Path) -> dict:
    if not file_path.exists():
        raise FileNotFoundError(f"Required file not found: {file_path}")

    return json.loads(file_path.read_text(encoding="utf-8-sig"))


def load_schema() -> dict:
    return load_json(BASE_DIR / "schema.json")


def get_ai_visual_generation_latest_path(channel: str) -> Path:
    return PROJECT_ROOT / "agents" / "ai_visual_generation" / "output" / channel.lower() / "latest.json"


def get_relative_path(path: Path) -> str:
    return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")


def check_image(image_item: dict) -> dict:
    image_path = PROJECT_ROOT / image_item["relative_path"]
    issues = []
    warnings = []

    if not image_path.exists():
        return {
            "insert_id": image_item["insert_id"],
            "relative_path": image_item["relative_path"],
            "status": "failed",
            "approved": False,
            "width": None,
            "height": None,
            "format": None,
            "size_bytes": 0,
            "aspect_ratio": None,
            "issues": ["Image file does not exist."],
            "warnings": []
        }

    size_bytes = image_path.stat().st_size

    if size_bytes < MIN_SIZE_BYTES:
        issues.append("Image file size is too small.")

    with Image.open(image_path) as image:
        width, height = image.size
        image_format = image.format

    if width < MIN_WIDTH:
        issues.append(f"Image width below minimum: {width}")

    if height < MIN_HEIGHT:
        issues.append(f"Image height below minimum: {height}")

    if width <= height:
        issues.append("Image is not landscape-oriented.")

    if image_format not in {"PNG", "JPEG", "WEBP"}:
        issues.append(f"Unsupported image format: {image_format}")

    aspect_ratio = width / height

    if abs(aspect_ratio - TARGET_VIDEO_ASPECT_RATIO) > 0.15:
        warnings.append("Image will need crop/scale treatment for 16:9 video timeline.")

    approved = len(issues) == 0

    return {
        "insert_id": image_item["insert_id"],
        "section_hint": image_item["section_hint"],
        "visual_role": image_item["visual_role"],
        "relative_path": image_item["relative_path"],
        "status": "approved" if approved else "failed",
        "approved": approved,
        "width": width,
        "height": height,
        "format": image_format,
        "size_bytes": size_bytes,
        "aspect_ratio": round(aspect_ratio, 3),
        "issues": issues,
        "warnings": warnings
    }


def build_output(channel: str, generation_path: Path, generation_data: dict) -> dict:
    if generation_data.get("status") != "images_ready":
        raise ValueError("AI Visual Generation output is not images_ready.")

    generated_images = generation_data.get("generated_images", [])

    if not generated_images:
        raise ValueError("AI Visual Generation output has no generated images.")

    image_checks = [
        check_image(image_item)
        for image_item in generated_images
    ]

    approved_count = sum(1 for item in image_checks if item["approved"])
    failed_count = len(image_checks) - approved_count
    warning_count = sum(len(item["warnings"]) for item in image_checks)

    status = "approved" if failed_count == 0 else "needs_revision"

    return {
        "agent": "ai_visual_qa",
        "version": "1.0",
        "channel": channel,
        "status": status,
        "summary": {
            "generated_image_count": len(generated_images),
            "approved_image_count": approved_count,
            "failed_image_count": failed_count,
            "warning_count": warning_count,
            "manual_visual_review": "founder_approved",
            "note": "Technical QA passed if status is approved. Founder has already approved visual style qualitatively."
        },
        "image_checks": image_checks,
        "readiness": {
            "images_ready_for_hybrid_assembly": status == "approved",
            "manual_style_approved": True,
            "blocking_notes": [] if status == "approved" else [
                "Some AI visual inserts failed technical QA."
            ]
        },
        "source": {
            "source_agent": "ai_visual_generation",
            "generation_reference": get_relative_path(generation_path),
            "video_title": generation_data["source"]["video_title"]
        },
        "metadata": {
            "next_agent": "hybrid_video_assembly"
        }
    }


def dry_run(final_output: dict) -> None:
    print("AI Visual QA Agent dry-run completed.")
    print(f"Channel: {final_output['channel']}")
    print(f"Status: {final_output['status']}")
    print(f"Generated images: {final_output['summary']['generated_image_count']}")
    print(f"Approved images: {final_output['summary']['approved_image_count']}")
    print(f"Failed images: {final_output['summary']['failed_image_count']}")
    print(f"Warnings: {final_output['summary']['warning_count']}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run technical QA for generated AI visual inserts."
    )

    parser.add_argument(
        "--channel",
        default=DEFAULT_CHANNEL,
        help="Channel name. Default: hiddenova"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate without saving output."
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    channel = args.channel.lower()

    load_dotenv(PROJECT_ROOT / ".env")

    generation_path = get_ai_visual_generation_latest_path(channel)
    generation_data = load_json(generation_path)

    final_output = build_output(
        channel=channel,
        generation_path=generation_path,
        generation_data=generation_data
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

    print("AI Visual QA Agent completed successfully.")
    print(f"Status: {final_output['status']}")
    print(f"Approved images: {final_output['summary']['approved_image_count']}")
    print(f"Failed images: {final_output['summary']['failed_image_count']}")
    print(f"Warnings: {final_output['summary']['warning_count']}")
    print(f"Output saved to: {latest_path}")


if __name__ == "__main__":
    main()
