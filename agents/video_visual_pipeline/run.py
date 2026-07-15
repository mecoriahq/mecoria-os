import argparse
import base64
import json
import os
import re
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont, ImageOps


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.video_run_context import (
    load_context,
    register_output,
    resolve_output,
    resolve_source,
    save_context,
    set_status,
)


from core.asset_usage_registry import (
    build_asset_record,
    register_asset_batch,
    remove_asset_usage_for_path,
    validate_asset_batch,
)

from core.thumbnail_standard import (
    assert_thumbnail_text,
    build_thumbnail_background_prompt,
    build_thumbnail_qa_checklist,
    load_thumbnail_standard,
)

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



def get_output_dir(
    channel: str,
    video_id: str,
    run_id: str
) -> Path:
    return (
        BASE_DIR
        / "output"
        / channel
        / video_id
        / run_id
    )


def resolve_context_input(
    context: dict,
    key: str,
    required: bool = True
) -> tuple[Path | None, dict]:
    source_type = None

    if key in context.get("outputs", {}):
        path = resolve_output(
            context=context,
            key=key
        )
        source_type = "output"
    elif key in context.get("sources", {}):
        path = resolve_source(
            context=context,
            key=key
        )
        source_type = "source"
    elif required:
        raise KeyError(f"Context input is missing: {key}")
    else:
        return None, {}

    data = load_json(path)

    source_video_id = data.get("video_id")
    source_run_id = data.get("run_id")

    if source_type == "output":
        if source_video_id != context["video_id"]:
            raise ValueError(f"{key} output video_id mismatch.")

        if source_run_id != context["run_id"]:
            raise ValueError(f"{key} output run_id mismatch.")
    else:
        if (
            source_video_id is not None
            and source_video_id != context["video_id"]
        ):
            raise ValueError(f"{key} source video_id mismatch.")

        if (
            source_run_id is not None
            and source_run_id != context["run_id"]
        ):
            raise ValueError(f"{key} source run_id mismatch.")

    return path, data


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
    seo_data: dict,
    visual_asset_plan_data: dict,
    thumbnail_strategy_data: dict,
    text_model: str,
    image_count: int
) -> dict:
    script_payload = script_data.get("script", {})
    seo_payload = seo_data.get("seo", {})

    asset_payload = visual_asset_plan_data.get(
        "asset_plan",
        visual_asset_plan_data
    )

    thumbnail_hint = (
        get_thumbnail_hint(thumbnail_strategy_data)
        or normalize_overlay_text(
            seo_payload.get("thumbnail_text")
        )
    )

    prompt = f"""
You are the visual director for Hiddenova, a premium English
documentary YouTube channel.

Create a topic-specific visual production plan for this exact video.

CHANNEL: {context["channel"]}
VIDEO_ID: {context["video_id"]}
RUN_ID: {context["run_id"]}
VIDEO_TITLE: {context["topic_title"]}
SEO_TITLE: {seo_payload.get("video_title", "")}
THUMBNAIL_TEXT_HINT: {thumbnail_hint or "none"}

SCRIPT:
{json.dumps(script_payload, ensure_ascii=True)}

OPTIONAL_VISUAL_ASSET_PLAN:
{json.dumps(asset_payload, ensure_ascii=True)}

Return one JSON object with exactly this structure:

{{
  "thumbnail": {{
    "overlay_text": "2 to 4 English words in uppercase",
    "text_position": "left or right",
    "background_prompt": "specific cinematic thumbnail background prompt with no text"
  }},
  "inserts": [
    {{
      "section_hint": "short section name",
      "visual_role": "short visual role",
      "target_duration_seconds": 5,
      "prompt": "specific cinematic 16:9 documentary still prompt"
    }}
  ]
}}

Rules:
- Return exactly {image_count} inserts.
- Every insert must directly match this exact video topic.
- Cover the hook, key explanations, human/system layer,
  failure or tension point, and conclusion.
- Every visual must be meaningfully different.
- Use realistic premium documentary imagery.
- Do not reuse imagery from another video topic.
- No logos, readable labels, barcodes, private data,
  fake dashboards, or operational interfaces.
- No embedded text inside generated images.
- Thumbnail must use one dominant subject.
- Thumbnail must have strong contrast and clear text space.
- Thumbnail text must contain 2 to 4 words.
- Thumbnail text must not repeat the full video title.
- Prefer the supplied thumbnail hint when valid.
"""

    raw_plan = call_text_model(
        prompt=prompt,
        model=text_model
    )

    thumbnail = raw_plan.get("thumbnail", {})
    raw_items = raw_plan.get("inserts", [])

    if len(raw_items) != image_count:
        raise ValueError(
            f"Expected {image_count} AI inserts, "
            f"received {len(raw_items)}."
        )

    overlay_text = normalize_overlay_text(
        thumbnail.get("overlay_text")
    )

    if not overlay_text:
        overlay_text = thumbnail_hint

    if not overlay_text:
        raise ValueError(
            "Thumbnail overlay text is missing or invalid."
        )

    items = []

    for index, item in enumerate(raw_items, start=1):
        item_prompt = str(item.get("prompt", "")).strip()

        if not item_prompt:
            raise ValueError(
                f"AI insert {index} has no prompt."
            )

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
                "no logos, no readable text, no barcodes, "
                "no QR codes, no brand names, no private data, "
                "no fake UI, no distorted hands, no cartoon style"
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
                "premium cinematic lighting",
                "dark Hiddenova atmosphere",
                "16:9 composition",
                "no embedded text"
            ],
            "negative_rules": [
                "no unrelated previous-video imagery",
                "no logos",
                "no readable labels",
                "no barcodes",
                "no QR codes",
                "no private information",
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
) -> dict:
    standard = load_thumbnail_standard()

    text_result = assert_thumbnail_text(
        value=overlay_text,
        standard=standard
    )

    words = text_result[
        "normalized_text"
    ].split()

    white = (255, 255, 255, 255)
    yellow = (255, 214, 0, 255)

    if len(words) == 2:
        lines = [
            (words[0], white),
            (words[1], yellow)
        ]
    elif len(words) == 3:
        lines = [
            (words[0], white),
            (words[1], white),
            (words[2], yellow)
        ]
    else:
        lines = [
            (" ".join(words[:2]), white),
            (words[2], white),
            (words[3], yellow)
        ]

    with Image.open(background_path) as source:
        image = ImageOps.fit(
            source.convert("RGB"),
            (1280, 720),
            method=Image.Resampling.LANCZOS
        )

    draw = ImageDraw.Draw(image, "RGBA")

    target_width_min = int(
        1280
        * float(
            standard["layout"][
                "text_area_ratio_min"
            ]
        )
    )
    target_width_max = int(
        1280
        * float(
            standard["layout"][
                "text_area_ratio_max"
            ]
        )
    )

    target_height_max = int(720 * 0.78)
    stroke_width = 12
    shadow_offset = 8
    font_size = 210

    def measure(
        current_font: ImageFont.FreeTypeFont
    ) -> tuple[list[int], list[int]]:
        widths = []
        heights = []

        for line, _ in lines:
            box = draw.textbbox(
                (0, 0),
                line,
                font=current_font,
                stroke_width=stroke_width
            )

            widths.append(box[2] - box[0])
            heights.append(box[3] - box[1])

        return widths, heights

    while font_size > 96:
        font = get_font(font_size)
        widths, heights = measure(font)

        line_gap = max(
            4,
            int(font_size * 0.03)
        )

        total_height = (
            sum(heights)
            + line_gap * (len(lines) - 1)
        )

        if (
            max(widths) <= target_width_max
            and total_height <= target_height_max
        ):
            break

        font_size -= 4

    font = get_font(font_size)
    widths, heights = measure(font)

    line_gap = max(
        4,
        int(font_size * 0.03)
    )

    total_height = (
        sum(heights)
        + line_gap * (len(lines) - 1)
    )

    y = int((720 - total_height) / 2)

    for index, (line, color) in enumerate(lines):
        width = widths[index]
        height = heights[index]

        if text_position == "right":
            x = 1280 - width - 45
        else:
            x = 45

        draw.text(
            (
                x + shadow_offset,
                y + shadow_offset
            ),
            line,
            font=font,
            fill=(0, 0, 0, 220),
            stroke_width=stroke_width + 3,
            stroke_fill=(0, 0, 0, 255)
        )

        draw.text(
            (x, y),
            line,
            font=font,
            fill=color,
            stroke_width=stroke_width,
            stroke_fill=(0, 0, 0, 255)
        )

        y += height + line_gap

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    image.save(
        output_path,
        format="JPEG",
        quality=95,
        optimize=True
    )

    max_line_width = max(widths)
    text_width_ratio = round(
        max_line_width / 1280,
        4
    )

    return {
        "font_size": font_size,
        "line_count": len(lines),
        "max_line_width": max_line_width,
        "text_width_ratio": text_width_ratio,
        "text_width_target_min": round(
            target_width_min / 1280,
            4
        ),
        "text_width_target_max": round(
            target_width_max / 1280,
            4
        ),
        "text_block_height_ratio": round(
            total_height / 720,
            4
        ),
        "stroke_width": stroke_width,
        "shadow_offset": shadow_offset,
        "standard_name": standard[
            "standard_name"
        ]
    }


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



def register_visual_asset_ownership(
    context: dict,
    generation_output: dict,
    qa_output: dict,
    thumbnail_output: dict
) -> Path:
    if qa_output.get("status") != "approved":
        raise ValueError(
            "Visual assets cannot be registered before QA approval."
        )

    records = []
    used_hashes = {}
    insert_hashes = {}

    for item in generation_output.get(
        "generated_images",
        []
    ):
        image_path = PROJECT_ROOT / item["relative_path"]

        record = build_asset_record(
            path=image_path,
            asset_type="ai_visual",
            channel=context["channel"],
            video_id=context["video_id"],
            run_id=context["run_id"],
            shared_brand_asset=False
        )

        existing_label = used_hashes.get(
            record["sha256"]
        )

        if existing_label:
            raise ValueError(
                "Duplicate visual content detected inside "
                f"the current video: {existing_label} and "
                f"{item['insert_id']}."
            )

        used_hashes[record["sha256"]] = item[
            "insert_id"
        ]
        insert_hashes[item["insert_id"]] = record[
            "sha256"
        ]
        item["sha256"] = record["sha256"]
        records.append(record)

    thumbnail_data = thumbnail_output["thumbnail"]
    thumbnail_path = (
        PROJECT_ROOT
        / thumbnail_data["relative_path"]
    )

    remove_asset_usage_for_path(
        path=thumbnail_path,
        channel=context["channel"],
        video_id=context["video_id"],
        asset_type="thumbnail"
    )

    thumbnail_record = build_asset_record(
        path=thumbnail_path,
        asset_type="thumbnail",
        channel=context["channel"],
        video_id=context["video_id"],
        run_id=context["run_id"],
        shared_brand_asset=False
    )

    if thumbnail_record["sha256"] in used_hashes:
        raise ValueError(
            "Thumbnail duplicates an AI visual asset."
        )

    thumbnail_data["sha256"] = thumbnail_record[
        "sha256"
    ]
    records.append(thumbnail_record)

    for check in qa_output.get(
        "image_checks",
        []
    ):
        insert_id = check["insert_id"]

        if insert_id not in insert_hashes:
            raise ValueError(
                f"Visual QA item has no generated asset: {insert_id}"
            )

        check["sha256"] = insert_hashes[insert_id]

    validate_asset_batch(records=records)

    registry_path = register_asset_batch(
        records=records
    )

    registry_reference = relative_path(
        registry_path
    )

    generation_output.setdefault(
        "summary",
        {}
    ).update({
        "registered_visual_asset_count": len(
            generation_output.get(
                "generated_images",
                []
            )
        ),
        "reused_visual_asset_count": 0,
        "asset_registry_reference": registry_reference
    })

    generation_output.setdefault(
        "source",
        {}
    )["asset_registry_reference"] = (
        registry_reference
    )

    qa_output.setdefault(
        "checks",
        {}
    ).update({
        "cross_video_asset_reuse": True,
        "unique_generated_asset_hashes": True,
        "asset_registry_ownership": True
    })

    qa_output.setdefault(
        "summary",
        {}
    ).update({
        "reused_visual_asset_count": 0,
        "asset_registry_verified_count": len(
            generation_output.get(
                "generated_images",
                []
            )
        )
    })

    qa_output.setdefault(
        "source",
        {}
    )["asset_registry_reference"] = (
        registry_reference
    )

    thumbnail_output.setdefault(
        "source",
        {}
    ).update({
        "asset_registry_reference": registry_reference,
        "video_id": context["video_id"],
        "run_id": context["run_id"]
    })

    return registry_path



def existing_image_is_valid(path: Path) -> bool:
    if not path.exists():
        return False

    try:
        return inspect_image(path)["approved"] is True
    except Exception:
        return False


def generate_outputs(
    context: dict,
    plan: dict,
    image_model: str,
    image_size: str,
    image_quality: str,
    force_regenerate: bool = False
) -> dict:
    channel = context["channel"]
    video_id = context["video_id"]
    output_dir = get_output_dir(
        channel,
        video_id,
        context["run_id"]
    )
    image_dir = output_dir / "images"
    thumbnail_standard = load_thumbnail_standard()

    thumbnail_text_result = assert_thumbnail_text(
        value=plan["thumbnail"]["overlay_text"],
        standard=thumbnail_standard
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    image_dir.mkdir(parents=True, exist_ok=True)

    client = None
    generated_images = []

    def get_image_client() -> OpenAI:
        nonlocal client

        if client is None:
            client = OpenAI()

        return client

    for item in plan["ai_visual_insert_plan"]["items"]:
        insert_id = item["insert_id"]
        image_path = image_dir / f"{insert_id.lower()}.png"

        full_prompt = (
            f"{item['prompt']}\n"
            "Create a cinematic 16:9 documentary still. "
            "No text inside the image. "
            f"Must avoid: {item['negative_prompt']}."
        )

        reuse_image = (
            not force_regenerate
            and existing_image_is_valid(image_path)
        )

        if reuse_image:
            print(
                f"Reusing existing {insert_id}: "
                f"{item['section_hint']}",
                flush=True
            )
        else:
            print(
                f"Generating {insert_id}: "
                f"{item['section_hint']}",
                flush=True
            )

            image_path.write_bytes(
                generate_image_bytes(
                    client=get_image_client(),
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
        build_thumbnail_background_prompt(
            video_topic=context["topic_title"],
            main_subject=plan["thumbnail"][
                "background_prompt"
            ],
            thumbnail_text=thumbnail_text_result[
                "normalized_text"
            ],
            text_position=plan["thumbnail"][
                "text_position"
            ],
            standard=thumbnail_standard
        )
    )

    reuse_thumbnail_background = (
        not force_regenerate
        and existing_image_is_valid(
            thumbnail_background_path
        )
    )

    if reuse_thumbnail_background:
        print(
            "Reusing existing thumbnail background.",
            flush=True
        )
    else:
        print(
            "Generating thumbnail background.",
            flush=True
        )

        thumbnail_background_path.write_bytes(
            generate_image_bytes(
                client=get_image_client(),
                model=image_model,
                prompt=thumbnail_prompt,
                size=image_size,
                quality=image_quality
            )
        )

    thumbnail_path = output_dir / "thumbnail.jpg"

    thumbnail_layout = None

    reuse_thumbnail = (
        not force_regenerate
        and existing_image_is_valid(thumbnail_path)
    )

    if reuse_thumbnail:
        print(
            "Reusing existing final thumbnail.",
            flush=True
        )
    else:
        thumbnail_layout = create_thumbnail(
            background_path=thumbnail_background_path,
            output_path=thumbnail_path,
            overlay_text=thumbnail_text_result[
                "normalized_text"
            ],
            text_position=plan["thumbnail"][
                "text_position"
            ]
        )

    generation_output = {
        "agent": "ai_visual_generation",
        "version": "2.0",
        "channel": channel,
        "video_id": video_id,
        "run_id": context["run_id"],
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
        "video_id": video_id,
        "run_id": context["run_id"],
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

    thumbnail_qa = build_thumbnail_qa_checklist(
        thumbnail_text=thumbnail_text_result[
            "normalized_text"
        ],
        standard=thumbnail_standard
    )

    if thumbnail_layout:
        automatic_checks = thumbnail_qa[
            "automatic_checks"
        ]

        automatic_checks.update({
            "text_is_very_large": (
                thumbnail_layout["font_size"]
                >= 130
            ),
            "mobile_readability_passed": (
                thumbnail_layout["font_size"]
                >= 130
                and thumbnail_layout[
                    "text_width_ratio"
                ] >= 0.35
            ),
            "standard_layout_applied": True
        })

    thumbnail_output = {
        "agent": "video_visual_pipeline",
        "version": "2.0",
        "channel": channel,
        "video_id": video_id,
        "run_id": context["run_id"],
        "status": "thumbnail_ready",
        "thumbnail": {
            "standard_name": thumbnail_standard[
                "standard_name"
            ],
            "overlay_text": thumbnail_text_result[
                "normalized_text"
            ],
            "text_position": plan["thumbnail"][
                "text_position"
            ],
            "relative_path": relative_path(
                thumbnail_path
            ),
            "size_bytes": (
                thumbnail_path.stat().st_size
            ),
            "width": 1280,
            "height": 720,
            "text_style": {
                "size": "very_large",
                "weight": "bold",
                "two_color": True,
                "colors": [
                    "white",
                    "yellow"
                ],
                "stroke": "black",
                "stroke_weight": "strong",
                "mobile_readable": True
            },
            "layout_metrics": thumbnail_layout,
            "qa": thumbnail_qa
        }
    }

    registry_path = register_visual_asset_ownership(
        context=context,
        generation_output=generation_output,
        qa_output=qa_output,
        thumbnail_output=thumbnail_output
    )

    print(
        "VISUAL_ASSET_REGISTRY: "
        f"{relative_path(registry_path)}"
    )

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
        "--force-regenerate",
        action="store_true",
        help=(
            "Regenerate visual assets even when valid "
            "video-specific files already exist."
        )
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

    context = load_context(
        channel=channel,
        video_id=video_id
    )

    script_path, script_data = resolve_context_input(
        context=context,
        key="script"
    )
    seo_path, seo_data = resolve_context_input(
        context=context,
        key="seo"
    )
    qa_path, qa_data = resolve_context_input(
        context=context,
        key="qa"
    )

    asset_plan_path, visual_asset_plan_data = (
        resolve_context_input(
            context=context,
            key="visual_asset_plan",
            required=False
        )
    )

    thumbnail_strategy_path, thumbnail_strategy_data = (
        resolve_context_input(
            context=context,
            key="thumbnail_strategy",
            required=False
        )
    )

    if not thumbnail_strategy_data:
        thumbnail_strategy_data = {
            "preferred_thumbnail_text": (
                seo_data.get("seo", {}).get(
                    "thumbnail_text"
                )
            )
        }

    if qa_data.get("status") != "approved":
        raise ValueError("Content QA is not approved.")

    minimum_qa_score = context.get(
        "quality_gates",
        {}
    ).get("minimum_content_qa_score", 85)

    if qa_data.get("overall_score", 0) < minimum_qa_score:
        raise ValueError(
            "Content QA score is below the required gate."
        )

    minimum_ai_count = context.get(
        "quality_gates",
        {}
    ).get("minimum_ai_insert_count", DEFAULT_IMAGE_COUNT)

    if args.image_count < minimum_ai_count:
        raise ValueError(
            f"AI insert count must be at least {minimum_ai_count}."
        )

    output_dir = get_output_dir(
        channel,
        video_id,
        context["run_id"]
    )

    print(f"VIDEO_CONTEXT_ID: {video_id}")
    print(f"RUN_ID: {context['run_id']}")
    print(f"VIDEO_TITLE: {context['topic_title']}")
    print(f"SCRIPT_SOURCE: {relative_path(script_path)}")
    print(f"SEO_SOURCE: {relative_path(seo_path)}")
    print(f"QA_SOURCE: {relative_path(qa_path)}")
    print(
        "ASSET_PLAN_SOURCE: "
        f"{relative_path(asset_plan_path) if asset_plan_path else 'derived'}"
    )
    print(
        "THUMBNAIL_STRATEGY_SOURCE: "
        f"{relative_path(thumbnail_strategy_path) if thumbnail_strategy_path else 'seo'}"
    )
    print("LATEST_JSON_INPUTS: blocked")
    print("THUMBNAIL_STYLE: large_two_color")

    if args.dry_run:
        print("STATUS: visual_pipeline_dry_run_ready")
        print(f"PLANNED_AI_INSERT_COUNT: {args.image_count}")
        print(
            "THUMBNAIL_TEXT_HINT: "
            f"{get_thumbnail_hint(thumbnail_strategy_data)}"
        )
        print(f"OUTPUT_DIR: {relative_path(output_dir)}")
        return

    output_dir.mkdir(parents=True, exist_ok=True)
    plan_path = output_dir / "visual_plan.json"

    if (
        plan_path.exists()
        and not args.force_regenerate
    ):
        plan = load_json(plan_path)

        if plan.get("channel") != context["channel"]:
            raise ValueError(
                "Existing visual plan channel mismatch."
            )

        if plan.get("video_id") != context["video_id"]:
            raise ValueError(
                "Existing visual plan video_id mismatch."
            )

        if plan.get("run_id") != context["run_id"]:
            raise ValueError(
                "Existing visual plan run_id mismatch."
            )

        planned_items = plan.get(
            "ai_visual_insert_plan",
            {}
        ).get("items", [])

        if len(planned_items) != args.image_count:
            raise ValueError(
                "Existing visual plan insert count mismatch."
            )

        print("VISUAL_PLAN_MODE: reused_existing")
    else:
        plan = build_dynamic_plan(
            context=context,
            script_data=script_data,
            seo_data=seo_data,
            visual_asset_plan_data=visual_asset_plan_data,
            thumbnail_strategy_data=thumbnail_strategy_data,
            text_model=args.text_model,
            image_count=args.image_count
        )

        save_json(plan_path, plan)
        print("VISUAL_PLAN_MODE: generated")

    outputs = generate_outputs(
        context=context,
        plan=plan,
        image_model=args.image_model,
        image_size=args.image_size,
        image_quality=args.image_quality,
        force_regenerate=args.force_regenerate
    )

    context.setdefault(
        "quality_gates",
        {}
    ).update({
        "allow_cross_video_asset_reuse": False,
        "require_visual_asset_registry_ownership": True,
        "require_thumbnail_asset_registry_ownership": True,
        "require_hiddenova_thumbnail_standard": True,
        "thumbnail_style": "hiddenova_cinematic_v1",
        "thumbnail_text_min_words": 2,
        "thumbnail_text_max_words": 4,
        "thumbnail_text_size": "very_large",
        "thumbnail_mobile_readability_priority": "maximum"
    })


    generated_count = outputs[
        "generation"
    ]["summary"]["generated_image_count"]

    if generated_count < minimum_ai_count:
        raise ValueError(
            "Generated AI insert count is below the required gate."
        )

    if outputs["qa"]["status"] != "approved":
        raise ValueError(
            "AI visual QA is not approved."
        )

    context = register_output(
        context=context,
        agent="visual_plan",
        reference=relative_path(plan_path),
        status="plan_ready"
    )
    context = register_output(
        context=context,
        agent="ai_visual_generation",
        reference=relative_path(
            output_dir / "ai_visual_generation.json"
        ),
        status="images_ready"
    )
    context = register_output(
        context=context,
        agent="ai_visual_qa",
        reference=relative_path(
            output_dir / "ai_visual_qa.json"
        ),
        status="approved"
    )
    context = register_output(
        context=context,
        agent="thumbnail",
        reference=outputs["thumbnail"]["thumbnail"][
            "relative_path"
        ],
        status="thumbnail_ready"
    )
    context = register_output(
        context=context,
        agent="thumbnail_record",
        reference=relative_path(
            output_dir / "thumbnail.json"
        ),
        status="thumbnail_ready"
    )

    if context.get("status") not in {
        "uploaded_for_founder_review",
        "published",
        "public"
    }:
        context = set_status(
            context=context,
            status="visual_assets_ready",
            next_agent="hybrid_video_assembly"
        )

    save_context(context)

    print("Video Visual Pipeline completed successfully.")
    print(f"AI_INSERT_COUNT: {generated_count}")
    print(f"AI_QA_STATUS: {outputs['qa']['status']}")
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
