import argparse
import base64
import json
import os
import re
import shutil
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont, ImageOps


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent.parent

DEFAULT_CHANNEL = "hiddenova"
DEFAULT_IMAGE_MODEL = "gpt-image-1"
DEFAULT_TEXT_MODEL = "gpt-5.5"
DEFAULT_IMAGE_COUNT = 8


def load_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Required file not found: {path}")

    return json.loads(path.read_text(encoding="utf-8-sig"))


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=True),
        encoding="utf-8"
    )


def relative_path(path: Path) -> str:
    return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")


def get_context_path(channel: str, video_id: str) -> Path:
    return (
        PROJECT_ROOT
        / "records"
        / "run_contexts"
        / channel
        / f"{video_id}.json"
    )


def get_context_input_dir(channel: str, video_id: str) -> Path:
    return (
        PROJECT_ROOT
        / "records"
        / "run_contexts"
        / channel
        / video_id
        / "inputs"
    )


def get_output_dir(channel: str, video_id: str) -> Path:
    return BASE_DIR / "output" / channel / video_id


def get_source_defaults(channel: str, video_id: str) -> dict[str, Path]:
    return {
        "script": (
            PROJECT_ROOT
            / "agents"
            / "script"
            / "output"
            / channel
            / "latest.json"
        ),
        "seo": (
            PROJECT_ROOT
            / "agents"
            / "seo"
            / "output"
            / channel
            / "latest.json"
        ),
        "qa": (
            PROJECT_ROOT
            / "agents"
            / "qa"
            / "output"
            / channel
            / "latest.json"
        ),
        "visual_asset_plan": (
            PROJECT_ROOT
            / "agents"
            / "visual_asset_plan"
            / "output"
            / channel
            / "latest.json"
        ),
        "thumbnail_strategy": (
            PROJECT_ROOT
            / "agents"
            / "thumbnail_strategy"
            / "output"
            / channel
            / "latest.json"
        ) if (
            PROJECT_ROOT
            / "agents"
            / "thumbnail_strategy"
            / "output"
            / channel
            / "latest.json"
        ).exists() else max(
            (
                PROJECT_ROOT
                / "records"
                / "content"
                / channel
            ).glob("*thumbnail_strategy_checkpoint.json"),
            key=lambda item: item.stat().st_mtime
        ),
        "stock_manifest": (
            PROJECT_ROOT
            / "records"
            / "assets"
            / channel
            / f"{video_id}_stock_footage_manifest.json"
        ),
        "audio_assembly": (
            PROJECT_ROOT
            / "agents"
            / "audio_assembly"
            / "output"
            / channel
            / "latest.json"
        )
    }


def create_context(
    channel: str,
    video_id: str,
    refresh: bool
) -> dict:
    context_path = get_context_path(channel, video_id)

    if context_path.exists() and not refresh:
        return load_json(context_path)

    input_dir = get_context_input_dir(channel, video_id)
    input_dir.mkdir(parents=True, exist_ok=True)

    sources = {}

    for key, source_path in get_source_defaults(channel, video_id).items():
        if not source_path.exists():
            raise FileNotFoundError(
                f"Context source missing: {key} -> {source_path}"
            )

        snapshot_path = input_dir / f"{key}.json"
        shutil.copy2(source_path, snapshot_path)
        sources[key] = relative_path(snapshot_path)

    script_data = load_json(PROJECT_ROOT / sources["script"])
    title = script_data.get("script", {}).get("title", "").strip()

    if not title:
        raise ValueError("Script title is missing.")

    context = {
        "schema_version": "1.0",
        "channel": channel,
        "video_id": video_id,
        "run_id": f"{channel}_{video_id}_v1",
        "status": "context_ready",
        "topic_title": title,
        "sources": sources,
        "outputs": {},
        "quality_gates": {
            "require_ai_visuals": True,
            "minimum_ai_insert_count": DEFAULT_IMAGE_COUNT,
            "require_thumbnail": True,
            "require_founder_review": True
        }
    }

    save_json(context_path, context)
    return context


def load_context_source(context: dict, key: str) -> tuple[Path, dict]:
    source_reference = context["sources"][key]
    source_path = PROJECT_ROOT / source_reference
    return source_path, load_json(source_path)


def find_text_value(data, preferred_keys: set[str]) -> str | None:
    if isinstance(data, dict):
        for key, value in data.items():
            normalized_key = key.lower().replace("-", "_")

            if normalized_key in preferred_keys and isinstance(value, str):
                text = value.strip()

                if text:
                    return text

        for value in data.values():
            result = find_text_value(value, preferred_keys)

            if result:
                return result

    if isinstance(data, list):
        for value in data:
            result = find_text_value(value, preferred_keys)

            if result:
                return result

    return None


def normalize_overlay_text(text: str | None) -> str | None:
    if not text:
        return None

    words = re.findall(r"[A-Za-z0-9]+", text.upper())

    if not 1 <= len(words) <= 4:
        return None

    return " ".join(words)


def get_thumbnail_hint(thumbnail_strategy_data: dict) -> str | None:
    candidate = find_text_value(
        thumbnail_strategy_data,
        {
            "preferred_text",
            "preferred_thumbnail_text",
            "thumbnail_text",
            "text_overlay",
            "headline",
            "preferred_headline"
        }
    )

    return normalize_overlay_text(candidate)


def extract_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}") + 1

        if start < 0 or end <= 0:
            raise ValueError("OpenAI response does not contain valid JSON.")

        return json.loads(text[start:end])


def call_text_model(prompt: str, model: str) -> dict:
    client = OpenAI()
    last_error = None

    for attempt in range(1, 4):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                max_completion_tokens=7000,
                response_format={
                    "type": "json_object"
                }
            )

            content = response.choices[0].message.content

            if not content:
                raise ValueError("OpenAI returned an empty planning response.")

            return extract_json(content)

        except Exception as exc:
            last_error = exc

            if attempt < 3:
                time.sleep(attempt * 2)

    raise RuntimeError(
        f"Visual planning failed after retries: {last_error}"
    )


def build_dynamic_plan(
    context: dict,
    script_data: dict,
    visual_asset_plan_data: dict,
    thumbnail_strategy_data: dict,
    text_model: str,
    image_count: int
) -> dict:
    script_payload = script_data.get("script", {})
    asset_payload = visual_asset_plan_data.get("asset_plan", {})
    thumbnail_hint = get_thumbnail_hint(thumbnail_strategy_data)

    prompt = f"""
You are the visual director for Hiddenova, a premium English documentary YouTube channel.

Create a topic-specific visual production plan for this exact video.

CHANNEL: {context["channel"]}
VIDEO_ID: {context["video_id"]}
VIDEO_TITLE: {context["topic_title"]}
THUMBNAIL_TEXT_HINT: {thumbnail_hint or "none"}

SCRIPT:
{json.dumps(script_payload, ensure_ascii=True)}

VISUAL_ASSET_PLAN:
{json.dumps(asset_payload, ensure_ascii=True)}

Return one JSON object with exactly this structure:
{{
  "thumbnail": {{
    "overlay_text": "1 to 4 English words in uppercase",
    "text_position": "left or right",
    "background_prompt": "cinematic thumbnail background prompt with no text"
  }},
  "inserts": [
    {{
      "section_hint": "short section name",
      "visual_role": "short role",
      "target_duration_seconds": 5,
      "prompt": "specific cinematic 16:9 documentary still prompt"
    }}
  ]
}}

Rules:
- Return exactly {image_count} inserts.
- Every insert must directly match this luggage and airport baggage topic.
- Cover hook, baggage identity, conveyors, screening, software routing, failure risk, workers, and final carousel.
- Each visual must be different.
- Use realistic documentary imagery.
- No logos, no readable tags, no barcodes, no airline names, no private data.
- No fake operational interfaces.
- No text inside generated images.
- Thumbnail must be simple, high contrast, mobile readable, and not repeat the full video title.
- Prefer the supplied thumbnail text hint when it is valid.
"""

    raw_plan = call_text_model(prompt=prompt, model=text_model)
    thumbnail = raw_plan.get("thumbnail", {})
    raw_items = raw_plan.get("inserts", [])

    if len(raw_items) != image_count:
        raise ValueError(
            f"Expected {image_count} AI inserts, received {len(raw_items)}."
        )

    overlay_text = normalize_overlay_text(
        thumbnail.get("overlay_text")
    )

    if not overlay_text:
        overlay_text = thumbnail_hint

    if not overlay_text:
        overlay_text = "HIDDEN SYSTEM"

    items = []

    for index, item in enumerate(raw_items, start=1):
        item_prompt = str(item.get("prompt", "")).strip()

        if not item_prompt:
            raise ValueError(f"AI insert {index} has no prompt.")

        items.append({
            "insert_id": f"AI-{index:03d}",
            "sequence": index,
            "section_hint": str(
                item.get("section_hint", f"section_{index}")
            ).strip(),
            "visual_role": str(
                item.get("visual_role", "cinematic_insert")
            ).strip(),
            "target_duration_seconds": 5,
            "prompt": item_prompt,
            "negative_prompt": (
                "no logos, no readable text, no barcodes, no QR codes, "
                "no airline branding, no private data, no fake UI, "
                "no distorted hands, no cartoon style"
            ),
            "status": "planned"
        })

    return {
        "channel": context["channel"],
        "video_id": context["video_id"],
        "run_id": context["run_id"],
        "video_title": context["topic_title"],
        "thumbnail": {
            "overlay_text": overlay_text,
            "text_position": (
                thumbnail.get("text_position")
                if thumbnail.get("text_position") in {"left", "right"}
                else "left"
            ),
            "background_prompt": str(
                thumbnail.get("background_prompt", "")
            ).strip()
        },
        "ai_visual_insert_plan": {
            "style_rules": [
                "realistic documentary look",
                "cinematic airport infrastructure",
                "dark premium Hiddenova atmosphere",
                "16:9 composition",
                "no embedded text"
            ],
            "negative_rules": [
                "no logos",
                "no readable labels",
                "no barcodes",
                "no QR codes",
                "no airline branding",
                "no private passenger data",
                "no fake operational interface",
                "no cartoon style"
            ],
            "items": items
        }
    }


def generate_image_bytes(
    client: OpenAI,
    model: str,
    prompt: str,
    size: str,
    quality: str
) -> bytes:
    last_error = None

    for attempt in range(1, 4):
        try:
            response = client.images.generate(
                model=model,
                prompt=prompt,
                n=1,
                size=size,
                quality=quality,
                output_format="png"
            )

            if not response.data:
                raise ValueError("Image generation returned no data.")

            image_b64 = response.data[0].b64_json

            if not image_b64:
                raise ValueError(
                    "Image generation response has no b64_json."
                )

            return base64.b64decode(image_b64)

        except Exception as exc:
            last_error = exc

            if attempt < 3:
                time.sleep(attempt * 3)

    raise RuntimeError(
        f"Image generation failed after retries: {last_error}"
    )


def get_font(size: int):
    font_paths = [
        Path("C:/Windows/Fonts/arialbd.ttf"),
        Path("C:/Windows/Fonts/impact.ttf")
    ]

    for font_path in font_paths:
        if font_path.exists():
            return ImageFont.truetype(str(font_path), size=size)

    return ImageFont.load_default()


def create_thumbnail(
    background_path: Path,
    output_path: Path,
    overlay_text: str,
    text_position: str
) -> None:
    with Image.open(background_path) as source:
        image = ImageOps.fit(
            source.convert("RGB"),
            (1280, 720),
            method=Image.Resampling.LANCZOS
        )

    draw = ImageDraw.Draw(image, "RGBA")
    font_size = 118
    font = get_font(font_size)

    while font_size > 58:
        box = draw.multiline_textbbox(
            (0, 0),
            overlay_text,
            font=font,
            spacing=8,
            stroke_width=6
        )

        if box[2] - box[0] <= 520:
            break

        font_size -= 6
        font = get_font(font_size)

    x = 70 if text_position == "left" else 700
    y = 250
    text_box = draw.multiline_textbbox(
        (x, y),
        overlay_text,
        font=font,
        spacing=8,
        stroke_width=7
    )

    padding = 24
    background_box = (
        text_box[0] - padding,
        text_box[1] - padding,
        text_box[2] + padding,
        text_box[3] + padding
    )

    draw.rounded_rectangle(
        background_box,
        radius=18,
        fill=(0, 0, 0, 150)
    )

    draw.multiline_text(
        (x, y),
        overlay_text,
        font=font,
        fill=(255, 255, 255, 255),
        spacing=8,
        stroke_width=7,
        stroke_fill=(0, 0, 0, 255)
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(
        output_path,
        format="JPEG",
        quality=92,
        optimize=True
    )


def inspect_image(path: Path) -> dict:
    warnings = []
    approved = True

    if not path.exists() or path.stat().st_size < 50000:
        return {
            "approved": False,
            "warnings": ["Image file is missing or too small."]
        }

    try:
        with Image.open(path) as image:
            width, height = image.size
            ratio = width / height

            if width < 1024 or height < 576:
                approved = False
                warnings.append("Image resolution is below minimum.")

            if ratio < 1.3 or ratio > 1.8:
                approved = False
                warnings.append("Image aspect ratio is not suitable for 16:9.")

    except Exception as exc:
        approved = False
        warnings.append(f"Image inspection failed: {exc}")

    return {
        "approved": approved,
        "warnings": warnings
    }


def generate_outputs(
    context: dict,
    plan: dict,
    image_model: str,
    image_size: str,
    image_quality: str
) -> dict:
    channel = context["channel"]
    video_id = context["video_id"]
    output_dir = get_output_dir(channel, video_id)
    image_dir = output_dir / "images"

    output_dir.mkdir(parents=True, exist_ok=True)
    image_dir.mkdir(parents=True, exist_ok=True)

    client = OpenAI()
    generated_images = []

    for item in plan["ai_visual_insert_plan"]["items"]:
        insert_id = item["insert_id"]
        image_path = image_dir / f"{insert_id.lower()}.png"

        full_prompt = (
            f"{item['prompt']}\n"
            "Create a cinematic 16:9 documentary still. "
            "No text inside the image. "
            f"Must avoid: {item['negative_prompt']}."
        )

        print(
            f"Generating {insert_id}: {item['section_hint']}",
            flush=True
        )

        image_path.write_bytes(
            generate_image_bytes(
                client=client,
                model=image_model,
                prompt=full_prompt,
                size=image_size,
                quality=image_quality
            )
        )

        generated_images.append({
            "insert_id": insert_id,
            "sequence": item["sequence"],
            "section_hint": item["section_hint"],
            "visual_role": item["visual_role"],
            "target_duration_seconds": item[
                "target_duration_seconds"
            ],
            "prompt": item["prompt"],
            "negative_prompt": item["negative_prompt"],
            "model": image_model,
            "size": image_size,
            "quality": image_quality,
            "output_format": "png",
            "filename": image_path.name,
            "relative_path": relative_path(image_path),
            "status": "generated_pending_qa"
        })

    thumbnail_background_path = (
        image_dir / "thumbnail_background.png"
    )

    thumbnail_prompt = (
        f"{plan['thumbnail']['background_prompt']}\n"
        "Create a premium cinematic YouTube documentary thumbnail "
        "background about airport baggage handling. "
        "Use one dominant suitcase and visible hidden conveyor "
        "infrastructure. Keep clear negative space for a short text "
        f"overlay on the {plan['thumbnail']['text_position']}. "
        "Do not include any text, logos, airline branding, barcodes, "
        "or readable luggage tags."
    )

    print("Generating thumbnail background.", flush=True)

    thumbnail_background_path.write_bytes(
        generate_image_bytes(
            client=client,
            model=image_model,
            prompt=thumbnail_prompt,
            size=image_size,
            quality=image_quality
        )
    )

    thumbnail_path = output_dir / "thumbnail.jpg"

    create_thumbnail(
        background_path=thumbnail_background_path,
        output_path=thumbnail_path,
        overlay_text=plan["thumbnail"]["overlay_text"],
        text_position=plan["thumbnail"]["text_position"]
    )

    generation_output = {
        "agent": "ai_visual_generation",
        "version": "2.0",
        "channel": channel,
        "status": "images_ready",
        "summary": {
            "planned_insert_count": len(generated_images),
            "selected_insert_count": len(generated_images),
            "generated_image_count": len(generated_images),
            "model": image_model,
            "size": image_size,
            "quality": image_quality,
            "output_format": "png",
            "output_dir": relative_path(image_dir),
            "next_agent": "ai_visual_qa"
        },
        "generated_images": generated_images,
        "source": {
            "source_agent": "video_visual_pipeline",
            "plan_reference": relative_path(
                output_dir / "visual_plan.json"
            ),
            "video_title": context["topic_title"],
            "video_id": video_id,
            "run_id": context["run_id"]
        },
        "metadata": {
            "next_agent": "ai_visual_qa"
        }
    }

    image_checks = []

    for item in generated_images:
        inspection = inspect_image(
            PROJECT_ROOT / item["relative_path"]
        )

        image_checks.append({
            "insert_id": item["insert_id"],
            "relative_path": item["relative_path"],
            "approved": inspection["approved"],
            "warnings": inspection["warnings"]
        })

    approved_count = sum(
        1 for item in image_checks if item["approved"]
    )
    failed_count = len(image_checks) - approved_count
    qa_status = "approved" if failed_count == 0 else "needs_revision"

    qa_output = {
        "agent": "ai_visual_qa",
        "version": "2.0",
        "channel": channel,
        "status": qa_status,
        "summary": {
            "generated_image_count": len(image_checks),
            "approved_image_count": approved_count,
            "failed_image_count": failed_count,
            "warning_count": sum(
                len(item["warnings"]) for item in image_checks
            ),
            "manual_visual_review": "required",
            "note": (
                "Technical QA only. Founder visual review is still required."
            )
        },
        "image_checks": image_checks,
        "readiness": {
            "images_ready_for_hybrid_assembly": qa_status == "approved",
            "manual_style_approved": False,
            "blocking_notes": [
                "Founder visual review is required before public export."
            ]
        },
        "source": {
            "source_agent": "ai_visual_generation",
            "generation_reference": relative_path(
                output_dir / "ai_visual_generation.json"
            ),
            "video_title": context["topic_title"],
            "video_id": video_id,
            "run_id": context["run_id"]
        },
        "metadata": {
            "next_agent": "hybrid_video_assembly"
        }
    }

    thumbnail_output = {
        "agent": "video_visual_pipeline",
        "version": "1.0",
        "channel": channel,
        "video_id": video_id,
        "run_id": context["run_id"],
        "status": "thumbnail_ready",
        "thumbnail": {
            "overlay_text": plan["thumbnail"]["overlay_text"],
            "text_position": plan["thumbnail"]["text_position"],
            "relative_path": relative_path(thumbnail_path),
            "size_bytes": thumbnail_path.stat().st_size,
            "width": 1280,
            "height": 720
        }
    }

    save_json(
        output_dir / "ai_visual_generation.json",
        generation_output
    )
    save_json(
        output_dir / "ai_visual_qa.json",
        qa_output
    )
    save_json(
        output_dir / "thumbnail.json",
        thumbnail_output
    )

    return {
        "generation": generation_output,
        "qa": qa_output,
        "thumbnail": thumbnail_output
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate video-specific AI inserts and thumbnail assets."
        )
    )

    parser.add_argument(
        "--channel",
        default=DEFAULT_CHANNEL
    )
    parser.add_argument(
        "--video-id",
        required=True
    )
    parser.add_argument(
        "--image-count",
        type=int,
        default=DEFAULT_IMAGE_COUNT
    )
    parser.add_argument(
        "--text-model",
        default=os.getenv(
            "OPENAI_TEXT_MODEL",
            DEFAULT_TEXT_MODEL
        )
    )
    parser.add_argument(
        "--image-model",
        default=os.getenv(
            "OPENAI_IMAGE_MODEL",
            DEFAULT_IMAGE_MODEL
        )
    )
    parser.add_argument(
        "--image-size",
        default=os.getenv(
            "OPENAI_IMAGE_SIZE",
            "1536x1024"
        )
    )
    parser.add_argument(
        "--image-quality",
        default=os.getenv(
            "OPENAI_IMAGE_QUALITY",
            "medium"
        )
    )
    parser.add_argument(
        "--refresh-context",
        action="store_true"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true"
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    channel = args.channel.lower()
    video_id = args.video_id.lower()

    load_dotenv(PROJECT_ROOT / ".env")

    context = create_context(
        channel=channel,
        video_id=video_id,
        refresh=args.refresh_context
    )

    script_path, script_data = load_context_source(
        context,
        "script"
    )
    qa_path, qa_data = load_context_source(
        context,
        "qa"
    )
    asset_plan_path, visual_asset_plan_data = load_context_source(
        context,
        "visual_asset_plan"
    )
    thumbnail_strategy_path, thumbnail_strategy_data = (
        load_context_source(
            context,
            "thumbnail_strategy"
        )
    )

    if qa_data.get("status") != "approved":
        raise ValueError("Script QA is not approved.")

    output_dir = get_output_dir(channel, video_id)

    print(f"VIDEO_CONTEXT_ID: {video_id}")
    print(f"RUN_ID: {context['run_id']}")
    print(f"VIDEO_TITLE: {context['topic_title']}")
    print(f"SCRIPT_SOURCE: {relative_path(script_path)}")
    print(f"QA_SOURCE: {relative_path(qa_path)}")
    print(f"ASSET_PLAN_SOURCE: {relative_path(asset_plan_path)}")
    print(
        "THUMBNAIL_STRATEGY_SOURCE: "
        f"{relative_path(thumbnail_strategy_path)}"
    )

    if args.dry_run:
        print("STATUS: context_ready")
        print(f"PLANNED_AI_INSERT_COUNT: {args.image_count}")
        print(
            "THUMBNAIL_TEXT_HINT: "
            f"{get_thumbnail_hint(thumbnail_strategy_data)}"
        )
        print(f"OUTPUT_DIR: {relative_path(output_dir)}")
        return

    plan = build_dynamic_plan(
        context=context,
        script_data=script_data,
        visual_asset_plan_data=visual_asset_plan_data,
        thumbnail_strategy_data=thumbnail_strategy_data,
        text_model=args.text_model,
        image_count=args.image_count
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    plan_path = output_dir / "visual_plan.json"
    save_json(plan_path, plan)

    outputs = generate_outputs(
        context=context,
        plan=plan,
        image_model=args.image_model,
        image_size=args.image_size,
        image_quality=args.image_quality
    )

    context["status"] = "visual_assets_ready"
    context["outputs"].update({
        "visual_plan": relative_path(plan_path),
        "ai_visual_generation": relative_path(
            output_dir / "ai_visual_generation.json"
        ),
        "ai_visual_qa": relative_path(
            output_dir / "ai_visual_qa.json"
        ),
        "thumbnail": outputs["thumbnail"]["thumbnail"][
            "relative_path"
        ]
    })

    save_json(get_context_path(channel, video_id), context)

    print("Video Visual Pipeline completed successfully.")
    print(
        "AI_INSERT_COUNT: "
        f"{outputs['generation']['summary']['generated_image_count']}"
    )
    print(
        "AI_QA_STATUS: "
        f"{outputs['qa']['status']}"
    )
    print(
        "THUMBNAIL_TEXT: "
        f"{outputs['thumbnail']['thumbnail']['overlay_text']}"
    )
    print(
        "THUMBNAIL_PATH: "
        f"{outputs['thumbnail']['thumbnail']['relative_path']}"
    )


if __name__ == "__main__":
    main()
