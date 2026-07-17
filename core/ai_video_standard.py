import json
import math
from pathlib import Path


DEFAULT_PROVIDER = "gemini_omni_flash"
DEFAULT_MODEL = "gemini-omni-flash-preview"
DEFAULT_INSERT_COUNT = 4
MIN_INSERT_COUNT = 4
MAX_INSERT_COUNT = 6
DEFAULT_TARGET_DURATION_SECONDS = 6
MIN_DURATION_SECONDS = 3
MAX_DURATION_SECONDS = 10
DEFAULT_ASPECT_RATIO = "16:9"
PROVIDER_CONFIG_VERSION = "1.0"


def load_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Required file not found: {path}")

    return json.loads(path.read_text(encoding="utf-8-sig"))


def validate_insert_count(count: int) -> int:
    count = int(count)

    if count < MIN_INSERT_COUNT or count > MAX_INSERT_COUNT:
        raise ValueError(
            "AI video insert count must be between "
            f"{MIN_INSERT_COUNT} and {MAX_INSERT_COUNT}."
        )

    return count


def validate_duration_seconds(value: float) -> float:
    value = float(value)

    if value < MIN_DURATION_SECONDS or value > MAX_DURATION_SECONDS:
        raise ValueError(
            "AI video duration must be between "
            f"{MIN_DURATION_SECONDS} and {MAX_DURATION_SECONDS} seconds."
        )

    return value


def evenly_spaced_indexes(item_count: int, selected_count: int) -> list[int]:
    if item_count <= 0:
        raise ValueError("item_count must be positive.")

    if selected_count <= 0:
        raise ValueError("selected_count must be positive.")

    if selected_count > item_count:
        raise ValueError(
            "Cannot select more AI video references than available images."
        )

    if selected_count == 1:
        return [0]

    last = item_count - 1
    indexes = [
        round(index * last / (selected_count - 1))
        for index in range(selected_count)
    ]

    if len(set(indexes)) != selected_count:
        raise ValueError("Even selection created duplicate indexes.")

    return indexes


def approved_image_items(
    generation_data: dict,
    qa_data: dict
) -> list[dict]:
    approved_ids = {
        item["insert_id"]
        for item in qa_data.get("image_checks", [])
        if item.get("approved") is True
    }

    items = [
        item
        for item in generation_data.get("generated_images", [])
        if item.get("insert_id") in approved_ids
    ]

    return sorted(
        items,
        key=lambda item: (
            int(item.get("sequence", 9999)),
            str(item.get("insert_id", ""))
        )
    )


def assert_identity(data: dict, context: dict, label: str) -> None:
    for key in ("channel", "video_id", "run_id"):
        if data.get(key) != context.get(key):
            raise ValueError(
                f"{label} {key} does not match video context."
            )


def build_motion_prompt(
    context: dict,
    image_item: dict
) -> str:
    section = str(image_item.get("section_hint", "Documentary scene"))
    role = str(image_item.get("visual_role", "cinematic documentary visual"))
    original_prompt = str(image_item.get("prompt", "")).strip()

    return (
        "Animate the supplied reference image into a premium cinematic "
        "documentary shot for Hiddenova. "
        f"Video topic: {context['topic_title']}. "
        f"Section: {section}. Visual role: {role}. "
        "Preserve the reference composition, subject identity, lighting, "
        "and factual visual meaning. Add subtle realistic subject motion, "
        "environmental motion, depth parallax, and one controlled camera "
        "movement. Keep the shot coherent and suitable for a serious "
        "technology documentary. Do not add text, captions, logos, "
        "watermarks, dialogue, narration, music, or sound effects. "
        "Avoid morphing, warped objects, duplicate subjects, extra fingers, "
        "fake interfaces, unreadable UI, surreal transitions, or sudden cuts. "
        f"Reference scene intent: {original_prompt}"
    )


def build_plan(
    context: dict,
    generation_data: dict,
    qa_data: dict,
    count: int = DEFAULT_INSERT_COUNT,
    provider: str = DEFAULT_PROVIDER,
    model: str = DEFAULT_MODEL,
    target_duration_seconds: int = DEFAULT_TARGET_DURATION_SECONDS
) -> dict:
    count = validate_insert_count(count)
    target_duration_seconds = int(
        validate_duration_seconds(target_duration_seconds)
    )

    assert_identity(generation_data, context, "AI visual generation")
    assert_identity(qa_data, context, "AI visual QA")

    if generation_data.get("status") != "images_ready":
        raise ValueError("AI visual generation is not images_ready.")

    if qa_data.get("status") != "approved":
        raise ValueError("AI visual QA is not approved.")

    available = approved_image_items(
        generation_data=generation_data,
        qa_data=qa_data
    )

    if len(available) < count:
        raise ValueError(
            "Not enough approved AI images for the requested "
            "AI video insert count."
        )

    indexes = evenly_spaced_indexes(
        item_count=len(available),
        selected_count=count
    )

    items = []

    for sequence, source_index in enumerate(indexes, start=1):
        image_item = available[source_index]
        items.append({
            "insert_id": f"AIV-{sequence:03d}",
            "sequence": sequence,
            "source_ai_image_insert_id": image_item["insert_id"],
            "section_hint": image_item.get("section_hint"),
            "visual_role": image_item.get("visual_role"),
            "reference_image_path": image_item["relative_path"],
            "prompt": build_motion_prompt(
                context=context,
                image_item=image_item
            ),
            "task": "image_to_video",
            "aspect_ratio": DEFAULT_ASPECT_RATIO,
            "target_duration_seconds": target_duration_seconds,
            "status": "planned"
        })

    return {
        "agent": "ai_video_insert_plan",
        "version": "1.0",
        "channel": context["channel"],
        "video_id": context["video_id"],
        "run_id": context["run_id"],
        "status": "plan_ready",
        "provider": {
            "provider_id": provider,
            "model": model,
            "api_mode": "interactions",
            "preview": True
        },
        "summary": {
            "planned_insert_count": len(items),
            "target_duration_seconds_each": target_duration_seconds,
            "planned_total_duration_seconds": (
                len(items) * target_duration_seconds
            ),
            "source_approved_image_count": len(available),
            "production_api_called": False
        },
        "items": items,
        "source": {
            "ai_visual_generation_reference": (
                context["outputs"]["ai_visual_generation"]
            ),
            "ai_visual_qa_reference": (
                context["outputs"]["ai_visual_qa"]
            ),
            "topic_title": context["topic_title"]
        },
        "readiness": {
            "dry_run_ready": True,
            "mock_generation_ready": True,
            "live_generation_ready": False,
            "blocking_notes": [
                "Live provider connection has not been approved or tested."
            ]
        }
    }


def validate_plan_identity(plan: dict, context: dict) -> None:
    assert_identity(plan, context, "AI video insert plan")

    if plan.get("status") != "plan_ready":
        raise ValueError("AI video insert plan is not ready.")

    items = plan.get("items", [])
    validate_insert_count(len(items))

    ids = [item.get("insert_id") for item in items]

    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate AI video insert ids detected.")

    for item in items:
        if item.get("task") != "image_to_video":
            raise ValueError("AI video task must be image_to_video.")

        if item.get("aspect_ratio") != DEFAULT_ASPECT_RATIO:
            raise ValueError("AI video aspect ratio must be 16:9.")

        validate_duration_seconds(
            item.get("target_duration_seconds", 0)
        )
