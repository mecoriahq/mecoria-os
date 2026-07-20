import argparse
import base64
import json
import os
import re
import shutil
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

from core.founder_editorial_override import (
    effective_content_approval,
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
    build_thumbnail_lines,
    build_thumbnail_overlay_spec,
    build_thumbnail_qa_checklist,
    combine_thumbnail_scores,
    load_thumbnail_standard,
    normalize_thumbnail_vision_qa,
    validate_thumbnail_concepts,
)

DEFAULT_CHANNEL = "hiddenova"
DEFAULT_IMAGE_MODEL = "gpt-image-1"
DEFAULT_TEXT_MODEL = "gpt-5.5"
DEFAULT_IMAGE_COUNT = 8
LEGACY_THUMBNAIL_STANDARD_NAME = "hiddenova_cinematic_v2"
LEGACY_THUMBNAIL_V2_COMPATIBILITY = {
    "thumbnail_style": "hiddenova_cinematic_v2",
    "thumbnail_standard_name": "hiddenova_cinematic_v2",
}


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



def call_thumbnail_vision_qa(
    image_path: Path,
    concept: dict,
    video_topic: str,
    model: str,
    standard: dict
) -> dict:
    client = OpenAI()
    image_b64 = base64.b64encode(
        image_path.read_bytes()
    ).decode("ascii")
    channel_name = standard.get(
        "channel_display_name",
        standard["channel"].replace("_", " ").title(),
    )
    forbidden = ", ".join(
        standard.get("forbidden_elements", [])
    )
    prompt = f"""
You are the strict thumbnail QA judge for {channel_name}.

Evaluate the actual rendered YouTube thumbnail image.

VIDEO_TOPIC:
{video_topic}

CHANNEL_STANDARD:
{standard["standard_name"]}

CONCEPT_TYPE:
{concept["concept_type"]}

EXPECTED_HEADLINE:
{concept["overlay_text"]}

EXPECTED_DOMINANT_SUBJECT:
{concept["dominant_subject"]}

EXPECTED_CONFLICT:
{concept["conflict"]}

FORBIDDEN_OR_MISLEADING ELEMENTS:
{forbidden}

Reject average, generic, low-tension, cluttered, weak, or misleading thumbnails.

Return exactly one JSON object:
{{
  "scores": {{
    "topic_match": 0,
    "dominant_subject": 0,
    "visual_tension": 0,
    "mobile_readability": 0,
    "clean_composition": 0,
    "cinematic_quality": 0,
    "ctr_strength": 0
  }},
  "verdict": "approved or rejected",
  "issues": ["short issue"],
  "summary": "one sentence"
}}

Scoring rules:
- 90-100 means exceptional and immediately clickable.
- 82-89 means production-ready.
- Below 82 is not approved.
- Headline must be instantly readable on mobile.
- One dominant topic-specific subject must control the right side.
- The concept must communicate one clear tension or consequence.
- Generic stock-poster appearance must be rejected.
- Reject fabricated evidence, fake quotations, fake arrests, or unsupported criminal implications.
- Do not approve merely because the image is technically valid.
""".strip()

    last_error = None

    for attempt in range(1, 4):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": (
                                        "data:image/jpeg;base64,"
                                        + image_b64
                                    )
                                }
                            }
                        ]
                    }
                ],
                max_completion_tokens=1400,
                response_format={"type": "json_object"}
            )

            content = response.choices[0].message.content

            if not content:
                raise ValueError(
                    "Thumbnail vision QA returned an empty response."
                )

            return normalize_thumbnail_vision_qa(
                raw_result=extract_json(content),
                standard=standard
            )

        except Exception as exc:
            last_error = exc

            if attempt < 3:
                time.sleep(attempt * 2)

    raise RuntimeError(
        "Thumbnail vision QA failed after retries: "
        f"{last_error}"
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
    thumbnail_standard = load_thumbnail_standard(
        channel=context["channel"]
    )
    concept_types = thumbnail_standard[
        "concept_system"
    ]["required_concept_types"]
    candidate_count = int(
        thumbnail_standard[
            "concept_system"
        ]["candidate_count"]
    )
    channel_name = thumbnail_standard.get(
        "channel_display_name",
        context["channel"].replace("_", " ").title(),
    )
    visual_style_lines = thumbnail_standard[
        "visual_tone"
    ].get("style_lines", [])

    thumbnail_hint = (
        get_thumbnail_hint(thumbnail_strategy_data)
        or normalize_overlay_text(
            seo_payload.get("thumbnail_text")
        )
    )

    prompt = f"""
You are the visual director for {channel_name}, a premium English
documentary YouTube channel.

Create a topic-specific visual production plan for this exact video.

CHANNEL: {context["channel"]}
VIDEO_ID: {context["video_id"]}
RUN_ID: {context["run_id"]}
VIDEO_TITLE: {context["topic_title"]}
SEO_TITLE: {seo_payload.get("video_title", "")}
THUMBNAIL_TEXT_HINT: {thumbnail_hint or "none"}
THUMBNAIL_STANDARD: {thumbnail_standard["standard_name"]}

SCRIPT:
{json.dumps(script_payload, ensure_ascii=True)}

OPTIONAL_VISUAL_ASSET_PLAN:
{json.dumps(asset_payload, ensure_ascii=True)}

Return one JSON object with exactly this structure:

{{
  "thumbnail_concepts": [
    {{
      "concept_id": "THUMB-01",
      "concept_type": "one required concept type",
      "overlay_text": "2 to 4 English words in uppercase",
      "dominant_subject": "one precise topic-specific subject",
      "conflict": "clear visual tension or consequence",
      "emotional_trigger": "curiosity, urgency, shock, or risk",
      "visual_hook": "one instantly understandable visual idea",
      "differentiation": "why this concept is unlike the other two",
      "topic_keywords": ["three topic-specific keywords"],
      "background_prompt": "detailed cinematic background prompt with no text"
    }}
  ],
  "inserts": [
    {{
      "section_hint": "short section name",
      "visual_role": "short visual role",
      "target_duration_seconds": 5,
      "prompt": "specific cinematic 16:9 documentary still prompt"
    }}
  ]
}}

THUMBNAIL CONCEPT CONTRACT:
- Return exactly {candidate_count} thumbnail concepts.
- Use each concept_type exactly once:
  {json.dumps(concept_types, ensure_ascii=True)}
- Interpret each concept type literally and make it visually distinct.
- The three concepts must use different headlines and dominant subjects.
- The supplied thumbnail hint may be used for only one concept.
- Each concept must contain one clear visual story, not a collage.
- Each background prompt must require subject on the right or center-right,
  clean dark negative space on the left, one dominant subject,
  premium cinematic lighting, high contrast, depth, visual tension,
  and no text.
- Do not output small variations of the same scene.
- Do not fabricate evidence, quotes, arrests, documents, or criminal implications.

AI INSERT CONTRACT:
- Return exactly {image_count} inserts.
- Every insert must directly match this exact video topic and script.
- Cover the hook, key explanations, human layer, turning point,
  failure or tension point, and conclusion.
- Every visual must be meaningfully different.
- Use realistic premium documentary imagery.
- Do not reuse imagery from another video topic.
- No logos, readable labels, private data, fake dashboards,
  fabricated evidence, or embedded text.

CHANNEL HOUSE STYLE:
- standard: {thumbnail_standard["standard_name"]}
- layout: {thumbnail_standard["layout"]["layout_signature"]}
- primary text: {thumbnail_standard["text"]["primary_color"]}
- emphasis text: {thumbnail_standard["text"]["highlight_color"]}
- style rules: {json.dumps(visual_style_lines, ensure_ascii=True)}
"""

    raw_plan = call_text_model(prompt=prompt, model=text_model)
    concepts = validate_thumbnail_concepts(
        concepts=raw_plan.get("thumbnail_concepts", []),
        video_topic=context["topic_title"],
        standard=thumbnail_standard
    )
    concepts = sorted(
        concepts,
        key=lambda item: item["preflight_score"],
        reverse=True
    )
    raw_items = raw_plan.get("inserts", [])

    if len(raw_items) != image_count:
        raise ValueError(
            f"Expected {image_count} AI inserts, "
            f"received {len(raw_items)}."
        )

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
                "no logos, no readable text, no barcodes, "
                "no QR codes, no brand names, no private data, "
                "no fake UI, no fabricated evidence, no fake quote, "
                "no fake arrest, no distorted hands, no cartoon style"
            ),
            "status": "planned"
        })

    strongest_preflight = concepts[0]

    return {
        "channel": context["channel"],
        "video_id": context["video_id"],
        "run_id": context["run_id"],
        "video_title": context["topic_title"],
        "thumbnail_system_version": str(
            thumbnail_standard["version"]
        ),
        "thumbnail_standard_name": thumbnail_standard[
            "standard_name"
        ],
        "thumbnail_candidates": concepts,
        "thumbnail": {
            "overlay_text": strongest_preflight["overlay_text"],
            "text_position": "left",
            "background_prompt": strongest_preflight[
                "background_prompt"
            ],
            "preflight_selected_concept_id": strongest_preflight[
                "concept_id"
            ]
        },
        "ai_visual_insert_plan": {
            "style_rules": [
                "realistic documentary look",
                "premium cinematic lighting",
                *visual_style_lines,
                "16:9 composition",
                "no embedded text"
            ],
            "negative_rules": [
                "no unrelated previous-video imagery",
                "no logos",
                "no readable labels",
                "no private information",
                "no fake operational interface",
                "no fabricated evidence",
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
        Path("C:/Windows/Fonts/impact.ttf"),
        Path("C:/Windows/Fonts/ariblk.ttf"),
        Path("C:/Windows/Fonts/arialbd.ttf")
    ]

    for font_path in font_paths:
        if font_path.exists():
            return ImageFont.truetype(str(font_path), size=size)

    return ImageFont.load_default()


def apply_thumbnail_text_gradient(
    image: Image.Image,
    standard: dict
) -> Image.Image:
    overlay_spec = build_thumbnail_overlay_spec(standard)

    if not overlay_spec.get("text_side_gradient", True):
        return image

    width, height = image.size
    end_x = max(1, int(
        width * float(overlay_spec["gradient_end_ratio"])
    ))
    max_alpha = int(overlay_spec["gradient_max_alpha"])
    gradient = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    gradient_draw = ImageDraw.Draw(gradient, "RGBA")

    for x in range(end_x):
        progress = x / max(1, end_x - 1)
        alpha = int(max_alpha * ((1.0 - progress) ** 1.7))
        gradient_draw.line(
            [(x, 0), (x, height)],
            fill=(0, 0, 0, alpha)
        )

    return Image.alpha_composite(
        image.convert("RGBA"),
        gradient
    ).convert("RGB")


def hex_to_rgba(value: str) -> tuple[int, int, int, int]:
    normalized = str(value).strip().lstrip("#")

    if len(normalized) != 6:
        raise ValueError(f"Invalid RGB hex value: {value}")

    return (
        int(normalized[0:2], 16),
        int(normalized[2:4], 16),
        int(normalized[4:6], 16),
        255,
    )


def create_thumbnail(
    background_path: Path,
    output_path: Path,
    overlay_text: str,
    text_position: str,
    standard: dict | None = None,
) -> dict:
    standard = standard or load_thumbnail_standard()
    text_result = assert_thumbnail_text(
        value=overlay_text,
        standard=standard
    )
    overlay_spec = build_thumbnail_overlay_spec(standard)
    line_specs = build_thumbnail_lines(
        text_result["normalized_text"],
        standard
    )

    colors = {
        "primary_white": hex_to_rgba(
            standard["text"]["primary_color"]
        ),
        "highlight_yellow": hex_to_rgba(
            standard["text"]["highlight_color"]
        ),
    }
    lines = [
        (item["text"], colors[item["color_role"]])
        for item in line_specs
    ]

    canvas_width = int(overlay_spec["canvas_width"])
    canvas_height = int(overlay_spec["canvas_height"])

    with Image.open(background_path) as source:
        image = ImageOps.fit(
            source.convert("RGB"),
            (canvas_width, canvas_height),
            method=Image.Resampling.LANCZOS
        )

    image = apply_thumbnail_text_gradient(image, standard)
    draw = ImageDraw.Draw(image, "RGBA")
    target_width_min = int(
        canvas_width
        * float(standard["layout"]["text_area_ratio_min"])
    )
    target_width_max = int(
        canvas_width
        * float(standard["layout"]["text_area_ratio_max"])
    )
    target_height_max = int(
        canvas_height
        * float(overlay_spec["max_text_height_ratio"])
    )
    stroke_width = int(overlay_spec["stroke_width_px"])
    shadow_offset = int(overlay_spec["shadow_offset_px"])
    font_size = int(overlay_spec["font_size_start_px"])
    font_size_min = int(overlay_spec["font_size_min_px"])
    font_step = int(overlay_spec["font_step_px"])

    def measure(current_font):
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

    while font_size > font_size_min:
        font = get_font(font_size)
        widths, heights = measure(font)
        line_gap = max(2, int(
            font_size * float(overlay_spec["line_gap_ratio"])
        ))
        total_height = sum(heights) + line_gap * (len(lines) - 1)

        if (
            max(widths) <= target_width_max
            and total_height <= target_height_max
        ):
            break

        font_size -= font_step

    font = get_font(font_size)
    widths, heights = measure(font)
    line_gap = max(2, int(
        font_size * float(overlay_spec["line_gap_ratio"])
    ))
    total_height = sum(heights) + line_gap * (len(lines) - 1)
    y = int((canvas_height - total_height) / 2)
    x = int(overlay_spec["left_margin_px"])

    for index, (line, color) in enumerate(lines):
        height = heights[index]
        draw.text(
            (x + shadow_offset, y + shadow_offset),
            line,
            font=font,
            fill=(0, 0, 0, 230),
            stroke_width=stroke_width + 4,
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

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(
        output_path,
        format="JPEG",
        quality=95,
        optimize=True
    )

    max_line_width = max(widths)
    text_width_ratio = round(max_line_width / canvas_width, 4)

    return {
        "font_size": font_size,
        "line_count": len(lines),
        "line_texts": [item["text"] for item in line_specs],
        "highlight_line": line_specs[-1]["text"],
        "highlight_color": standard["text"]["highlight_color"],
        "max_line_width": max_line_width,
        "text_width_ratio": text_width_ratio,
        "text_width_target_min": round(
            target_width_min / canvas_width,
            4
        ),
        "text_width_target_max": round(
            target_width_max / canvas_width,
            4
        ),
        "text_block_height_ratio": round(
            total_height / canvas_height,
            4
        ),
        "stroke_width": stroke_width,
        "shadow_offset": shadow_offset,
        "layout_signature": overlay_spec["layout_signature"],
        "text_position": overlay_spec["text_position"],
        "subject_position": overlay_spec["subject_position"],
        "gold_reference_path": overlay_spec[
            "gold_reference_path"
        ],
        "gold_reference_sha256": overlay_spec[
            "gold_reference_sha256"
        ],
        "standard_name": standard["standard_name"],
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
    thumbnail_qa_model: str,
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
    candidate_dir = output_dir / "thumbnail_candidates"
    thumbnail_standard = load_thumbnail_standard(channel=channel)
    concept_system = thumbnail_standard["concept_system"]
    candidates = plan.get("thumbnail_candidates", [])

    candidates = validate_thumbnail_concepts(
        concepts=candidates,
        video_topic=context["topic_title"],
        standard=thumbnail_standard
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    image_dir.mkdir(parents=True, exist_ok=True)
    candidate_dir.mkdir(parents=True, exist_ok=True)

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

    candidate_results = []

    for sequence, concept in enumerate(candidates, start=1):
        concept_id = concept["concept_id"]
        safe_id = concept_id.lower().replace("_", "-")
        background_path = (
            candidate_dir
            / f"{safe_id}_background.png"
        )
        candidate_path = (
            candidate_dir
            / f"{safe_id}.jpg"
        )
        thumbnail_prompt = (
            build_thumbnail_background_prompt(
                video_topic=context["topic_title"],
                main_subject=concept["dominant_subject"],
                thumbnail_text=concept["overlay_text"],
                text_position="left",
                standard=thumbnail_standard,
                concept_type=concept["concept_type"],
                conflict=concept["conflict"],
                emotional_trigger=concept[
                    "emotional_trigger"
                ],
                visual_hook=concept["visual_hook"]
            )
        )

        reuse_background = (
            not force_regenerate
            and existing_image_is_valid(background_path)
        )
        reuse_candidate = (
            not force_regenerate
            and existing_image_is_valid(candidate_path)
        )

        if reuse_background:
            print(
                f"Reusing thumbnail background {concept_id}.",
                flush=True
            )
        else:
            print(
                f"Generating thumbnail background {concept_id}.",
                flush=True
            )
            background_path.write_bytes(
                generate_image_bytes(
                    client=get_image_client(),
                    model=image_model,
                    prompt=thumbnail_prompt,
                    size=image_size,
                    quality=image_quality
                )
            )

        if reuse_candidate:
            print(
                f"Reusing thumbnail candidate {concept_id}.",
                flush=True
            )
            layout_metrics = None
        else:
            layout_metrics = create_thumbnail(
                background_path=background_path,
                output_path=candidate_path,
                overlay_text=concept["overlay_text"],
                text_position="left",
                standard=thumbnail_standard
            )

        if layout_metrics is None:
            layout_metrics = create_thumbnail(
                background_path=background_path,
                output_path=candidate_path,
                overlay_text=concept["overlay_text"],
                text_position="left",
                standard=thumbnail_standard
            )

        technical_inspection = inspect_image(
            candidate_path
        )
        qa_checklist = build_thumbnail_qa_checklist(
            thumbnail_text=concept["overlay_text"],
            standard=thumbnail_standard
        )
        automatic_checks = qa_checklist[
            "automatic_checks"
        ]
        minimum_font_size = int(
            thumbnail_standard["overlay"][
                "font_size_min_px"
            ]
        )
        automatic_checks.update({
            "text_is_oversized": (
                layout_metrics["font_size"]
                >= minimum_font_size
            ),
            "last_line_uses_highlight_color": (
                bool(layout_metrics["highlight_line"])
            ),
            "mobile_readability_passed": (
                layout_metrics["font_size"]
                >= minimum_font_size
                and layout_metrics[
                    "text_width_ratio"
                ] >= 0.30
            ),
            "standard_layout_applied": (
                layout_metrics["layout_signature"]
                == thumbnail_standard["layout"][
                    "layout_signature"
                ]
            ),
            "text_position_locked_left": (
                layout_metrics["text_position"] == "left"
            ),
            "subject_position_locked_right": (
                layout_metrics["subject_position"] == "right"
            ),
            "gold_reference_traceable": (
                layout_metrics["gold_reference_sha256"]
                == thumbnail_standard["gold_reference"][
                    "sha256"
                ]
            ),
            "technical_image_valid": (
                technical_inspection["approved"]
            ),
        })
        automatic_passed = all(
            value is True
            for value in automatic_checks.values()
        )

        vision_qa = call_thumbnail_vision_qa(
            image_path=candidate_path,
            concept=concept,
            video_topic=context["topic_title"],
            model=thumbnail_qa_model,
            standard=thumbnail_standard
        )
        combined_score = combine_thumbnail_scores(
            preflight_score=concept[
                "preflight_score"
            ],
            vision_score=vision_qa[
                "average_score"
            ],
            standard=thumbnail_standard
        )
        approved = (
            automatic_passed
            and vision_qa["approved"]
            and combined_score["approved"]
        )

        candidate_results.append({
            "sequence": sequence,
            "concept_id": concept_id,
            "concept_type": concept["concept_type"],
            "overlay_text": concept["overlay_text"],
            "dominant_subject": concept[
                "dominant_subject"
            ],
            "conflict": concept["conflict"],
            "emotional_trigger": concept[
                "emotional_trigger"
            ],
            "visual_hook": concept["visual_hook"],
            "differentiation": concept[
                "differentiation"
            ],
            "background_prompt": concept[
                "background_prompt"
            ],
            "background_relative_path": relative_path(
                background_path
            ),
            "relative_path": relative_path(
                candidate_path
            ),
            "preflight_score": concept[
                "preflight_score"
            ],
            "vision_qa": vision_qa,
            "final_score": combined_score[
                "final_score"
            ],
            "minimum_final_score": combined_score[
                "minimum_score"
            ],
            "layout_metrics": layout_metrics,
            "automatic_checks": automatic_checks,
            "automatic_checks_passed": automatic_passed,
            "approved": approved,
        })

    approved_candidates = sorted(
        [
            item
            for item in candidate_results
            if item["approved"]
        ],
        key=lambda item: item["final_score"],
        reverse=True
    )

    if not approved_candidates:
        score_summary = ", ".join(
            (
                f"{item['concept_id']}="
                f"{item['final_score']}"
            )
            for item in candidate_results
        )
        raise ValueError(
            "All thumbnail candidates failed v3 QA: "
            + score_summary
        )

    selected = approved_candidates[0]
    finalist_count = int(
        concept_system["finalist_count"]
    )
    finalists = approved_candidates[
        :finalist_count
    ]

    if len(finalists) < finalist_count:
        raise ValueError(
            "Thumbnail v3 did not produce enough approved finalists."
        )

    thumbnail_path = output_dir / "thumbnail.jpg"
    thumbnail_background_path = (
        image_dir / "thumbnail_background.png"
    )
    shutil.copy2(
        PROJECT_ROOT / selected["relative_path"],
        thumbnail_path
    )
    shutil.copy2(
        PROJECT_ROOT
        / selected["background_relative_path"],
        thumbnail_background_path
    )

    candidate_record = {
        "agent": "thumbnail_candidate_selector",
        "version": "3.0",
        "channel": channel,
        "video_id": video_id,
        "run_id": context["run_id"],
        "status": "winner_selected",
        "candidate_count": len(candidate_results),
        "approved_candidate_count": len(
            approved_candidates
        ),
        "rejected_candidate_count": (
            len(candidate_results)
            - len(approved_candidates)
        ),
        "selected_concept_id": selected[
            "concept_id"
        ],
        "selected_final_score": selected[
            "final_score"
        ],
        "finalists": [
            {
                "concept_id": item["concept_id"],
                "concept_type": item["concept_type"],
                "overlay_text": item["overlay_text"],
                "relative_path": item["relative_path"],
                "final_score": item["final_score"],
            }
            for item in finalists
        ],
        "candidates": candidate_results,
        "selection_policy": (
            "highest_scoring_approved_candidate"
        ),
        "founder_review_scope": "finalists_only",
    }
    candidate_record_path = (
        output_dir / "thumbnail_candidates.json"
    )
    save_json(
        candidate_record_path,
        candidate_record
    )

    selected_qa = build_thumbnail_qa_checklist(
        thumbnail_text=selected["overlay_text"],
        standard=thumbnail_standard
    )
    selected_qa["automatic_checks"].update(
        selected["automatic_checks"]
    )
    selected_qa["vision_qa"] = selected[
        "vision_qa"
    ]
    selected_qa["final_score"] = selected[
        "final_score"
    ]
    selected_qa["automatic_text_checks_passed"] = (
        selected["automatic_checks_passed"]
        and selected["vision_qa"]["approved"]
    )

    thumbnail_output = {
        "agent": "video_visual_pipeline",
        "version": "3.0",
        "channel": channel,
        "video_id": video_id,
        "run_id": context["run_id"],
        "status": "thumbnail_ready",
        "thumbnail": {
            "standard_name": thumbnail_standard[
                "standard_name"
            ],
            "previous_standard_name": (
                LEGACY_THUMBNAIL_STANDARD_NAME
            ),
            "system_version": "3.0",
            "overlay_text": selected[
                "overlay_text"
            ],
            "text_position": "left",
            "selected_concept_id": selected[
                "concept_id"
            ],
            "selected_concept_type": selected[
                "concept_type"
            ],
            "selected_final_score": selected[
                "final_score"
            ],
            "relative_path": relative_path(
                thumbnail_path
            ),
            "size_bytes": (
                thumbnail_path.stat().st_size
            ),
            "width": 1280,
            "height": 720,
            "gold_reference": thumbnail_standard[
                "gold_reference"
            ],
            "layout_signature": thumbnail_standard[
                "layout"
            ]["layout_signature"],
            "text_style": {
                "size": "oversized",
                "weight": "extra_bold_condensed",
                "two_color": True,
                "colors": [
                    "white",
                    "yellow"
                ],
                "stroke": "black",
                "stroke_weight": "strong",
                "mobile_readable": True
            },
            "layout_metrics": selected[
                "layout_metrics"
            ],
            "qa": selected_qa,
            "candidate_record": relative_path(
                candidate_record_path
            ),
            "finalists": candidate_record[
                "finalists"
            ],
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
        "thumbnail": thumbnail_output,
        "thumbnail_candidates": candidate_record
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
        default=None,
        help=(
            "Optional AI image count. When omitted, use the "
            "video context minimum_ai_insert_count gate."
        )
    )
    parser.add_argument(
        "--text-model",
        default=os.getenv(
            "OPENAI_TEXT_MODEL",
            DEFAULT_TEXT_MODEL
        )
    )
    parser.add_argument(
        "--thumbnail-qa-model",
        default=os.getenv(
            "OPENAI_THUMBNAIL_QA_MODEL",
            os.getenv(
                "OPENAI_TEXT_MODEL",
                DEFAULT_TEXT_MODEL
            )
        ),
        help=(
            "Multimodal model used to score actual rendered "
            "thumbnail candidates."
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

    content_approval = effective_content_approval(
        project_root=PROJECT_ROOT,
        context=context,
        qa_data=qa_data,
    )

    if not content_approval["approved"]:
        raise ValueError(
            "Content approval is not valid: "
            f"{content_approval['reason']}"
        )

    print(
        "CONTENT_APPROVAL_SOURCE: "
        f"{content_approval['source']}"
    )
    print(
        "CONTENT_APPROVAL_REASON: "
        f"{content_approval['reason']}"
    )

    minimum_ai_count = int(
        context.get(
            "quality_gates",
            {}
        ).get("minimum_ai_insert_count", DEFAULT_IMAGE_COUNT)
    )
    effective_image_count = (
        int(args.image_count)
        if args.image_count is not None
        else minimum_ai_count
    )

    if effective_image_count < minimum_ai_count:
        raise ValueError(
            f"AI insert count must be at least {minimum_ai_count}."
        )

    output_dir = get_output_dir(
        channel,
        video_id,
        context["run_id"]
    )
    thumbnail_standard = load_thumbnail_standard(
        channel=channel
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
    print(
        "THUMBNAIL_STYLE: "
        f"{thumbnail_standard['standard_name']}"
    )

    if args.dry_run:
        print("STATUS: visual_pipeline_dry_run_ready")
        print(f"PLANNED_AI_INSERT_COUNT: {effective_image_count}")
        print(
            "THUMBNAIL_CANDIDATE_COUNT: "
            f"{thumbnail_standard['concept_system']['candidate_count']}"
        )
        print(
            "THUMBNAIL_FINALIST_COUNT: "
            f"{thumbnail_standard['concept_system']['finalist_count']}"
        )
        print("THUMBNAIL_VISION_QA_REQUIRED: true")
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
        candidate_count = int(
            thumbnail_standard["concept_system"][
                "candidate_count"
            ]
        )
        planned_candidates = plan.get(
            "thumbnail_candidates",
            []
        )
        v3_plan_ready = (
            str(plan.get("thumbnail_system_version"))
            == str(thumbnail_standard["version"])
            and len(planned_candidates) == candidate_count
        )

        if (
            len(planned_items) != effective_image_count
            or not v3_plan_ready
        ):
            plan = build_dynamic_plan(
                context=context,
                script_data=script_data,
                seo_data=seo_data,
                visual_asset_plan_data=visual_asset_plan_data,
                thumbnail_strategy_data=thumbnail_strategy_data,
                text_model=args.text_model,
                image_count=effective_image_count
            )
            save_json(plan_path, plan)
            print(
                "VISUAL_PLAN_MODE: regenerated_for_channel_contract"
            )
        else:
            print("VISUAL_PLAN_MODE: reused_existing")
    else:
        plan = build_dynamic_plan(
            context=context,
            script_data=script_data,
            seo_data=seo_data,
            visual_asset_plan_data=visual_asset_plan_data,
            thumbnail_strategy_data=thumbnail_strategy_data,
            text_model=args.text_model,
            image_count=effective_image_count
        )

        save_json(plan_path, plan)
        print("VISUAL_PLAN_MODE: generated")

    outputs = generate_outputs(
        context=context,
        plan=plan,
        image_model=args.image_model,
        image_size=args.image_size,
        image_quality=args.image_quality,
        thumbnail_qa_model=args.thumbnail_qa_model,
        force_regenerate=args.force_regenerate
    )

    context.setdefault(
        "quality_gates",
        {}
    ).update({
        "allow_cross_video_asset_reuse": False,
        "require_visual_asset_registry_ownership": True,
        "require_thumbnail_asset_registry_ownership": True,
        "require_channel_thumbnail_standard": True,
        "require_hiddenova_thumbnail_standard": (
            channel == "hiddenova"
        ),
        "thumbnail_style": thumbnail_standard["standard_name"],
        "thumbnail_standard_name": thumbnail_standard[
            "standard_name"
        ],
        "thumbnail_previous_standard_name": (
            LEGACY_THUMBNAIL_STANDARD_NAME
            if channel == "hiddenova"
            else None
        ),
        "thumbnail_candidate_count": int(
            thumbnail_standard["concept_system"]["candidate_count"]
        ),
        "thumbnail_finalist_count": int(
            thumbnail_standard["concept_system"]["finalist_count"]
        ),
        "thumbnail_vision_qa_required": True,
        "thumbnail_minimum_final_score": int(
            thumbnail_standard["concept_system"][
                "minimum_final_score"
            ]
        ),
        "thumbnail_text_min_words": int(
            thumbnail_standard["text"]["min_words"]
        ),
        "thumbnail_text_max_words": int(
            thumbnail_standard["text"]["max_words"]
        ),
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
    context = register_output(
        context=context,
        agent="thumbnail_candidates",
        reference=relative_path(
            output_dir / "thumbnail_candidates.json"
        ),
        status="winner_selected"
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
    print(
        "THUMBNAIL_STANDARD: "
        f"{outputs['thumbnail']['thumbnail']['standard_name']}"
    )
    print(
        "THUMBNAIL_LAYOUT_SIGNATURE: "
        f"{outputs['thumbnail']['thumbnail']['layout_signature']}"
    )
    print(
        "THUMBNAIL_CANDIDATE_COUNT: "
        f"{outputs['thumbnail_candidates']['candidate_count']}"
    )
    print(
        "THUMBNAIL_APPROVED_CANDIDATE_COUNT: "
        f"{outputs['thumbnail_candidates']['approved_candidate_count']}"
    )
    print(
        "THUMBNAIL_SELECTED_CONCEPT: "
        f"{outputs['thumbnail']['thumbnail']['selected_concept_id']}"
    )
    print(
        "THUMBNAIL_SELECTED_SCORE: "
        f"{outputs['thumbnail']['thumbnail']['selected_final_score']}"
    )
    print(
        "THUMBNAIL_FINALISTS: "
        + ", ".join(
            item["relative_path"]
            for item in outputs[
                "thumbnail_candidates"
            ]["finalists"]
        )
    )


if __name__ == "__main__":
    main()
