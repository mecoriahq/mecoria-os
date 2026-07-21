from __future__ import annotations

import math
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP
from statistics import median
from typing import Any


CAPACITY_CONTRACT_VERSION = "hybrid_capacity_frames_v1_1"
DEFAULT_FPS = 30
DEFAULT_STOCK_SEGMENT_SECONDS = 6.0
DEFAULT_MAX_STOCK_SEGMENT_SECONDS = 8.0
DEFAULT_MAX_AI_IMAGE_SEGMENT_SECONDS = 13.0
DEFAULT_MAX_AI_IMAGE_USES = 2
DEFAULT_TAIL_PADDING_SECONDS = 3.0


class HybridCapacityError(ValueError):
    def __init__(self, message: str, report: dict[str, Any]):
        super().__init__(message)
        self.report = report


def _decimal(value: float | int | str) -> Decimal:
    return Decimal(str(value))


def seconds_to_frames(
    seconds: float | int | str,
    fps: int = DEFAULT_FPS,
    rounding: str = "nearest",
) -> int:
    if fps <= 0:
        raise ValueError("fps must be positive.")

    value = _decimal(seconds) * Decimal(fps)

    modes = {
        "ceil": ROUND_CEILING,
        "floor": ROUND_FLOOR,
        "nearest": ROUND_HALF_UP,
    }

    if rounding not in modes:
        raise ValueError(
            "rounding must be ceil, floor, or nearest."
        )

    return max(
        0,
        int(value.to_integral_value(rounding=modes[rounding])),
    )


def frames_to_seconds(
    frames: int,
    fps: int = DEFAULT_FPS,
) -> float:
    if fps <= 0:
        raise ValueError("fps must be positive.")

    return round(int(frames) / fps, 6)


def resolve_capacity_settings(
    quality_gates: dict[str, Any] | None,
    fps: int = DEFAULT_FPS,
) -> dict[str, Any]:
    gates = quality_gates or {}

    return {
        "fps": int(gates.get("timeline_fps", fps)),
        "stock_segment_seconds": float(
            gates.get(
                "stock_segment_seconds",
                DEFAULT_STOCK_SEGMENT_SECONDS,
            )
        ),
        "maximum_stock_segment_seconds": float(
            gates.get(
                "maximum_stock_segment_seconds",
                DEFAULT_MAX_STOCK_SEGMENT_SECONDS,
            )
        ),
        "maximum_stock_segments_per_clip": int(
            gates.get("maximum_stock_segments_per_clip", 5)
        ),
        "maximum_ai_image_segment_seconds": float(
            gates.get(
                "maximum_ai_image_segment_seconds",
                DEFAULT_MAX_AI_IMAGE_SEGMENT_SECONDS,
            )
        ),
        "maximum_ai_image_uses": int(
            gates.get(
                "maximum_ai_image_uses",
                DEFAULT_MAX_AI_IMAGE_USES,
            )
        ),
        "timeline_tail_padding_seconds": float(
            gates.get(
                "timeline_tail_padding_seconds",
                DEFAULT_TAIL_PADDING_SECONDS,
            )
        ),
    }


def build_stock_segment_specs(
    stock_clips: list[dict[str, Any]],
    max_segments_per_clip: int = 5,
    target_total_duration: float | None = None,
    maximum_segment_seconds: float = (
        DEFAULT_MAX_STOCK_SEGMENT_SECONDS
    ),
    stock_segment_seconds: float = (
        DEFAULT_STOCK_SEGMENT_SECONDS
    ),
    fps: int = DEFAULT_FPS,
) -> list[dict[str, Any]]:
    base_frames = seconds_to_frames(
        stock_segment_seconds,
        fps=fps,
        rounding="nearest",
    )
    max_frames = seconds_to_frames(
        maximum_segment_seconds,
        fps=fps,
        rounding="floor",
    )
    minimum_frames = seconds_to_frames(
        2.0,
        fps=fps,
        rounding="ceil",
    )
    clip_buckets: list[list[dict[str, Any]]] = []

    for clip in stock_clips:
        clip_frames = seconds_to_frames(
            clip["duration_seconds"],
            fps=fps,
            rounding="floor",
        )
        possible_count = max(
            1,
            math.ceil(clip_frames / base_frames),
        )
        segment_count = min(
            possible_count,
            int(max_segments_per_clip),
        )

        if segment_count == 1:
            starts = [0]
        elif possible_count <= max_segments_per_clip:
            starts = [
                index * base_frames
                for index in range(segment_count)
            ]
        else:
            maximum_start = max(
                0,
                clip_frames - base_frames,
            )
            starts = [
                round(
                    index * maximum_start / (segment_count - 1)
                )
                for index in range(segment_count)
            ]

        bucket: list[dict[str, Any]] = []

        for index, start_frame in enumerate(starts, start=1):
            remaining_frames = clip_frames - start_frame
            duration_frames = min(
                base_frames,
                remaining_frames,
            )

            if duration_frames < minimum_frames:
                continue

            spec = {
                "type": "stock",
                "segment_id": (
                    f"{clip['candidate_id']}_S{index:02d}"
                ),
                "asset_id": clip.get("asset_id"),
                "candidate_id": clip["candidate_id"],
                "role": clip.get(
                    "role",
                    "topic_specific_stock_footage",
                ),
                "source_path": clip.get("path"),
                "source_relative_path": (
                    clip.get("source_relative_path")
                    or clip.get("relative_path")
                ),
                "start_frame": int(start_frame),
                "duration_frames": int(duration_frames),
                "start_seconds": frames_to_seconds(
                    start_frame,
                    fps,
                ),
                "duration_seconds": frames_to_seconds(
                    duration_frames,
                    fps,
                ),
                "risk_level": clip.get(
                    "risk_level",
                    "unknown",
                ),
            }
            bucket.append(spec)

        clip_buckets.append(bucket)

    specs: list[dict[str, Any]] = []
    maximum_bucket_size = max(
        (len(bucket) for bucket in clip_buckets),
        default=0,
    )

    for segment_index in range(maximum_bucket_size):
        for bucket in clip_buckets:
            if segment_index < len(bucket):
                specs.append(bucket[segment_index])

    _attach_stock_capacity(
        stock_clips=stock_clips,
        stock_specs=specs,
        maximum_segment_frames=max_frames,
        fps=fps,
    )

    if target_total_duration is not None:
        return expand_stock_specs_for_target(
            stock_clips=stock_clips,
            stock_specs=specs,
            target_total_duration=target_total_duration,
            maximum_segment_seconds=maximum_segment_seconds,
            fps=fps,
        )

    return specs


def _attach_stock_capacity(
    stock_clips: list[dict[str, Any]],
    stock_specs: list[dict[str, Any]],
    maximum_segment_frames: int,
    fps: int,
) -> None:
    clip_frames_by_id = {
        str(item["candidate_id"]): seconds_to_frames(
            item["duration_seconds"],
            fps=fps,
            rounding="floor",
        )
        for item in stock_clips
    }
    grouped: dict[str, list[dict[str, Any]]] = {}

    for spec in stock_specs:
        if "start_frame" not in spec:
            spec["start_frame"] = seconds_to_frames(
                spec.get("start_seconds", 0),
                fps=fps,
                rounding="nearest",
            )

        if "duration_frames" not in spec:
            spec["duration_frames"] = seconds_to_frames(
                spec.get("duration_seconds", 0),
                fps=fps,
                rounding="nearest",
            )

        grouped.setdefault(
            str(spec["candidate_id"]),
            [],
        ).append(spec)

    for candidate_id, specs in grouped.items():
        specs.sort(key=lambda item: int(item["start_frame"]))
        clip_frames = clip_frames_by_id[candidate_id]

        for index, spec in enumerate(specs):
            start_frame = int(spec["start_frame"])
            next_start_frame = (
                int(specs[index + 1]["start_frame"])
                if index + 1 < len(specs)
                else clip_frames
            )
            non_overlap_frames = max(
                0,
                next_start_frame - start_frame,
            )
            maximum_duration_frames = min(
                maximum_segment_frames,
                non_overlap_frames,
            )
            spec["maximum_duration_frames"] = int(
                maximum_duration_frames
            )
            spec["maximum_duration_seconds"] = (
                frames_to_seconds(
                    maximum_duration_frames,
                    fps,
                )
            )


def maximum_stock_spec_frames(
    stock_clips: list[dict[str, Any]],
    stock_specs: list[dict[str, Any]],
    maximum_segment_seconds: float = (
        DEFAULT_MAX_STOCK_SEGMENT_SECONDS
    ),
    fps: int = DEFAULT_FPS,
) -> int:
    max_frames = seconds_to_frames(
        maximum_segment_seconds,
        fps=fps,
        rounding="floor",
    )
    working = [dict(item) for item in stock_specs]
    _attach_stock_capacity(
        stock_clips=stock_clips,
        stock_specs=working,
        maximum_segment_frames=max_frames,
        fps=fps,
    )
    return sum(
        int(item["maximum_duration_frames"])
        for item in working
    )


def maximum_stock_spec_duration(
    stock_clips: list[dict[str, Any]],
    stock_specs: list[dict[str, Any]],
    maximum_segment_seconds: float = (
        DEFAULT_MAX_STOCK_SEGMENT_SECONDS
    ),
    fps: int = DEFAULT_FPS,
) -> float:
    return frames_to_seconds(
        maximum_stock_spec_frames(
            stock_clips=stock_clips,
            stock_specs=stock_specs,
            maximum_segment_seconds=maximum_segment_seconds,
            fps=fps,
        ),
        fps,
    )


def expand_stock_specs_for_target(
    stock_clips: list[dict[str, Any]],
    stock_specs: list[dict[str, Any]],
    target_total_duration: float | None = None,
    maximum_segment_seconds: float = (
        DEFAULT_MAX_STOCK_SEGMENT_SECONDS
    ),
    fps: int = DEFAULT_FPS,
    target_total_frames: int | None = None,
) -> list[dict[str, Any]]:
    expanded = [dict(item) for item in stock_specs]
    max_frames = seconds_to_frames(
        maximum_segment_seconds,
        fps=fps,
        rounding="floor",
    )
    _attach_stock_capacity(
        stock_clips=stock_clips,
        stock_specs=expanded,
        maximum_segment_frames=max_frames,
        fps=fps,
    )

    if target_total_frames is not None:
        target_frames = max(0, int(target_total_frames))
    elif target_total_duration is not None:
        target_frames = seconds_to_frames(
            target_total_duration,
            fps=fps,
            rounding="ceil",
        )
    else:
        raise ValueError(
            "target_total_duration or target_total_frames "
            "is required."
        )
    current_frames = sum(
        int(item["duration_frames"])
        for item in expanded
    )
    remaining_frames = max(
        0,
        target_frames - current_frames,
    )

    capacities = [
        {
            "spec": item,
            "remaining_frames": max(
                0,
                int(item["maximum_duration_frames"])
                - int(item["duration_frames"]),
            ),
        }
        for item in expanded
    ]

    while remaining_frames > 0:
        progressed = False

        for item in capacities:
            if remaining_frames <= 0:
                break

            available = int(item["remaining_frames"])

            if available <= 0:
                continue

            increment = min(
                max(1, fps // 2),
                available,
                remaining_frames,
            )
            spec = item["spec"]
            spec["duration_frames"] = (
                int(spec["duration_frames"]) + increment
            )
            spec["duration_seconds"] = frames_to_seconds(
                spec["duration_frames"],
                fps,
            )
            item["remaining_frames"] = available - increment
            remaining_frames -= increment
            progressed = True

        capacities = [
            item
            for item in capacities
            if int(item["remaining_frames"]) > 0
        ]

        if not progressed:
            break

    if remaining_frames > 0:
        report = {
            "status": "insufficient",
            "deficit_frames": remaining_frames,
            "deficit_seconds": frames_to_seconds(
                remaining_frames,
                fps,
            ),
        }
        raise HybridCapacityError(
            "Stock source duration cannot satisfy one-cycle "
            "timeline coverage without overlapping or reusing "
            "segments.",
            report,
        )

    return expanded


def expand_ai_image_specs_for_target(
    ai_specs: list[dict[str, Any]],
    target_total_duration: float | None = None,
    maximum_uses_per_image: int = DEFAULT_MAX_AI_IMAGE_USES,
    maximum_segment_seconds: float = (
        DEFAULT_MAX_AI_IMAGE_SEGMENT_SECONDS
    ),
    fps: int = DEFAULT_FPS,
    target_total_frames: int | None = None,
) -> list[dict[str, Any]]:
    if not ai_specs:
        raise ValueError(
            "AI image specs are required for hybrid coverage."
        )

    max_frames = seconds_to_frames(
        maximum_segment_seconds,
        fps=fps,
        rounding="floor",
    )
    expanded: list[dict[str, Any]] = []

    for item in ai_specs:
        spec = dict(item)
        duration_frames = seconds_to_frames(
            spec["duration_seconds"],
            fps=fps,
            rounding="ceil",
        )
        spec["duration_frames"] = duration_frames
        spec["duration_seconds"] = frames_to_seconds(
            duration_frames,
            fps,
        )
        spec["motion_variant"] = int(
            spec.get("motion_variant", 1)
        )
        expanded.append(spec)

    base_total_frames = sum(
        int(item["duration_frames"])
        for item in expanded
    )

    if target_total_frames is not None:
        requested_target_frames = max(
            0,
            int(target_total_frames),
        )
    elif target_total_duration is not None:
        requested_target_frames = seconds_to_frames(
            target_total_duration,
            fps=fps,
            rounding="ceil",
        )
    else:
        raise ValueError(
            "target_total_duration or target_total_frames "
            "is required."
        )

    target_frames = max(
        base_total_frames,
        requested_target_frames,
    )

    if (
        target_frames
        > sum(int(item["duration_frames"]) for item in expanded)
    ):
        originals = list(expanded)

        for use_index in range(
            2,
            int(maximum_uses_per_image) + 1,
        ):
            for original in originals:
                duplicate = dict(original)
                duplicate["segment_id"] = (
                    f"{original['segment_id']}_M{use_index:02d}"
                )
                duplicate["motion_variant"] = use_index
                expanded.append(duplicate)

    remaining_frames = max(
        0,
        target_frames
        - sum(
            int(item["duration_frames"])
            for item in expanded
        ),
    )

    while remaining_frames > 0:
        progressed = False

        for item in expanded:
            if remaining_frames <= 0:
                break

            current_frames = int(item["duration_frames"])
            capacity_frames = max(
                0,
                max_frames - current_frames,
            )

            if capacity_frames <= 0:
                continue

            increment = min(
                max(1, fps // 2),
                capacity_frames,
                remaining_frames,
            )
            item["duration_frames"] = current_frames + increment
            item["duration_seconds"] = frames_to_seconds(
                item["duration_frames"],
                fps,
            )
            remaining_frames -= increment
            progressed = True

        if not progressed:
            break

    if remaining_frames > 0:
        report = {
            "status": "insufficient",
            "deficit_frames": remaining_frames,
            "deficit_seconds": frames_to_seconds(
                remaining_frames,
                fps,
            ),
        }
        raise HybridCapacityError(
            "Combined stock and AI image capacity cannot "
            "satisfy one-cycle timeline coverage.",
            report,
        )

    return expanded


def _ai_base_and_max_frames(
    ai_image_specs: list[dict[str, Any]],
    maximum_uses_per_image: int,
    maximum_segment_seconds: float,
    fps: int,
) -> tuple[int, int]:
    maximum_frames = seconds_to_frames(
        maximum_segment_seconds,
        fps=fps,
        rounding="floor",
    )
    base = 0
    maximum = 0

    for item in ai_image_specs:
        item_frames = seconds_to_frames(
            item.get("duration_seconds", 5.0),
            fps=fps,
            rounding="ceil",
        )
        base += item_frames
        maximum += (
            max(item_frames, maximum_frames)
            * int(maximum_uses_per_image)
        )

    return base, maximum


def build_hybrid_capacity_report(
    stock_clips: list[dict[str, Any]],
    ai_image_specs: list[dict[str, Any]],
    audio_duration_seconds: float,
    quality_gates: dict[str, Any] | None = None,
    ai_video_specs: list[dict[str, Any]] | None = None,
    fps: int = DEFAULT_FPS,
) -> dict[str, Any]:
    settings = resolve_capacity_settings(
        quality_gates,
        fps=fps,
    )
    fps = int(settings["fps"])
    ai_video_specs = ai_video_specs or []

    base_stock_specs = build_stock_segment_specs(
        stock_clips=stock_clips,
        max_segments_per_clip=int(
            settings["maximum_stock_segments_per_clip"]
        ),
        maximum_segment_seconds=float(
            settings["maximum_stock_segment_seconds"]
        ),
        stock_segment_seconds=float(
            settings["stock_segment_seconds"]
        ),
        fps=fps,
    )
    stock_base_frames = sum(
        int(item["duration_frames"])
        for item in base_stock_specs
    )
    stock_max_frames = maximum_stock_spec_frames(
        stock_clips=stock_clips,
        stock_specs=base_stock_specs,
        maximum_segment_seconds=float(
            settings["maximum_stock_segment_seconds"]
        ),
        fps=fps,
    )
    ai_base_frames, ai_max_frames = _ai_base_and_max_frames(
        ai_image_specs=ai_image_specs,
        maximum_uses_per_image=int(
            settings["maximum_ai_image_uses"]
        ),
        maximum_segment_seconds=float(
            settings["maximum_ai_image_segment_seconds"]
        ),
        fps=fps,
    )
    ai_video_frames = sum(
        seconds_to_frames(
            item.get("duration_seconds", 0),
            fps=fps,
            rounding="ceil",
        )
        for item in ai_video_specs
    )
    target_frames = seconds_to_frames(
        (
            float(audio_duration_seconds)
            + float(settings["timeline_tail_padding_seconds"])
        ),
        fps=fps,
        rounding="ceil",
    )

    selected_ai_frames = max(
        ai_base_frames,
        target_frames - stock_max_frames - ai_video_frames,
    )
    ai_deficit_frames = max(
        0,
        selected_ai_frames - ai_max_frames,
    )
    selected_ai_frames = min(
        selected_ai_frames,
        ai_max_frames,
    )
    selected_stock_frames = max(
        0,
        target_frames
        - ai_video_frames
        - selected_ai_frames,
    )
    stock_deficit_frames = max(
        0,
        selected_stock_frames - stock_max_frames,
    )
    total_deficit_frames = max(
        ai_deficit_frames,
        stock_deficit_frames,
        target_frames
        - stock_max_frames
        - ai_max_frames
        - ai_video_frames,
        0,
    )

    per_clip_max_frames: list[int] = []
    grouped: dict[str, int] = {}

    for item in base_stock_specs:
        grouped[str(item["candidate_id"])] = (
            grouped.get(str(item["candidate_id"]), 0)
            + int(item["maximum_duration_frames"])
        )

    per_clip_max_frames.extend(grouped.values())
    estimated_clip_frames = int(
        median(per_clip_max_frames)
    ) if per_clip_max_frames else seconds_to_frames(
        settings["maximum_stock_segment_seconds"],
        fps=fps,
        rounding="floor",
    )
    estimated_additional_clips = (
        math.ceil(total_deficit_frames / estimated_clip_frames)
        if total_deficit_frames > 0 and estimated_clip_frames > 0
        else 0
    )
    approved = total_deficit_frames == 0

    return {
        "contract_version": CAPACITY_CONTRACT_VERSION,
        "status": "approved" if approved else "insufficient",
        "approved": approved,
        "fps": fps,
        "settings": settings,
        "target": {
            "frames": target_frames,
            "seconds": frames_to_seconds(target_frames, fps),
            "audio_duration_seconds": float(
                audio_duration_seconds
            ),
            "tail_padding_seconds": float(
                settings["timeline_tail_padding_seconds"]
            ),
        },
        "stock": {
            "source_clip_count": len(stock_clips),
            "base_frames": stock_base_frames,
            "base_seconds": frames_to_seconds(
                stock_base_frames,
                fps,
            ),
            "maximum_frames": stock_max_frames,
            "maximum_seconds": frames_to_seconds(
                stock_max_frames,
                fps,
            ),
            "selected_frames": min(
                selected_stock_frames,
                stock_max_frames,
            ),
            "selected_seconds": frames_to_seconds(
                min(selected_stock_frames, stock_max_frames),
                fps,
            ),
        },
        "ai_images": {
            "unique_count": len(ai_image_specs),
            "base_frames": ai_base_frames,
            "base_seconds": frames_to_seconds(
                ai_base_frames,
                fps,
            ),
            "maximum_frames": ai_max_frames,
            "maximum_seconds": frames_to_seconds(
                ai_max_frames,
                fps,
            ),
            "selected_frames": selected_ai_frames,
            "selected_seconds": frames_to_seconds(
                selected_ai_frames,
                fps,
            ),
        },
        "ai_video": {
            "segment_count": len(ai_video_specs),
            "frames": ai_video_frames,
            "seconds": frames_to_seconds(
                ai_video_frames,
                fps,
            ),
        },
        "deficit": {
            "frames": total_deficit_frames,
            "seconds": frames_to_seconds(
                total_deficit_frames,
                fps,
            ),
            "estimated_additional_stock_clips": (
                estimated_additional_clips
            ),
        },
    }


def materialize_hybrid_capacity_plan(
    stock_clips: list[dict[str, Any]],
    ai_image_specs: list[dict[str, Any]],
    capacity_report: dict[str, Any],
    quality_gates: dict[str, Any] | None = None,
    fps: int = DEFAULT_FPS,
) -> dict[str, Any]:
    if not capacity_report.get("approved"):
        raise HybridCapacityError(
            "Hybrid visual capacity is insufficient.",
            capacity_report,
        )

    settings = resolve_capacity_settings(
        quality_gates,
        fps=fps,
    )
    fps = int(settings["fps"])
    base_stock_specs = build_stock_segment_specs(
        stock_clips=stock_clips,
        max_segments_per_clip=int(
            settings["maximum_stock_segments_per_clip"]
        ),
        maximum_segment_seconds=float(
            settings["maximum_stock_segment_seconds"]
        ),
        stock_segment_seconds=float(
            settings["stock_segment_seconds"]
        ),
        fps=fps,
    )
    expanded_ai_specs = expand_ai_image_specs_for_target(
        ai_specs=ai_image_specs,
        maximum_uses_per_image=int(
            settings["maximum_ai_image_uses"]
        ),
        maximum_segment_seconds=float(
            settings["maximum_ai_image_segment_seconds"]
        ),
        fps=fps,
        target_total_frames=int(
            capacity_report["ai_images"]["selected_frames"]
        ),
    ) if ai_image_specs else []
    expanded_stock_specs = expand_stock_specs_for_target(
        stock_clips=stock_clips,
        stock_specs=base_stock_specs,
        maximum_segment_seconds=float(
            settings["maximum_stock_segment_seconds"]
        ),
        fps=fps,
        target_total_frames=int(
            capacity_report["stock"]["selected_frames"]
        ),
    )

    actual_stock_frames = sum(
        int(item["duration_frames"])
        for item in expanded_stock_specs
    )
    actual_ai_frames = sum(
        int(item["duration_frames"])
        for item in expanded_ai_specs
    )
    expected_stock_frames = int(
        capacity_report["stock"]["selected_frames"]
    )
    expected_ai_frames = int(
        capacity_report["ai_images"]["selected_frames"]
    )

    if (
        actual_stock_frames != expected_stock_frames
        or actual_ai_frames != expected_ai_frames
    ):
        mismatch_report = dict(capacity_report)
        mismatch_report["allocation_mismatch"] = {
            "expected_stock_frames": expected_stock_frames,
            "actual_stock_frames": actual_stock_frames,
            "expected_ai_frames": expected_ai_frames,
            "actual_ai_frames": actual_ai_frames,
        }
        raise HybridCapacityError(
            "Hybrid capacity allocation did not materialize "
            "the approved frame plan.",
            mismatch_report,
        )

    return {
        "contract_version": CAPACITY_CONTRACT_VERSION,
        "fps": fps,
        "base_stock_specs": base_stock_specs,
        "stock_specs": expanded_stock_specs,
        "ai_image_specs": expanded_ai_specs,
        "allocation": {
            "stock_frames": actual_stock_frames,
            "stock_seconds": frames_to_seconds(
                actual_stock_frames,
                fps,
            ),
            "ai_image_frames": actual_ai_frames,
            "ai_image_seconds": frames_to_seconds(
                actual_ai_frames,
                fps,
            ),
        },
    }


def require_hybrid_capacity(
    *args: Any,
    **kwargs: Any,
) -> dict[str, Any]:
    report = build_hybrid_capacity_report(
        *args,
        **kwargs,
    )

    if not report["approved"]:
        raise HybridCapacityError(
            "Hybrid visual capacity is insufficient.",
            report,
        )

    return report


def audio_duration_from_assembly(
    audio_assembly: dict[str, Any],
) -> float:
    audio = audio_assembly.get("audio", {})
    value = (
        audio.get("actual_duration_seconds")
        or audio_assembly.get("actual_duration_seconds")
        or audio_assembly.get("duration_seconds")
    )

    if value is None:
        raise ValueError(
            "Audio assembly has no actual duration."
        )

    return float(value)


def ai_image_specs_from_generation(
    generation: dict[str, Any],
) -> list[dict[str, Any]]:
    items = generation.get("generated_images", [])

    return [
        {
            "segment_id": str(
                item.get("insert_id")
                or f"AI-{index:03d}"
            ),
            "duration_seconds": float(
                item.get("target_duration_seconds", 5.0)
            ),
            "source_relative_path": item.get(
                "relative_path"
            ),
        }
        for index, item in enumerate(items, start=1)
    ]


def ai_video_specs_from_generation(
    generation: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if not generation:
        return []

    items = (
        generation.get("generated_videos")
        or generation.get("items")
        or []
    )

    return [
        {
            "segment_id": str(
                item.get("insert_id")
                or item.get("segment_id")
                or f"AI-VIDEO-{index:03d}"
            ),
            "duration_seconds": float(
                item.get("duration_seconds", 0)
            ),
            "source_relative_path": item.get(
                "relative_path"
            ),
        }
        for index, item in enumerate(items, start=1)
        if float(item.get("duration_seconds", 0)) > 0
    ]


def stock_clips_from_manifest(
    manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    clips = []

    for index, item in enumerate(
        manifest.get("items", []),
        start=1,
    ):
        status = str(
            item.get("status", "approved")
        ).lower()

        if status and not status.startswith("approved"):
            continue

        if not item.get("duration_seconds"):
            continue

        clip = dict(item)
        clip["asset_id"] = str(
            clip.get("asset_id")
            or f"STOCK-{index:03d}"
        )
        clip["candidate_id"] = str(
            clip.get("candidate_id")
            or f"STOCK-C{index:03d}"
        )
        clip["role"] = str(
            clip.get("role")
            or "topic_specific_stock_footage"
        )
        clips.append(clip)

    return clips


def build_capacity_report_from_records(
    context: dict[str, Any],
    stock_manifest: dict[str, Any],
    audio_assembly: dict[str, Any],
    ai_visual_generation: dict[str, Any],
    ai_video_generation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return build_hybrid_capacity_report(
        stock_clips=stock_clips_from_manifest(
            stock_manifest
        ),
        ai_image_specs=ai_image_specs_from_generation(
            ai_visual_generation
        ),
        ai_video_specs=ai_video_specs_from_generation(
            ai_video_generation
        ),
        audio_duration_seconds=audio_duration_from_assembly(
            audio_assembly
        ),
        quality_gates=context.get(
            "quality_gates",
            {},
        ),
    )
