import argparse
import base64
import json
import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from jsonschema import validate
from openai import OpenAI

from output import save_output


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent.parent

DEFAULT_CHANNEL = "hiddenova"
DEFAULT_MODEL = "gpt-image-1.5"
DEFAULT_SIZE = "1536x1024"
DEFAULT_QUALITY = "medium"
DEFAULT_OUTPUT_FORMAT = "png"


def load_json(file_path: Path) -> dict:
    if not file_path.exists():
        raise FileNotFoundError(f"Required file not found: {file_path}")

    return json.loads(file_path.read_text(encoding="utf-8-sig"))


def load_schema() -> dict:
    return load_json(BASE_DIR / "schema.json")


def get_plan_latest_path(channel: str) -> Path:
    return PROJECT_ROOT / "agents" / "ai_visual_insert_plan" / "output" / channel.lower() / "latest.json"


def get_relative_path(path: Path) -> str:
    return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")


def get_image_output_dir(channel: str) -> Path:
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    output_dir = BASE_DIR / "output" / channel.lower() / "images" / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def select_plan_items(plan_data: dict, limit: int | None) -> list[dict]:
    items = plan_data["ai_visual_insert_plan"]["items"]
    planned_items = [
        item for item in items
        if item.get("status") == "planned"
    ]

    if limit is not None:
        return planned_items[:limit]

    return planned_items


def build_full_prompt(item: dict, style_rules: list[str], negative_rules: list[str]) -> str:
    style_text = ", ".join(style_rules)
    negative_text = ", ".join(negative_rules)

    return (
        f"{item['prompt']}\n\n"
        f"Global style rules: {style_text}.\n"
        f"Must avoid: {negative_text}.\n"
        "Output must be a cinematic 16:9 documentary still that can be used as a short visual insert in a YouTube documentary."
    )


def generate_image(
    client: OpenAI,
    model: str,
    prompt: str,
    size: str,
    quality: str,
    output_format: str
) -> bytes:
    response = client.images.generate(
        model=model,
        prompt=prompt,
        n=1,
        size=size,
        quality=quality,
        output_format=output_format
    )

    if not response.data:
        raise ValueError("Image generation returned no data.")

    image_b64 = response.data[0].b64_json

    if not image_b64:
        raise ValueError("Image generation response did not include b64_json.")

    return base64.b64decode(image_b64)


def generate_images(
    channel: str,
    plan_data: dict,
    selected_items: list[dict],
    model: str,
    size: str,
    quality: str,
    output_format: str
) -> tuple[list[dict], Path]:
    client = OpenAI()
    output_dir = get_image_output_dir(channel)

    style_rules = plan_data["ai_visual_insert_plan"]["style_rules"]
    negative_rules = plan_data["ai_visual_insert_plan"]["negative_rules"]

    generated_images = []

    for item in selected_items:
        insert_id = item["insert_id"]
        filename = f"{insert_id.lower()}_{item['section_hint'].replace(' ', '_')}.{output_format}"
        image_path = output_dir / filename

        full_prompt = build_full_prompt(
            item=item,
            style_rules=style_rules,
            negative_rules=negative_rules
        )

        print(f"Generating {insert_id}: {item['section_hint']}", flush=True)

        image_bytes = generate_image(
            client=client,
            model=model,
            prompt=full_prompt,
            size=size,
            quality=quality,
            output_format=output_format
        )

        image_path.write_bytes(image_bytes)

        generated_images.append({
            "insert_id": insert_id,
            "sequence": item["sequence"],
            "section_hint": item["section_hint"],
            "visual_role": item["visual_role"],
            "target_duration_seconds": item["target_duration_seconds"],
            "prompt": item["prompt"],
            "negative_prompt": item["negative_prompt"],
            "model": model,
            "size": size,
            "quality": quality,
            "output_format": output_format,
            "filename": image_path.name,
            "relative_path": get_relative_path(image_path),
            "status": "generated_pending_qa"
        })

    return generated_images, output_dir


def build_output(
    channel: str,
    plan_path: Path,
    plan_data: dict,
    selected_items: list[dict],
    generated_images: list[dict],
    mode: str,
    model: str,
    size: str,
    quality: str,
    output_format: str,
    output_dir: Path | None = None
) -> dict:
    return {
        "agent": "ai_visual_generation",
        "version": "1.0",
        "channel": channel,
        "status": "dry_run_ready" if mode == "dry_run" else "images_ready",
        "summary": {
            "planned_insert_count": len(plan_data["ai_visual_insert_plan"]["items"]),
            "selected_insert_count": len(selected_items),
            "generated_image_count": len(generated_images),
            "model": model,
            "size": size,
            "quality": quality,
            "output_format": output_format,
            "output_dir": get_relative_path(output_dir) if output_dir else None,
            "next_agent": "ai_visual_qa"
        },
        "generated_images": generated_images,
        "source": {
            "source_agent": "ai_visual_insert_plan",
            "plan_reference": get_relative_path(plan_path),
            "video_title": plan_data["source"]["video_title"]
        },
        "metadata": {
            "next_agent": "ai_visual_qa"
        }
    }


def dry_run(final_output: dict, selected_items: list[dict]) -> None:
    print("AI Visual Generation Agent dry-run completed.")
    print(f"Channel: {final_output['channel']}")
    print(f"Status: {final_output['status']}")
    print(f"Selected inserts: {final_output['summary']['selected_insert_count']}")
    print(f"Model: {final_output['summary']['model']}")
    print(f"Size: {final_output['summary']['size']}")
    print(f"Quality: {final_output['summary']['quality']}")
    print("Generation queue:")

    for item in selected_items:
        print(
            f"- {item['insert_id']} | {item['section_hint']} | "
            f"{item['target_duration_seconds']}s | {item['visual_role']}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate AI cinematic visual inserts from the AI Visual Insert Plan."
    )

    parser.add_argument(
        "--channel",
        default=DEFAULT_CHANNEL,
        help="Channel name. Default: hiddenova"
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of inserts to generate. Useful for cost-controlled tests."
    )

    parser.add_argument(
        "--model",
        default=os.getenv("OPENAI_IMAGE_MODEL", DEFAULT_MODEL),
        help="Image generation model."
    )

    parser.add_argument(
        "--size",
        default=os.getenv("OPENAI_IMAGE_SIZE", DEFAULT_SIZE),
        help="Image size."
    )

    parser.add_argument(
        "--quality",
        default=os.getenv("OPENAI_IMAGE_QUALITY", DEFAULT_QUALITY),
        help="Image quality."
    )

    parser.add_argument(
        "--output-format",
        default=os.getenv("OPENAI_IMAGE_OUTPUT_FORMAT", DEFAULT_OUTPUT_FORMAT),
        help="Image output format."
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate generation queue without calling the image API."
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    channel = args.channel.lower()

    load_dotenv(PROJECT_ROOT / ".env")

    plan_path = get_plan_latest_path(channel)
    plan_data = load_json(plan_path)

    selected_items = select_plan_items(
        plan_data=plan_data,
        limit=args.limit
    )

    if not selected_items:
        raise ValueError("No planned AI visual inserts selected.")

    if args.dry_run:
        final_output = build_output(
            channel=channel,
            plan_path=plan_path,
            plan_data=plan_data,
            selected_items=selected_items,
            generated_images=[],
            mode="dry_run",
            model=args.model,
            size=args.size,
            quality=args.quality,
            output_format=args.output_format,
            output_dir=None
        )

        schema = load_schema()
        validate(instance=final_output, schema=schema)

        dry_run(
            final_output=final_output,
            selected_items=selected_items
        )
        return

    generated_images, output_dir = generate_images(
        channel=channel,
        plan_data=plan_data,
        selected_items=selected_items,
        model=args.model,
        size=args.size,
        quality=args.quality,
        output_format=args.output_format
    )

    final_output = build_output(
        channel=channel,
        plan_path=plan_path,
        plan_data=plan_data,
        selected_items=selected_items,
        generated_images=generated_images,
        mode="generate",
        model=args.model,
        size=args.size,
        quality=args.quality,
        output_format=args.output_format,
        output_dir=output_dir
    )

    schema = load_schema()
    validate(instance=final_output, schema=schema)

    latest_path = save_output(
        channel=final_output["channel"],
        data=final_output
    )

    print("AI Visual Generation Agent completed successfully.")
    print(f"Generated images: {len(generated_images)}")
    print(f"Output directory: {output_dir}")
    print(f"Output saved to: {latest_path}")


if __name__ == "__main__":
    main()
