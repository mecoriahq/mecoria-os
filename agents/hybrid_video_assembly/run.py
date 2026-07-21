import argparse
import json
import math
import re
import subprocess
from datetime import datetime
import sys
from pathlib import Path

import imageio_ffmpeg
from dotenv import load_dotenv
from jsonschema import validate

from output import save_output


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.video_run_context import (
    load_context,
    register_output,
    save_context,
    set_status,
)


from core.asset_usage_registry import (
    assert_asset_registered,
    build_asset_record,
    register_asset_batch,
)

from core.content_quality import (
    DEFAULT_MEDIA_DURATION_MAX_SECONDS,
    DEFAULT_MEDIA_DURATION_MIN_SECONDS,
    evaluate_duration_seconds,
)
from core.ai_video_integration import (
    ai_video_context_enabled,
    interleave_ai_specs,
)
from core.hybrid_capacity import (
    CAPACITY_CONTRACT_VERSION,
    HybridCapacityError,
    build_hybrid_capacity_report,
    materialize_hybrid_capacity_plan,
    build_stock_segment_specs as shared_build_stock_segment_specs,
    expand_ai_image_specs_for_target as shared_expand_ai_image_specs_for_target,
    expand_stock_specs_for_target as shared_expand_stock_specs_for_target,
    maximum_stock_spec_duration as shared_maximum_stock_spec_duration,
)

DEFAULT_CHANNEL = "hiddenova"
OUTPUT_FILENAME = "hybrid_video_draft.mp4"
VIDEO_WIDTH = 1920
VIDEO_HEIGHT = 1080
FPS = 30

STOCK_SEGMENT_SECONDS = 6
MAX_ADAPTIVE_STOCK_SEGMENT_SECONDS = 8
MAX_AI_IMAGE_SEGMENT_SECONDS = 13.0
DURATION_EPSILON_SECONDS = 0.001
TIMELINE_TAIL_PADDING_SECONDS = 3.0
AI_INSERT_AFTER_STOCK_SEGMENTS = 2
VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".mkv"}

def load_json(file_path: Path) -> dict:
    if not file_path.exists():
        raise FileNotFoundError(f"Required file not found: {file_path}")

    return json.loads(file_path.read_text(encoding="utf-8-sig"))


def load_schema() -> dict:
    return load_json(BASE_DIR / "schema.json")


def get_audio_assembly_latest_path(
    channel: str,
    video_id: str | None = None
) -> Path:
    if video_id:
        context_path = (
            PROJECT_ROOT
            / "records"
            / "run_contexts"
            / channel.lower()
            / f"{video_id.lower()}.json"
        )
        context_data = load_json(context_path)

        reference = (
            context_data.get("outputs", {}).get("audio_assembly")
            or context_data.get("sources", {}).get("audio_assembly")
        )

        if not reference:
            raise ValueError(
                "Run context has no audio_assembly reference."
            )

        normalized = reference.replace("\\", "/").lower()

        if normalized.endswith("/latest.json"):
            raise ValueError(
                "Production audio source cannot use latest.json."
            )

        return PROJECT_ROOT / reference

    extended_audio_path = (
        PROJECT_ROOT
        / "agents"
        / "intro_outro_audio_assembly"
        / "output"
        / channel.lower()
        / "latest.json"
    )
    audio_assembly_path = (
        PROJECT_ROOT
        / "agents"
        / "audio_assembly"
        / "output"
        / channel.lower()
        / "latest.json"
    )

    if extended_audio_path.exists():
        return extended_audio_path

    return audio_assembly_path



def get_publisher_latest_path(channel: str) -> Path:
    return PROJECT_ROOT / "agents" / "publisher" / "output" / channel.lower() / "latest.json"


def get_stock_manifest_path(
    channel: str,
    video_id: str | None = None
) -> Path:
    if video_id:
        return get_video_context_reference_path(
            channel=channel,
            video_id=video_id,
            key="stock_manifest"
        )

    return (
        PROJECT_ROOT
        / "records"
        / "assets"
        / channel.lower()
        / "stock_footage_manifest.json"
    )


def get_stock_qa_path(
    channel: str,
    video_id: str
) -> Path:
    return get_video_context_reference_path(
        channel=channel,
        video_id=video_id,
        key="stock_qa"
    )


def get_video_context_reference_path(
    channel: str,
    video_id: str,
    key: str
) -> Path:
    context_path = (
        PROJECT_ROOT
        / "records"
        / "run_contexts"
        / channel.lower()
        / f"{video_id.lower()}.json"
    )
    context_data = load_json(context_path)

    reference = (
        context_data.get("outputs", {}).get(key)
        or context_data.get("sources", {}).get(key)
    )

    if not reference:
        raise ValueError(
            f"Run context has no {key} reference."
        )

    normalized = reference.replace("\\", "/").lower()

    if normalized.endswith("/latest.json"):
        raise ValueError(
            f"Production source cannot use latest.json: {key}"
        )

    path = PROJECT_ROOT / reference

    if not path.exists():
        raise FileNotFoundError(
            f"Context file not found: {path}"
        )

    return path


def get_ai_generation_latest_path(
    channel: str,
    video_id: str | None = None
) -> Path:
    if video_id:
        return get_video_context_reference_path(
            channel=channel,
            video_id=video_id,
            key="ai_visual_generation"
        )

    return (
        PROJECT_ROOT
        / "agents"
        / "ai_visual_generation"
        / "output"
        / channel.lower()
        / "latest.json"
    )


def get_ai_qa_latest_path(
    channel: str,
    video_id: str | None = None
) -> Path:
    if video_id:
        return get_video_context_reference_path(
            channel=channel,
            video_id=video_id,
            key="ai_visual_qa"
        )

    return (
        PROJECT_ROOT
        / "agents"
        / "ai_visual_qa"
        / "output"
        / channel.lower()
        / "latest.json"
    )


def get_ai_video_generation_path(
    channel: str,
    video_id: str
) -> Path:
    return get_video_context_reference_path(
        channel=channel,
        video_id=video_id,
        key="ai_video_generation"
    )


def get_ai_video_qa_path(
    channel: str,
    video_id: str
) -> Path:
    return get_video_context_reference_path(
        channel=channel,
        video_id=video_id,
        key="ai_video_qa"
    )


def get_relative_path(path: Path) -> str:
    return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")


def get_output_dir(
    channel: str,
    video_id: str | None = None,
    run_id: str | None = None
) -> Path:
    if video_id:
        if not run_id:
            raise ValueError(
                "run_id is required for video-specific render output."
            )

        output_dir = (
            BASE_DIR
            / "output"
            / channel.lower()
            / video_id.lower()
            / run_id
            / "render"
        )
    else:
        timestamp = datetime.now().strftime(
            "%Y-%m-%d_%H-%M-%S"
        )
        output_dir = (
            BASE_DIR
            / "output"
            / channel.lower()
            / "drafts"
            / timestamp
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def run_ffmpeg(command: list[str], error_label: str) -> None:
    result = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"{error_label} failed:\n"
            + result.stderr[-4000:]
        )


def get_media_duration_seconds(media_path: Path) -> float:
    ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()

    result = subprocess.run(
        [
            ffmpeg_path,
            "-hide_banner",
            "-i",
            str(media_path)
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True
    )

    text = result.stderr + result.stdout

    match = re.search(
        r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)",
        text
    )

    if not match:
        raise ValueError(f"Could not read media duration: {media_path}")

    hours = int(match.group(1))
    minutes = int(match.group(2))
    seconds = float(match.group(3))

    return hours * 3600 + minutes * 60 + seconds


def validate_production_duration(
    context: dict | None,
    actual_seconds: float
) -> dict:
    gates = context.get("quality_gates", {}) if context else {}
    minimum = int(
        gates.get(
            "target_audio_duration_min_seconds",
            DEFAULT_MEDIA_DURATION_MIN_SECONDS
        )
    )
    maximum = int(
        gates.get(
            "target_audio_duration_max_seconds",
            DEFAULT_MEDIA_DURATION_MAX_SECONDS
        )
    )

    result = evaluate_duration_seconds(
        actual_seconds=actual_seconds,
        minimum=minimum,
        maximum=maximum
    )

    if not result["approved"]:
        raise ValueError(
            "Render blocked: narration duration must be "
            "between 480 and 720 seconds."
        )

    return result


def validate_ai_insert_requirement(
    context: dict | None,
    ai_specs: list[dict]
) -> dict:
    gates = context.get("quality_gates", {}) if context else {}
    required = bool(gates.get("require_ai_visuals", False))
    minimum = int(gates.get("minimum_ai_insert_count", 0))
    actual = len(ai_specs)

    approved = (
        not required
        or actual >= max(1, minimum)
    )

    if not approved:
        raise ValueError(
            "Render blocked: AI visual insert count is below "
            f"the required minimum. actual={actual} minimum={minimum}."
        )

    return {
        "required": required,
        "minimum": minimum,
        "actual": actual,
        "approved": approved,
    }


def validate_ai_video_insert_requirement(
    context: dict | None,
    ai_video_specs: list[dict]
) -> dict:
    gates = context.get("quality_gates", {}) if context else {}
    required = bool(
        gates.get("require_ai_video_inserts", False)
    )
    minimum = int(
        gates.get("minimum_ai_video_insert_count", 0)
    )
    maximum = int(
        gates.get("maximum_ai_video_insert_count", 6)
    )
    actual = len(ai_video_specs)
    approved = (
        not required
        or minimum <= actual <= maximum
    )

    if not approved:
        raise ValueError(
            "Render blocked: AI video insert count is outside "
            "the required range. "
            f"actual={actual} minimum={minimum} maximum={maximum}."
        )

    return {
        "required": required,
        "minimum": minimum,
        "maximum": maximum,
        "actual": actual,
        "approved": approved,
    }


def stock_video_filter() -> str:
    return (
        f"scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={VIDEO_WIDTH}:{VIDEO_HEIGHT},"
        f"fps={FPS},"
        "setsar=1,"
        "format=yuv420p"
    )


def ai_image_filter(
    duration_seconds: float,
    motion_variant: int = 1
) -> str:
    frames = max(1, int(duration_seconds * FPS))

    if motion_variant % 2 == 0:
        zoompan = (
            "zoompan="
            "z='1.04':"
            f"x='(iw-iw/zoom)*on/{max(1, frames - 1)}':"
            "y='ih/2-(ih/zoom/2)':"
            f"d={frames}:s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:fps={FPS},"
        )
    else:
        zoompan = (
            "zoompan="
            "z='min(1.0+on*0.00045,1.045)':"
            "x='iw/2-(iw/zoom/2)':"
            "y='ih/2-(ih/zoom/2)':"
            f"d={frames}:s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:fps={FPS},"
        )

    return (
        f"scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={VIDEO_WIDTH}:{VIDEO_HEIGHT},"
        + zoompan
        + "setsar=1,"
        + "format=yuv420p"
    )


def ensure_inputs_ready(
    audio_data: dict,
    ai_generation_data: dict,
    ai_qa_data: dict,
    ai_inserts_enabled: bool,
    video_id: str | None
) -> None:
    if audio_data.get("status") != "assembled":
        raise ValueError("Audio Assembly output is not assembled.")

    if not audio_data["readiness"].get("combined_audio_ready"):
        raise ValueError("Combined narration audio is not ready.")

    if not ai_inserts_enabled:
        return

    if ai_generation_data.get("status") != "images_ready":
        raise ValueError("AI Visual Generation output is not images_ready.")

    if ai_qa_data.get("status") != "approved":
        raise ValueError("AI Visual QA output is not approved.")

    if video_id:
        generation_video_id = ai_generation_data.get(
            "source",
            {}
        ).get("video_id")
        qa_video_id = ai_qa_data.get(
            "source",
            {}
        ).get("video_id")

        if generation_video_id != video_id:
            raise ValueError(
                "AI Visual Generation video_id does not match context."
            )

        if qa_video_id != video_id:
            raise ValueError(
                "AI Visual QA video_id does not match context."
            )


def get_audio_path(audio_data: dict) -> Path:
    audio_path = PROJECT_ROOT / audio_data["audio"]["combined_audio"]["relative_path"]

    if not audio_path.exists():
        raise FileNotFoundError(f"Combined audio file not found: {audio_path}")

    return audio_path



def validate_audio_asset_ownership(
    audio_data: dict,
    audio_path: Path,
    context: dict
) -> None:
    audio_video_id = (
        audio_data.get("video_id")
        or audio_data.get("source", {}).get("video_id")
    )
    audio_run_id = (
        audio_data.get("run_id")
        or audio_data.get("source", {}).get("run_id")
    )

    if audio_video_id != context["video_id"]:
        raise ValueError(
            "Audio assembly video_id mismatch."
        )

    if audio_run_id != context["run_id"]:
        raise ValueError(
            "Audio assembly run_id mismatch."
        )

    combined = audio_data.get(
        "audio",
        {}
    ).get("combined_audio", {})

    expected_sha256 = combined.get("sha256")

    if not expected_sha256:
        raise ValueError(
            "Narration audio has no SHA-256 fingerprint."
        )

    declared_path = combined.get("relative_path")

    if (
        not declared_path
        or PROJECT_ROOT / declared_path != audio_path
    ):
        raise ValueError(
            "Narration audio path does not match assembly record."
        )

    assert_asset_registered(
        path=audio_path,
        channel=context["channel"],
        video_id=context["video_id"],
        expected_sha256=expected_sha256
    )


def preferred_stock_sort_key(
    item: dict
) -> tuple[int, str]:
    return (
        int(item.get("usage_priority", 999)),
        str(item["candidate_id"])
    )


def load_stock_clips(
    stock_manifest_data: dict,
    channel: str,
    video_id: str | None,
    run_id: str | None
) -> list[dict]:
    manifest_status = str(
        stock_manifest_data.get("status", "")
    ).lower()

    if not manifest_status.startswith("approved"):
        raise ValueError("Stock manifest is not approved.")

    if (
        stock_manifest_data.get("channel")
        and stock_manifest_data["channel"].lower() != channel
    ):
        raise ValueError("Stock manifest channel mismatch.")

    if video_id:
        manifest_video_id = stock_manifest_data.get(
            "video_id"
        )

        if manifest_video_id and manifest_video_id != video_id:
            raise ValueError("Stock manifest video_id mismatch.")

        manifest_run_id = stock_manifest_data.get("run_id")

        if manifest_run_id and manifest_run_id != run_id:
            raise ValueError("Stock manifest run_id mismatch.")

    clips = []
    used_paths = set()

    for index, item in enumerate(
        stock_manifest_data.get("items", []),
        start=1
    ):
        status = str(item.get("status", "")).lower()

        if not status.startswith("approved"):
            continue

        relative_path = item.get("relative_path")

        if not relative_path:
            continue

        normalized_path = relative_path.replace("\\", "/")

        if normalized_path in used_paths:
            raise ValueError(
                f"Duplicate stock path: {normalized_path}"
            )

        path = PROJECT_ROOT / normalized_path

        if path.suffix.lower() not in VIDEO_EXTENSIONS:
            continue

        if not path.exists():
            raise FileNotFoundError(
                f"Stock footage file not found: {path}"
            )

        if video_id:
            expected_sha256 = item.get("sha256")

            if not expected_sha256:
                raise ValueError(
                    "Stock manifest item has no SHA-256 fingerprint."
                )

            assert_asset_registered(
                path=path,
                channel=channel,
                video_id=video_id,
                expected_sha256=expected_sha256
            )

        used_paths.add(normalized_path)

        clip = dict(item)
        asset_id = str(
            clip.get("asset_id")
            or f"A{index:03d}"
        )
        candidate_id = str(
            clip.get("candidate_id")
            or clip.get("clip_id")
            or f"{asset_id}-C{index:03d}"
        )

        clip["asset_id"] = asset_id
        clip["candidate_id"] = candidate_id
        clip["role"] = clip.get(
            "role",
            "topic_specific_stock_footage"
        )
        clip["risk_level"] = clip.get(
            "risk_level",
            "low"
        )
        clip["usage_priority"] = int(
            clip.get("usage_priority", index)
        )
        clip["path"] = path
        clip["duration_seconds"] = float(
            clip.get("duration_seconds")
            or get_media_duration_seconds(path)
        )

        clips.append(clip)

    if not clips:
        raise ValueError("No usable approved stock clips found.")

    return sorted(
        clips,
        key=preferred_stock_sort_key
    )


def expand_stock_specs_for_target(
    stock_clips: list[dict],
    stock_specs: list[dict],
    target_total_duration: float | None = None,
    maximum_segment_seconds: float = (
        MAX_ADAPTIVE_STOCK_SEGMENT_SECONDS
    ),
    target_total_frames: int | None = None,
) -> list[dict]:
    return shared_expand_stock_specs_for_target(
        stock_clips=stock_clips,
        stock_specs=stock_specs,
        target_total_duration=target_total_duration,
        maximum_segment_seconds=maximum_segment_seconds,
        fps=FPS,
        target_total_frames=target_total_frames,
    )


def build_stock_segment_specs(
    stock_clips: list[dict],
    max_segments_per_clip: int = 5,
    target_total_duration: float | None = None,
    maximum_segment_seconds: float = (
        MAX_ADAPTIVE_STOCK_SEGMENT_SECONDS
    ),
) -> list[dict]:
    return shared_build_stock_segment_specs(
        stock_clips=stock_clips,
        max_segments_per_clip=max_segments_per_clip,
        target_total_duration=target_total_duration,
        maximum_segment_seconds=maximum_segment_seconds,
        stock_segment_seconds=STOCK_SEGMENT_SECONDS,
        fps=FPS,
    )



def maximum_stock_spec_duration(
    stock_clips: list[dict],
    stock_specs: list[dict],
    maximum_segment_seconds: float = (
        MAX_ADAPTIVE_STOCK_SEGMENT_SECONDS
    ),
) -> float:
    return shared_maximum_stock_spec_duration(
        stock_clips=stock_clips,
        stock_specs=stock_specs,
        maximum_segment_seconds=maximum_segment_seconds,
        fps=FPS,
    )


def expand_ai_image_specs_for_target(
    ai_specs: list[dict],
    target_total_duration: float | None = None,
    maximum_uses_per_image: int = 2,
    maximum_segment_seconds: float = (
        MAX_AI_IMAGE_SEGMENT_SECONDS
    ),
    target_total_frames: int | None = None,
) -> list[dict]:
    return shared_expand_ai_image_specs_for_target(
        ai_specs=ai_specs,
        target_total_duration=target_total_duration,
        maximum_uses_per_image=maximum_uses_per_image,
        maximum_segment_seconds=maximum_segment_seconds,
        fps=FPS,
        target_total_frames=target_total_frames,
    )

def validate_stock_repetition(
    context: dict | None,
    stock_clips: list[dict],
    stock_specs: list[dict],
    ai_specs: list[dict],
    audio_duration: float
) -> dict:
    gates = (
        context.get("quality_gates", {})
        if context
        else {}
    )

    configured_minimum_clips = int(
        gates.get("minimum_stock_clip_count", 10)
    )
    configured_maximum_share = float(
        gates.get(
            "maximum_single_stock_clip_share",
            0.25
        )
    )
    require_ai_visuals = bool(
        gates.get("require_ai_visuals", False)
    )
    minimum_ai_insert_count = int(
        gates.get("minimum_ai_insert_count", 0)
    )

    hybrid_mode = (
        require_ai_visuals
        and minimum_ai_insert_count > 0
    )

    if hybrid_mode:
        minimum_clips = int(
            gates.get(
                "minimum_hybrid_stock_clip_count",
                max(
                    16,
                    configured_minimum_clips
                    - minimum_ai_insert_count
                )
            )
        )
        maximum_share = float(
            gates.get(
                "maximum_stock_source_clip_share",
                max(
                    configured_maximum_share,
                    0.15
                )
            )
        )
        minimum_combined_visuals = int(
            gates.get(
                "minimum_combined_visual_asset_count",
                configured_minimum_clips
            )
        )
    else:
        minimum_clips = configured_minimum_clips
        maximum_share = configured_maximum_share
        minimum_combined_visuals = configured_minimum_clips
    minimum_coverage = float(
        gates.get(
            "minimum_timeline_cycle_coverage",
            0.70
        )
    )
    maximum_cycles = int(
        gates.get("maximum_timeline_cycles", 2)
    )

    unique_clip_count = len({
        item["candidate_id"]
        for item in stock_clips
    })

    unique_ai_source_count = len({
        (
            item.get("source_relative_path")
            or str(item.get("source_path", ""))
            or item.get("segment_id")
        )
        for item in ai_specs
    })

    combined_visual_count = (
        unique_clip_count
        + unique_ai_source_count
    )

    total_stock_duration = sum(
        item["duration_seconds"]
        for item in stock_clips
    )

    largest_clip_share = (
        max(
            item["duration_seconds"]
            for item in stock_clips
        ) / total_stock_duration
        if total_stock_duration > 0
        else 1.0
    )

    cycle_duration = sum(
        item["duration_seconds"]
        for item in stock_specs
    ) + sum(
        item["duration_seconds"]
        for item in ai_specs
    )

    target_timeline_duration = (
        audio_duration + TIMELINE_TAIL_PADDING_SECONDS
    )
    coverage_ratio = (
        cycle_duration / target_timeline_duration
        if target_timeline_duration > 0
        else 0.0
    )

    timeline_cycles = (
        math.ceil(
            target_timeline_duration / cycle_duration
        )
        if cycle_duration > 0
        else 999
    )

    issues = []

    if unique_clip_count < minimum_clips:
        issues.append(
            "Stock clip count is below the diversity gate."
        )

    if largest_clip_share > maximum_share:
        issues.append(
            "One stock clip dominates the package."
        )

    if (
        hybrid_mode
        and combined_visual_count
        < minimum_combined_visuals
    ):
        issues.append(
            "Combined stock and AI visual count is below "
            "the diversity gate."
        )

    if coverage_ratio < minimum_coverage:
        issues.append(
            "Timeline cycle coverage is too low."
        )

    if timeline_cycles > maximum_cycles:
        issues.append(
            "Timeline would repeat too many cycles."
        )

    if issues:
        raise ValueError(
            "Stock repetition gate failed: "
            + " | ".join(issues)
        )

    return {
        "stock_unique_clip_count": unique_clip_count,
        "ai_unique_visual_count": unique_ai_source_count,
        "combined_unique_visual_count": combined_visual_count,
        "diversity_mode": (
            "hybrid_visual_diversity"
            if hybrid_mode
            else "stock_only_diversity"
        ),
        "effective_minimum_stock_clip_count": minimum_clips,
        "effective_maximum_stock_source_share": maximum_share,
        "stock_total_source_duration_seconds": round(
            total_stock_duration,
            2
        ),
        "stock_largest_clip_share": round(
            largest_clip_share,
            4
        ),
        "stock_cycle_coverage_ratio": round(
            coverage_ratio,
            4
        ),
        "timeline_target_duration_seconds": round(
            target_timeline_duration,
            2
        ),
        "stock_timeline_cycles": timeline_cycles,
        "stock_repetition_risk": "acceptable",
        "cross_video_reused_clip_count": 0,
        "asset_registry_verified_count": len(
            stock_clips
        )
    }


def load_ai_specs(
    ai_generation_data: dict,
    ai_qa_data: dict,
    channel: str,
    video_id: str | None
) -> list[dict]:
    if video_id:
        generation_video_id = (
            ai_generation_data.get(
                "source",
                {}
            ).get("video_id")
            or ai_generation_data.get("video_id")
        )

        qa_video_id = (
            ai_qa_data.get(
                "source",
                {}
            ).get("video_id")
            or ai_qa_data.get("video_id")
        )

        if generation_video_id != video_id:
            raise ValueError(
                "AI visual generation video_id mismatch."
            )

        if qa_video_id != video_id:
            raise ValueError(
                "AI visual QA video_id mismatch."
            )

        qa_checks = ai_qa_data.get(
            "checks",
            {}
        )

        if not qa_checks.get(
            "cross_video_asset_reuse"
        ):
            raise ValueError(
                "AI visual cross-video reuse gate is missing."
            )

        if not qa_checks.get(
            "asset_registry_ownership"
        ):
            raise ValueError(
                "AI visual registry ownership gate is missing."
            )

        if (
            ai_qa_data.get(
                "summary",
                {}
            ).get("reused_visual_asset_count")
            != 0
        ):
            raise ValueError(
                "Cross-video AI visual reuse was detected."
            )

    approved_ids = {
        item["insert_id"]
        for item in ai_qa_data.get(
            "image_checks",
            []
        )
        if item.get("approved") is True
    }

    specs = []
    used_hashes = set()

    for item in ai_generation_data.get(
        "generated_images",
        []
    ):
        insert_id = item["insert_id"]

        if insert_id not in approved_ids:
            continue

        path = PROJECT_ROOT / item["relative_path"]

        if not path.exists():
            raise FileNotFoundError(
                f"AI visual image not found: {path}"
            )

        if video_id:
            expected_sha256 = item.get("sha256")

            if not expected_sha256:
                raise ValueError(
                    "AI visual has no SHA-256 fingerprint."
                )

            if expected_sha256 in used_hashes:
                raise ValueError(
                    "Duplicate AI visual hash detected "
                    "inside the current video."
                )

            assert_asset_registered(
                path=path,
                channel=channel,
                video_id=video_id,
                expected_sha256=expected_sha256
            )

            used_hashes.add(expected_sha256)

        specs.append({
            "type": "ai_insert",
            "segment_id": insert_id,
            "insert_id": insert_id,
            "section_hint": item["section_hint"],
            "visual_role": item["visual_role"],
            "source_path": path,
            "source_relative_path": get_relative_path(
                path
            ),
            "sha256": item.get("sha256"),
            "duration_seconds": int(
                item.get(
                    "target_duration_seconds",
                    5
                )
            )
        })

    if not specs:
        raise ValueError(
            "No approved AI visual inserts found."
        )

    return sorted(
        specs,
        key=lambda item: item["insert_id"]
    )



def load_ai_video_specs(
    generation_data: dict,
    qa_data: dict,
    context: dict
) -> list[dict]:
    for key in ("channel", "video_id", "run_id"):
        if generation_data.get(key) != context.get(key):
            raise ValueError(
                f"AI video generation {key} mismatch."
            )

        if qa_data.get(key) != context.get(key):
            raise ValueError(
                f"AI video QA {key} mismatch."
            )

    if generation_data.get("status") != "videos_ready":
        raise ValueError("AI video generation is not videos_ready.")

    if generation_data.get("generation_mode") != "live":
        raise ValueError(
            "Only live AI video generation can enter assembly."
        )

    if qa_data.get("status") != "approved":
        raise ValueError("AI video QA is not approved.")

    if qa_data.get("generation_mode") != "live":
        raise ValueError("AI video QA is not for live outputs.")

    qa_checks = qa_data.get("checks", {})

    for required_check in (
        "technical_video_quality",
        "silent_video_required",
        "asset_registry_ownership",
        "cross_video_asset_reuse",
    ):
        if qa_checks.get(required_check) is not True:
            raise ValueError(
                "AI video QA gate is missing: "
                f"{required_check}."
            )

    approved_checks = {
        item["insert_id"]: item
        for item in qa_data.get("video_checks", [])
        if item.get("approved") is True
    }
    approved_ids = set(approved_checks)
    specs = []
    used_hashes = set()

    for item in generation_data.get("generated_videos", []):
        insert_id = item["insert_id"]

        if insert_id not in approved_ids:
            continue

        path = PROJECT_ROOT / item["relative_path"]

        if not path.exists():
            raise FileNotFoundError(
                f"AI video insert not found: {path}"
            )

        expected_sha256 = item.get("sha256")

        if not expected_sha256:
            raise ValueError(
                "AI video insert has no SHA-256 fingerprint."
            )

        if expected_sha256 in used_hashes:
            raise ValueError(
                "Duplicate AI video hash detected inside "
                "the current video."
            )

        assert_asset_registered(
            path=path,
            channel=context["channel"],
            video_id=context["video_id"],
            expected_sha256=expected_sha256
        )
        used_hashes.add(expected_sha256)

        specs.append({
            "type": "ai_video",
            "segment_id": insert_id,
            "insert_id": insert_id,
            "section_hint": item["section_hint"],
            "visual_role": item["visual_role"],
            "source_path": path,
            "source_relative_path": get_relative_path(path),
            "sha256": expected_sha256,
            "duration_seconds": float(
                approved_checks[insert_id].get(
                    "duration_seconds"
                )
                or item.get("target_duration_seconds", 6)
            )
        })

    validate_ai_video_insert_requirement(
        context=context,
        ai_video_specs=specs
    )

    return sorted(
        specs,
        key=lambda item: item["insert_id"]
    )


def build_hybrid_cycle(stock_specs: list[dict], ai_specs: list[dict]) -> list[dict]:
    if not ai_specs:
        return list(stock_specs)

    slots = {}

    for ai_index, ai_spec in enumerate(ai_specs, start=1):
        stock_position = round(
            ai_index * len(stock_specs) / (len(ai_specs) + 1)
        )
        stock_position = max(1, min(stock_position, len(stock_specs)))
        slots.setdefault(stock_position, []).append(ai_spec)

    cycle = []

    for index, stock_spec in enumerate(stock_specs, start=1):
        cycle.append(stock_spec)
        cycle.extend(slots.get(index, []))

    return cycle


def build_timeline_sequence(cycle: list[dict], audio_duration: float) -> list[dict]:
    cycle_duration = sum(item["duration_seconds"] for item in cycle)

    if cycle_duration <= 0:
        raise ValueError("Hybrid cycle duration is zero.")

    entries = []
    timeline_duration = 0.0
    cycle_number = 1
    sequence = 1

    while timeline_duration < audio_duration + 3:
        for item in cycle:
            entry = dict(item)
            entry["sequence"] = sequence
            entry["cycle"] = cycle_number
            entries.append(entry)

            timeline_duration += item["duration_seconds"]
            sequence += 1

            if timeline_duration >= audio_duration + 3:
                break

        cycle_number += 1

    return entries


def effective_timeline_entries(
    timeline_entries: list[dict],
    target_duration: float,
) -> list[dict]:
    remaining = max(0.0, float(target_duration))
    elapsed = 0.0
    effective = []

    for item in timeline_entries:
        if remaining <= 0.01:
            break

        duration = min(
            float(item["duration_seconds"]),
            remaining,
        )

        if duration <= 0.01:
            continue

        entry = dict(item)
        entry["timeline_start_seconds"] = round(
            elapsed,
            2,
        )
        entry["effective_duration_seconds"] = round(
            duration,
            2,
        )
        effective.append(entry)
        elapsed += duration
        remaining -= duration

    return effective


def nearest_rank_percentile(
    values: list[float],
    percentile: float,
) -> float:
    if not values:
        return 0.0

    ordered = sorted(float(value) for value in values)
    rank = max(
        1,
        math.ceil(float(percentile) * len(ordered)),
    )
    return ordered[min(rank - 1, len(ordered) - 1)]


def validate_visual_pacing(
    context: dict | None,
    timeline_entries: list[dict],
    audio_duration: float,
) -> dict:
    gates = (
        context.get("quality_gates", {})
        if context
        else {}
    )
    required = bool(
        gates.get("require_visual_pacing_qa", False)
    )
    target_duration = (
        float(audio_duration)
        + TIMELINE_TAIL_PADDING_SECONDS
    )
    effective = effective_timeline_entries(
        timeline_entries=timeline_entries,
        target_duration=target_duration,
    )
    durations = [
        float(item["effective_duration_seconds"])
        for item in effective
    ]
    covered_duration = sum(durations)
    average_hold = (
        covered_duration / len(durations)
        if durations
        else 0.0
    )
    p95_hold = nearest_rank_percentile(
        durations,
        0.95,
    )
    maximum_average = float(
        gates.get(
            "maximum_average_visual_hold_seconds",
            999.0,
        )
    )
    maximum_p95 = float(
        gates.get(
            "maximum_p95_visual_hold_seconds",
            999.0,
        )
    )
    maximum_ai_hold = float(
        gates.get(
            "maximum_ai_image_segment_seconds",
            MAX_AI_IMAGE_SEGMENT_SECONDS,
        )
    )
    maximum_ai_uses = int(
        gates.get("maximum_ai_image_uses", 2)
    )
    minimum_reuse_gap = float(
        gates.get("minimum_ai_reuse_gap_seconds", 0.0)
    )

    ai_occurrences: dict[str, list[float]] = {}
    ai_holds = []

    for item in effective:
        if item.get("type") != "ai_insert":
            continue

        source = str(
            item.get("source_relative_path")
            or item.get("source_path")
            or item.get("insert_id")
            or item.get("segment_id")
        )
        ai_occurrences.setdefault(
            source,
            [],
        ).append(
            float(item["timeline_start_seconds"])
        )
        ai_holds.append(
            float(item["effective_duration_seconds"])
        )

    maximum_actual_ai_uses = max(
        (
            len(starts)
            for starts in ai_occurrences.values()
        ),
        default=0,
    )
    reuse_gaps = []

    for starts in ai_occurrences.values():
        starts.sort()
        reuse_gaps.extend(
            following - current
            for current, following in zip(
                starts,
                starts[1:],
            )
        )

    actual_minimum_reuse_gap = (
        min(reuse_gaps)
        if reuse_gaps
        else None
    )

    checks = {
        "timeline_coverage": (
            covered_duration + 0.01
            >= target_duration
        ),
        "maximum_average_visual_hold": (
            average_hold <= maximum_average + 0.01
        ),
        "maximum_p95_visual_hold": (
            p95_hold <= maximum_p95 + 0.01
        ),
        "maximum_ai_image_hold": (
            max(ai_holds, default=0.0)
            <= maximum_ai_hold + 0.01
        ),
        "maximum_ai_image_uses": (
            maximum_actual_ai_uses
            <= maximum_ai_uses
        ),
        "minimum_ai_reuse_gap": (
            actual_minimum_reuse_gap is None
            or actual_minimum_reuse_gap + 0.01
            >= minimum_reuse_gap
        ),
    }
    issues = [
        name
        for name, passed in checks.items()
        if not passed
    ]
    status = (
        "approved"
        if all(checks.values())
        else "rejected"
    )

    report = {
        "required": required,
        "status": status if required else "not_required",
        "checks": checks,
        "issues": issues,
        "metrics": {
            "timeline_visual_entry_count": len(effective),
            "average_visual_hold_seconds": round(
                average_hold,
                2,
            ),
            "p95_visual_hold_seconds": round(
                p95_hold,
                2,
            ),
            "maximum_ai_image_hold_seconds": round(
                max(ai_holds, default=0.0),
                2,
            ),
            "maximum_actual_ai_image_uses": (
                maximum_actual_ai_uses
            ),
            "minimum_actual_ai_reuse_gap_seconds": (
                round(actual_minimum_reuse_gap, 2)
                if actual_minimum_reuse_gap is not None
                else None
            ),
        },
        "thresholds": {
            "maximum_average_visual_hold_seconds": (
                maximum_average
            ),
            "maximum_p95_visual_hold_seconds": maximum_p95,
            "maximum_ai_image_segment_seconds": (
                maximum_ai_hold
            ),
            "maximum_ai_image_uses": maximum_ai_uses,
            "minimum_ai_reuse_gap_seconds": (
                minimum_reuse_gap
            ),
        },
    }

    if required and issues:
        raise ValueError(
            "Visual pacing QA rejected the timeline: "
            + " | ".join(issues)
        )

    return report


def render_stock_segment(spec: dict, segment_path: Path) -> None:
    ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()

    command = [
        ffmpeg_path,
        "-y",
        "-ss",
        f"{spec['start_seconds']:.2f}",
        "-i",
        str(spec["source_path"]),
        "-t",
        f"{spec['duration_seconds']:.2f}",
        "-vf",
        stock_video_filter(),
        "-an",
        "-r",
        str(FPS),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-pix_fmt",
        "yuv420p",
        str(segment_path)
    ]

    run_ffmpeg(command, "ffmpeg stock segment render")


def render_ai_segment(spec: dict, segment_path: Path) -> None:
    ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
    frames = max(1, int(spec["duration_seconds"] * FPS))

    command = [
        ffmpeg_path,
        "-y",
        "-loop",
        "1",
        "-i",
        str(spec["source_path"]),
        "-vf",
        ai_image_filter(
            spec["duration_seconds"],
            motion_variant=int(
                spec.get("motion_variant", 1)
            ),
        ),
        "-frames:v",
        str(frames),
        "-an",
        "-r",
        str(FPS),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-pix_fmt",
        "yuv420p",
        str(segment_path)
    ]

    run_ffmpeg(command, "ffmpeg AI image segment render")


def render_ai_video_segment(
    spec: dict,
    segment_path: Path
) -> None:
    ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
    command = [
        ffmpeg_path,
        "-y",
        "-i",
        str(spec["source_path"]),
        "-t",
        f"{spec['duration_seconds']:.2f}",
        "-map",
        "0:v:0",
        "-vf",
        stock_video_filter(),
        "-an",
        "-r",
        str(FPS),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-pix_fmt",
        "yuv420p",
        str(segment_path)
    ]
    run_ffmpeg(command, "ffmpeg AI video segment render")


def render_unique_segments(unique_specs: list[dict], segment_library_dir: Path) -> dict[str, Path]:
    segment_library_dir.mkdir(parents=True, exist_ok=True)
    rendered = {}

    for spec in unique_specs:
        safe_id = spec["segment_id"].lower().replace(" ", "_").replace("/", "_")
        segment_path = segment_library_dir / f"{safe_id}.mp4"

        print(f"Rendering segment: {spec['segment_id']} ({spec['type']})", flush=True)

        if spec["type"] == "stock":
            render_stock_segment(spec, segment_path)
        elif spec["type"] == "ai_insert":
            render_ai_segment(spec, segment_path)
        elif spec["type"] == "ai_video":
            render_ai_video_segment(spec, segment_path)
        else:
            raise ValueError(f"Unknown segment type: {spec['type']}")

        if not segment_path.exists() or segment_path.stat().st_size <= 0:
            raise ValueError(f"Segment was not created correctly: {segment_path}")

        rendered[spec["segment_id"]] = segment_path

    return rendered


def write_concat_list(timeline_entries: list[dict], rendered_segments: dict[str, Path], concat_list_path: Path) -> None:
    lines = []

    for entry in timeline_entries:
        segment_path = rendered_segments[entry["segment_id"]]
        safe_path = segment_path.resolve().as_posix().replace("'", "\\'")
        lines.append(f"file '{safe_path}'")

    concat_list_path.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8"
    )


def concat_silent_video(concat_list_path: Path, silent_video_path: Path) -> None:
    ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()

    command = [
        ffmpeg_path,
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_list_path),
        "-c",
        "copy",
        str(silent_video_path)
    ]

    run_ffmpeg(command, "ffmpeg hybrid silent video concatenation")


def attach_audio(silent_video_path: Path, audio_path: Path, output_path: Path, audio_duration: float) -> None:
    ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()

    command = [
        ffmpeg_path,
        "-y",
        "-i",
        str(silent_video_path),
        "-i",
        str(audio_path),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-t",
        f"{audio_duration:.2f}",
        "-movflags",
        "+faststart",
        str(output_path)
    ]

    run_ffmpeg(command, "ffmpeg hybrid audio attachment")

    if not output_path.exists() or output_path.stat().st_size <= 0:
        raise ValueError(f"Hybrid video draft was not created: {output_path}")


def build_timeline_plan(
    stock_clips: list[dict],
    stock_specs: list[dict],
    ai_specs: list[dict],
    cycle: list[dict],
    timeline_entries: list[dict],
    audio_duration: float,
    output_dir: Path
) -> Path:
    timeline_plan_path = output_dir / "hybrid_timeline_plan.json"

    timeline_plan = {
        "mode": "hybrid_stock_ai_timeline",
        "audio_duration_seconds": round(audio_duration, 2),
        "stock_source_clip_count": len(stock_clips),
        "stock_segment_count": len(stock_specs),
        "ai_insert_count": len(ai_specs),
        "cycle_entry_count": len(cycle),
        "cycle_duration_seconds": round(sum(item["duration_seconds"] for item in cycle), 2),
        "timeline_entry_count": len(timeline_entries),
        "timeline_duration_before_trim_seconds": round(sum(item["duration_seconds"] for item in timeline_entries), 2),
        "stock_segments": [
            {
                "segment_id": item["segment_id"],
                "candidate_id": item["candidate_id"],
                "role": item["role"],
                "source_relative_path": item["source_relative_path"],
                "start_seconds": item["start_seconds"],
                "duration_seconds": item["duration_seconds"]
            }
            for item in stock_specs
        ],
        "ai_segments": [
            {
                "segment_id": item["segment_id"],
                "section_hint": item["section_hint"],
                "visual_role": item["visual_role"],
                "source_relative_path": item["source_relative_path"],
                "duration_seconds": item["duration_seconds"]
            }
            for item in ai_specs
        ],
        "timeline_entries": [
            {
                "sequence": item["sequence"],
                "cycle": item["cycle"],
                "type": item["type"],
                "segment_id": item["segment_id"],
                "duration_seconds": item["duration_seconds"],
                "source_relative_path": item["source_relative_path"]
            }
            for item in timeline_entries
        ]
    }

    timeline_plan_path.write_text(
        json.dumps(timeline_plan, indent=2),
        encoding="utf-8"
    )

    return timeline_plan_path


def assemble_hybrid_video(
    audio_path: Path,
    stock_clips: list[dict],
    stock_specs: list[dict],
    ai_specs: list[dict],
    output_dir: Path
) -> tuple[Path, dict]:
    audio_duration = get_media_duration_seconds(audio_path)

    cycle = build_hybrid_cycle(
        stock_specs=stock_specs,
        ai_specs=ai_specs
    )

    timeline_entries = build_timeline_sequence(
        cycle=cycle,
        audio_duration=audio_duration
    )

    unique_specs_by_id = {}

    for item in cycle:
        unique_specs_by_id[item["segment_id"]] = item

    unique_specs = list(unique_specs_by_id.values())

    segment_library_dir = output_dir / "segment_library"
    concat_list_path = output_dir / "hybrid_concat_list.txt"
    silent_video_path = output_dir / "hybrid_silent_video.mp4"
    output_path = output_dir / OUTPUT_FILENAME

    timeline_plan_path = build_timeline_plan(
        stock_clips=stock_clips,
        stock_specs=stock_specs,
        ai_specs=ai_specs,
        cycle=cycle,
        timeline_entries=timeline_entries,
        audio_duration=audio_duration,
        output_dir=output_dir
    )

    rendered_segments = render_unique_segments(
        unique_specs=unique_specs,
        segment_library_dir=segment_library_dir
    )

    write_concat_list(
        timeline_entries=timeline_entries,
        rendered_segments=rendered_segments,
        concat_list_path=concat_list_path
    )

    concat_silent_video(
        concat_list_path=concat_list_path,
        silent_video_path=silent_video_path
    )

    attach_audio(
        silent_video_path=silent_video_path,
        audio_path=audio_path,
        output_path=output_path,
        audio_duration=audio_duration
    )

    summary = {
        "audio_duration_seconds": round(audio_duration, 2),
        "stock_source_clip_count": len(stock_clips),
        "stock_segment_count": len(stock_specs),
        "ai_insert_count": len(ai_specs),
        "cycle_entry_count": len(cycle),
        "cycle_duration_seconds": round(sum(item["duration_seconds"] for item in cycle), 2),
        "timeline_entry_count": len(timeline_entries),
        "timeline_plan_path": get_relative_path(timeline_plan_path),
        "concat_list_path": get_relative_path(concat_list_path),
        "silent_video_path": get_relative_path(silent_video_path)
    }

    return output_path, summary


def build_output(
    channel: str,
    mode: str,
    audio_path: Path,
    audio_assembly_path: Path,
    publisher_path: Path,
    stock_manifest_path: Path,
    ai_generation_path: Path,
    ai_qa_path: Path,
    publisher_data: dict,
    video_path: Path | None,
    summary: dict
) -> dict:
    return {
        "agent": "hybrid_video_assembly",
        "version": "1.0",
        "channel": channel,
        "status": "dry_run_ready" if mode == "dry_run" else "draft_ready",
        "summary": summary,
        "video": {
            "filename": video_path.name if video_path else None,
            "relative_path": get_relative_path(video_path) if video_path else None,
            "format": "mp4" if video_path else None,
            "size_bytes": video_path.stat().st_size if video_path else 0,
            "resolution": f"{VIDEO_WIDTH}x{VIDEO_HEIGHT}",
            "fps": FPS,
            "mode": "hybrid_stock_ai_timeline",
            "audio_track_path": get_relative_path(audio_path),
            "timeline_plan_path": summary.get("timeline_plan_path"),
            "upload_ready": False
        },
        "readiness": {
            "video_ready": mode != "dry_run",
            "audio_ready": True,
            "stock_ready": True,
            "ai_visuals_ready": True,
            "upload_ready": False,
            "blocking_notes": [
                "Video QA has not been completed yet.",
                "Stock footage license and visual QA must be confirmed before public usage."
            ]
        },
        "source": {
            "audio_assembly_reference": get_relative_path(audio_assembly_path),
            "publisher_reference": get_relative_path(publisher_path),
            "stock_manifest_reference": get_relative_path(stock_manifest_path),
            "ai_visual_generation_reference": get_relative_path(ai_generation_path),
            "ai_visual_qa_reference": get_relative_path(ai_qa_path),
            "title": publisher_data["publishing_package"]["video_metadata"]["title"]
        },
        "metadata": {
            "next_agent": "video_qa"
        }
    }


def dry_run(final_output: dict, stock_specs: list[dict], ai_specs: list[dict]) -> None:
    print("Hybrid Video Assembly Agent dry-run completed.")
    print(f"Channel: {final_output['channel']}")
    print(f"Status: {final_output['status']}")
    print(f"Audio duration: {final_output['summary']['audio_duration_seconds']}s")
    print(f"Stock source clips: {final_output['summary']['stock_source_clip_count']}")
    print(f"Stock segments: {final_output['summary']['stock_segment_count']}")
    print(f"AI inserts: {final_output['summary']['ai_insert_count']}")
    print(f"Cycle duration: {final_output['summary']['cycle_duration_seconds']}s")
    print(f"Estimated timeline entries: {final_output['summary']['timeline_entry_count']}")
    print("First stock segments:")

    for item in stock_specs[:10]:
        print(
            f"- {item['segment_id']} | {item['role']} | "
            f"{item['duration_seconds']}s"
        )

    print("AI inserts:")

    for item in ai_specs:
        print(
            f"- {item['insert_id']} | {item['section_hint']} | "
            f"{item['duration_seconds']}s"
        )



def save_video_specific_output(
    channel: str,
    video_id: str,
    data: dict
) -> Path:
    context = load_context(
        channel=channel,
        video_id=video_id
    )

    output_dir = (
        BASE_DIR
        / "output"
        / channel
        / video_id
        / context["run_id"]
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / "hybrid_video_assembly.json"
    output_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=True),
        encoding="utf-8"
    )

    context = register_output(
        context=context,
        agent="hybrid_video_assembly",
        reference=get_relative_path(output_path),
        status="draft_ready"
    )

    video_reference = data.get(
        "video",
        {}
    ).get("relative_path")

    if video_reference:
        context = register_output(
            context=context,
            agent="final_video",
            reference=video_reference,
            status="draft_ready"
        )

    if context.get("status") not in {
        "uploaded_for_founder_review",
        "published",
        "public"
    }:
        context = set_status(
            context=context,
            status="video_draft_ready",
            next_agent="video_qa"
        )

    save_context(context)
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Assemble a hybrid video from stock footage, AI visual inserts, and narration audio."
    )

    parser.add_argument(
        "--channel",
        default=DEFAULT_CHANNEL,
        help="Channel name. Default: hiddenova"
    )

    parser.add_argument(
        "--video-id",
        default=None,
        help="Optional video context id, for example video_002"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate timeline without rendering video."
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    channel = args.channel.lower()
    video_id = args.video_id

    load_dotenv(PROJECT_ROOT / ".env")

    context = (
        load_context(
            channel=channel,
            video_id=video_id
        )
        if video_id
        else None
    )

    if video_id:
        print(f"VIDEO_CONTEXT_ID: {video_id}")

    audio_assembly_path = get_audio_assembly_latest_path(
        channel,
        video_id=video_id
    )

    if context:
        publisher_path = (
            PROJECT_ROOT
            / "records"
            / "run_contexts"
            / channel
            / f"{video_id}.json"
        )
        publisher_data = {
            "publishing_package": {
                "video_metadata": {
                    "title": context["topic_title"]
                }
            }
        }
    else:
        publisher_path = get_publisher_latest_path(channel)
        publisher_data = load_json(publisher_path)
    stock_manifest_path = get_stock_manifest_path(channel, video_id=video_id)
    ai_generation_path = get_ai_generation_latest_path(
        channel,
        video_id=video_id
    )
    ai_qa_path = get_ai_qa_latest_path(
        channel,
        video_id=video_id
    )

    audio_data = load_json(audio_assembly_path)
    stock_manifest_data = load_json(stock_manifest_path)

    if video_id:
        stock_qa_path = get_stock_qa_path(
            channel=channel,
            video_id=video_id
        )
        stock_qa_data = load_json(stock_qa_path)

        if stock_qa_data.get("status") != "approved":
            raise ValueError("Stock QA is not approved.")

        if (
            stock_qa_data.get("summary", {}).get(
                "reused_clip_count"
            )
            != 0
        ):
            raise ValueError(
                "Cross-video stock reuse was detected."
            )

        if not stock_qa_data.get(
            "checks",
            {}
        ).get("cross_video_asset_reuse"):
            raise ValueError(
                "Cross-video stock registry gate is missing."
            )

    ai_generation_data = load_json(ai_generation_path)
    ai_qa_data = load_json(ai_qa_path)

    ai_video_enabled = ai_video_context_enabled(context)
    ai_video_generation_data = None
    ai_video_qa_data = None

    if ai_video_enabled:
        if not video_id or not context:
            raise ValueError(
                "AI video inserts require a video-specific context."
            )

        ai_video_generation_data = load_json(
            get_ai_video_generation_path(channel, video_id)
        )
        ai_video_qa_data = load_json(
            get_ai_video_qa_path(channel, video_id)
        )

    ai_inserts_enabled = video_id is not None or (
        ai_generation_path.exists() and ai_qa_path.exists()
    )

    ensure_inputs_ready(
        audio_data=audio_data,
        ai_generation_data=ai_generation_data,
        ai_qa_data=ai_qa_data,
        ai_inserts_enabled=ai_inserts_enabled,
        video_id=video_id
    )

    audio_path = get_audio_path(audio_data)

    if context:
        validate_audio_asset_ownership(
            audio_data=audio_data,
            audio_path=audio_path,
            context=context
        )

    print(f"SELECTED_AUDIO_ASSEMBLY_PATH: {get_relative_path(audio_assembly_path)}")
    print(f"SELECTED_AUDIO_FILE_PATH: {get_relative_path(audio_path)}")
    print(f"SELECTED_STOCK_MANIFEST_PATH: {get_relative_path(stock_manifest_path)}")
    print(f"AI_INSERTS_ENABLED: {ai_inserts_enabled}")

    stock_clips = load_stock_clips(
        stock_manifest_data=stock_manifest_data,
        channel=channel,
        video_id=video_id,
        run_id=context["run_id"] if context else None
    )

    maximum_segments = int(
        context.get(
            "quality_gates",
            {}
        ).get(
            "maximum_stock_segments_per_clip",
            5
        )
    ) if context else 5

    if ai_inserts_enabled:
        unique_ai_image_specs = load_ai_specs(
            ai_generation_data=ai_generation_data,
            ai_qa_data=ai_qa_data,
            channel=channel,
            video_id=video_id
        )
    else:
        unique_ai_image_specs = []
        print("AI_INSERTS_DISABLED_FOR_VIDEO_CONTEXT: true")

    if ai_video_enabled:
        ai_video_specs = load_ai_video_specs(
            generation_data=ai_video_generation_data,
            qa_data=ai_video_qa_data,
            context=context
        )
    else:
        ai_video_specs = []

    audio_duration = get_media_duration_seconds(audio_path)
    quality_gates = (
        context.get("quality_gates", {})
        if context
        else {}
    )
    maximum_ai_image_uses = int(
        quality_gates.get("maximum_ai_image_uses", 2)
    )
    maximum_ai_image_segment_seconds = float(
        quality_gates.get(
            "maximum_ai_image_segment_seconds",
            MAX_AI_IMAGE_SEGMENT_SECONDS,
        )
    )

    capacity_report = build_hybrid_capacity_report(
        stock_clips=stock_clips,
        ai_image_specs=unique_ai_image_specs,
        ai_video_specs=ai_video_specs,
        audio_duration_seconds=audio_duration,
        quality_gates=quality_gates,
        fps=FPS,
    )
    maximum_capacity_seconds = round(
        capacity_report["stock"]["maximum_seconds"]
        + capacity_report["ai_images"]["maximum_seconds"]
        + capacity_report["ai_video"]["seconds"],
        6,
    )

    print(
        "HYBRID_CAPACITY_CONTRACT: "
        f"{capacity_report['contract_version']}"
    )
    print(
        "HYBRID_CAPACITY_STATUS: "
        f"{capacity_report['status']}"
    )
    print(
        "HYBRID_CAPACITY_TARGET_SECONDS: "
        f"{capacity_report['target']['seconds']}"
    )
    print(
        "HYBRID_CAPACITY_MAXIMUM_SECONDS: "
        f"{maximum_capacity_seconds}"
    )

    if not capacity_report["approved"]:
        raise HybridCapacityError(
            "Hybrid visual capacity is insufficient.",
            capacity_report,
        )

    capacity_plan = materialize_hybrid_capacity_plan(
        stock_clips=stock_clips,
        ai_image_specs=unique_ai_image_specs,
        capacity_report=capacity_report,
        quality_gates=quality_gates,
        fps=FPS,
    )
    base_stock_specs = capacity_plan["base_stock_specs"]
    ai_image_specs = capacity_plan["ai_image_specs"]
    stock_specs = capacity_plan["stock_specs"]

    print(
        "HYBRID_CAPACITY_ALLOCATION: exact_selected_frames"
    )
    print(
        "HYBRID_CAPACITY_STOCK_SELECTED_FRAMES: "
        f"{capacity_plan['allocation']['stock_frames']}"
    )
    print(
        "HYBRID_CAPACITY_AI_SELECTED_FRAMES: "
        f"{capacity_plan['allocation']['ai_image_frames']}"
    )

    ai_specs = interleave_ai_specs(
        image_specs=ai_image_specs,
        video_specs=ai_video_specs
    )

    duration_gate = validate_production_duration(
        context=context,
        actual_seconds=audio_duration
    )
    ai_insert_gate = validate_ai_insert_requirement(
        context=context,
        ai_specs=unique_ai_image_specs
    )
    ai_video_insert_gate = validate_ai_video_insert_requirement(
        context=context,
        ai_video_specs=ai_video_specs
    )
    cycle = build_hybrid_cycle(
        stock_specs=stock_specs,
        ai_specs=ai_specs
    )

    stock_report = validate_stock_repetition(
        context=context,
        stock_clips=stock_clips,
        stock_specs=stock_specs,
        ai_specs=ai_specs,
        audio_duration=audio_duration
    )

    print(
        "STOCK_UNIQUE_CLIPS: "
        f"{stock_report['stock_unique_clip_count']}"
    )
    print(
        "STOCK_CYCLE_COVERAGE: "
        f"{stock_report['stock_cycle_coverage_ratio']}"
    )
    print(
        "STOCK_TIMELINE_CYCLES: "
        f"{stock_report['stock_timeline_cycles']}"
    )
    print(
        "STOCK_REPETITION_RISK: "
        f"{stock_report['stock_repetition_risk']}"
    )
    print(
        "AUDIO_DURATION_GATE: "
        f"{duration_gate['status']}"
    )
    print(
        "AI_INSERT_GATE: "
        f"{'pass' if ai_insert_gate['approved'] else 'fail'}"
    )
    print(
        "AI_IMAGE_INSERT_COUNT: "
        f"{len(unique_ai_image_specs)}"
    )
    print(
        "AI_IMAGE_TIMELINE_SEGMENT_COUNT: "
        f"{len(ai_image_specs)}"
    )
    print(f"AI_VIDEO_INSERT_COUNT: {len(ai_video_specs)}")
    print(
        "AI_VIDEO_INSERT_GATE: "
        f"{'pass' if ai_video_insert_gate['approved'] else 'fail'}"
    )

    timeline_entries = build_timeline_sequence(
        cycle=cycle,
        audio_duration=audio_duration
    )
    pacing_report = validate_visual_pacing(
        context=context,
        timeline_entries=timeline_entries,
        audio_duration=audio_duration,
    )

    print(
        "VISUAL_PACING_QA_STATUS: "
        f"{pacing_report['status']}"
    )
    print(
        "AVERAGE_VISUAL_HOLD_SECONDS: "
        f"{pacing_report['metrics']['average_visual_hold_seconds']}"
    )
    print(
        "P95_VISUAL_HOLD_SECONDS: "
        f"{pacing_report['metrics']['p95_visual_hold_seconds']}"
    )
    print(
        "MINIMUM_AI_REUSE_GAP_SECONDS: "
        f"{pacing_report['metrics']['minimum_actual_ai_reuse_gap_seconds']}"
    )

    dry_run_summary = {
        "audio_duration_seconds": round(audio_duration, 2),
        "stock_source_clip_count": len(stock_clips),
        "stock_segment_count": len(stock_specs),
        "ai_insert_count": len(ai_specs),
        "cycle_entry_count": len(cycle),
        "cycle_duration_seconds": round(sum(item["duration_seconds"] for item in cycle), 2),
        "timeline_entry_count": len(timeline_entries),
        "timeline_plan_path": None,
        "concat_list_path": None,
        "silent_video_path": None,
        "visual_pacing_qa_status": pacing_report["status"],
        **pacing_report["metrics"],
        **stock_report
    }

    if args.dry_run:
        final_output = build_output(
            channel=channel,
            mode="dry_run",
            audio_path=audio_path,
            audio_assembly_path=audio_assembly_path,
            publisher_path=publisher_path,
            stock_manifest_path=stock_manifest_path,
            ai_generation_path=ai_generation_path,
            ai_qa_path=ai_qa_path,
            publisher_data=publisher_data,
            video_path=None,
            summary=dry_run_summary
        )

        schema = load_schema()
        validate(instance=final_output, schema=schema)

        dry_run(
            final_output=final_output,
            stock_specs=stock_specs,
            ai_specs=ai_specs
        )
        return

    output_dir = get_output_dir(
        channel=channel,
        video_id=video_id,
        run_id=context["run_id"] if context else None
    )

    video_path, render_summary = assemble_hybrid_video(
        audio_path=audio_path,
        stock_clips=stock_clips,
        stock_specs=stock_specs,
        ai_specs=ai_specs,
        output_dir=output_dir
    )

    render_summary.update(stock_report)
    render_summary.update({
        "visual_pacing_qa_status": pacing_report["status"],
        **pacing_report["metrics"],
    })

    final_video_record = None
    final_video_registry_path = None

    if context:
        final_video_record = build_asset_record(
            path=video_path,
            asset_type="final_video",
            channel=context["channel"],
            video_id=context["video_id"],
            run_id=context["run_id"],
            shared_brand_asset=False
        )

        final_video_registry_path = register_asset_batch(
            records=[final_video_record]
        )

        context.setdefault(
            "quality_gates",
            {}
        ).update({
            "allow_cross_video_asset_reuse": False,
            "require_audio_asset_registry_ownership": True,
            "require_final_video_asset_registry_ownership": True
        })

        save_context(context)

    final_output = build_output(
        channel=channel,
        mode="render",
        audio_path=audio_path,
        audio_assembly_path=audio_assembly_path,
        publisher_path=publisher_path,
        stock_manifest_path=stock_manifest_path,
        ai_generation_path=ai_generation_path,
        ai_qa_path=ai_qa_path,
        publisher_data=publisher_data,
        video_path=video_path,
        summary=render_summary
    )

    if context and final_video_record:
        final_output["video"]["sha256"] = (
            final_video_record["sha256"]
        )
        final_output["video"][
            "asset_registry_reference"
        ] = get_relative_path(
            final_video_registry_path
        )
        final_output["source"].update({
            "video_id": context["video_id"],
            "run_id": context["run_id"],
            "asset_registry_reference": get_relative_path(
                final_video_registry_path
            )
        })

    schema = load_schema()
    validate(instance=final_output, schema=schema)

    latest_path = save_output(
        channel=final_output["channel"],
        data=final_output
    )

    video_specific_path = None

    if video_id:
        video_specific_path = save_video_specific_output(
            channel=channel,
            video_id=video_id,
            data=final_output
        )

    print("Hybrid Video Assembly Agent completed successfully.")
    print(f"Video draft saved to: {video_path}")
    print(f"Output saved to: {latest_path}")

    if video_specific_path:
        print(
            "VIDEO_CONTEXT_OUTPUT: "
            f"{get_relative_path(video_specific_path)}"
        )


if __name__ == "__main__":
    main()
