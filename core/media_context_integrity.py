import json
from pathlib import Path

from core.asset_usage_registry import (
    DEFAULT_REGISTRY_PATH,
    assert_asset_registered,
)


from core.content_usage_registry import (
    assert_context_content_registered,
)
from core.video_run_context import (
    PROJECT_ROOT,
    assert_no_latest_outputs,
    assert_no_latest_sources,
)


NON_FILE_OUTPUT_KEYS = {
    "youtube_url",
    "youtube_video_id",
}

STRICT_JSON_KEYS = {
    "script",
    "seo",
    "qa",
    "audio_assembly",
    "stock_manifest",
    "stock_qa",
    "thumbnail_strategy",
    "visual_asset_plan",
    "visual_plan",
    "ai_visual_generation",
    "ai_visual_qa",
    "ai_video_insert_plan",
    "ai_video_generation",
    "ai_video_qa",
    "thumbnail_record",
    "hybrid_video_assembly",
    "video_qa",
    "publisher",
}


def load_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(
            f"Required context file not found: {path}"
        )

    return json.loads(
        path.read_text(encoding="utf-8-sig")
    )


def is_url(reference: str) -> bool:
    normalized = reference.lower()
    return (
        normalized.startswith("https://")
        or normalized.startswith("http://")
    )


def resolve_reference(
    reference: str,
    project_root: Path
) -> Path:
    if Path(reference).is_absolute():
        raise ValueError(
            "Production reference must be repo-relative."
        )

    normalized = reference.replace("\\", "/").lower()

    if normalized.endswith("/latest.json"):
        raise ValueError(
            "Production reference cannot use latest.json."
        )

    path = project_root / reference

    if not path.exists():
        raise FileNotFoundError(
            f"Production reference not found: {path}"
        )

    return path


def extract_record_identity(
    data: dict
) -> tuple[str | None, str | None, str | None]:
    source = data.get("source", {})

    if not isinstance(source, dict):
        source = {}

    channel = (
        data.get("channel")
        or source.get("channel")
    )
    video_id = (
        data.get("video_id")
        or source.get("video_id")
    )
    run_id = (
        data.get("run_id")
        or source.get("run_id")
    )

    return channel, video_id, run_id


def assert_record_identity(
    data: dict,
    context: dict,
    label: str
) -> None:
    channel, video_id, run_id = extract_record_identity(
        data
    )

    if not channel:
        raise ValueError(
            f"{label} has no channel identity."
        )

    if not video_id:
        raise ValueError(
            f"{label} has no video_id identity."
        )

    if not run_id:
        raise ValueError(
            f"{label} has no run_id identity."
        )

    if channel.lower() != context["channel"].lower():
        raise ValueError(
            f"{label} channel mismatch."
        )

    if video_id.lower() != context["video_id"].lower():
        raise ValueError(
            f"{label} video_id mismatch."
        )

    if run_id != context["run_id"]:
        raise ValueError(
            f"{label} run_id mismatch."
        )


def get_production_reference(
    context: dict,
    key: str
) -> str | None:
    if key in context.get("outputs", {}):
        return context["outputs"][key]

    return context.get("sources", {}).get(key)


def validate_media_context(
    context: dict,
    project_root: Path = PROJECT_ROOT,
    registry_path: Path = DEFAULT_REGISTRY_PATH
) -> dict:
    assert_no_latest_sources(context)
    assert_no_latest_outputs(context)

    validated_json_records = 0
    validated_assets = 0
    validated_paths = set()

    def validate_asset(
        reference: str,
        expected_sha256: str | None,
        label: str
    ) -> None:
        nonlocal validated_assets

        path = resolve_reference(
            reference=reference,
            project_root=project_root
        )

        cache_key = (
            str(path.resolve()),
            expected_sha256
        )

        if cache_key in validated_paths:
            return

        assert_asset_registered(
            path=path,
            channel=context["channel"],
            video_id=context["video_id"],
            expected_sha256=expected_sha256,
            registry_path=registry_path,
            project_root=project_root
        )

        validated_paths.add(cache_key)
        validated_assets += 1

    for collection_name in ("sources", "outputs"):
        collection = context.get(
            collection_name,
            {}
        )

        for key, reference in collection.items():
            if key in NON_FILE_OUTPUT_KEYS:
                continue

            if is_url(reference):
                continue

            path = resolve_reference(
                reference=reference,
                project_root=project_root
            )

            if (
                path.suffix.lower() == ".json"
                and key in STRICT_JSON_KEYS
            ):
                data = load_json(path)

                assert_record_identity(
                    data=data,
                    context=context,
                    label=f"{collection_name}.{key}"
                )

                validated_json_records += 1

    stock_reference = get_production_reference(
        context,
        "stock_manifest"
    )

    if stock_reference:
        stock_data = load_json(
            resolve_reference(
                stock_reference,
                project_root
            )
        )

        for item in stock_data.get("items", []):
            status = str(
                item.get("status", "")
            ).lower()

            if not status.startswith("approved"):
                continue

            if not item.get("sha256"):
                raise ValueError(
                    "Approved stock asset has no SHA-256."
                )

            validate_asset(
                reference=item["relative_path"],
                expected_sha256=item["sha256"],
                label=item.get(
                    "candidate_id",
                    "stock"
                )
            )

    visual_reference = get_production_reference(
        context,
        "ai_visual_generation"
    )

    if visual_reference:
        visual_data = load_json(
            resolve_reference(
                visual_reference,
                project_root
            )
        )

        used_hashes = set()

        for item in visual_data.get(
            "generated_images",
            []
        ):
            asset_hash = item.get("sha256")

            if not asset_hash:
                raise ValueError(
                    "AI visual has no SHA-256."
                )

            if asset_hash in used_hashes:
                raise ValueError(
                    "Duplicate AI visual hash detected."
                )

            used_hashes.add(asset_hash)

            validate_asset(
                reference=item["relative_path"],
                expected_sha256=asset_hash,
                label=item["insert_id"]
            )

    ai_video_generation_reference = get_production_reference(
        context,
        "ai_video_generation"
    )
    ai_video_qa_reference = get_production_reference(
        context,
        "ai_video_qa"
    )

    if ai_video_generation_reference and ai_video_qa_reference:
        ai_video_generation = load_json(
            resolve_reference(
                ai_video_generation_reference,
                project_root
            )
        )
        ai_video_qa = load_json(
            resolve_reference(
                ai_video_qa_reference,
                project_root
            )
        )

        if ai_video_generation.get("generation_mode") != "live":
            raise ValueError(
                "Non-live AI video generation cannot enter "
                "production context validation."
            )

        if ai_video_qa.get("status") != "approved":
            raise ValueError("AI video QA is not approved.")

        approved_ids = {
            item["insert_id"]
            for item in ai_video_qa.get("video_checks", [])
            if item.get("approved") is True
        }
        used_hashes = set()

        for item in ai_video_generation.get(
            "generated_videos",
            []
        ):
            if item.get("insert_id") not in approved_ids:
                continue

            asset_hash = item.get("sha256")

            if not asset_hash:
                raise ValueError(
                    "Approved AI video has no SHA-256."
                )

            if asset_hash in used_hashes:
                raise ValueError(
                    "Duplicate AI video hash detected."
                )

            used_hashes.add(asset_hash)
            validate_asset(
                reference=item["relative_path"],
                expected_sha256=asset_hash,
                label=item["insert_id"]
            )

    thumbnail_record_reference = (
        get_production_reference(
            context,
            "thumbnail_record"
        )
    )

    if thumbnail_record_reference:
        thumbnail_data = load_json(
            resolve_reference(
                thumbnail_record_reference,
                project_root
            )
        )["thumbnail"]

        if not thumbnail_data.get("sha256"):
            raise ValueError(
                "Thumbnail has no SHA-256."
            )

        validate_asset(
            reference=thumbnail_data["relative_path"],
            expected_sha256=thumbnail_data["sha256"],
            label="thumbnail"
        )

        if (
            context.get("outputs", {}).get("thumbnail")
            != thumbnail_data["relative_path"]
        ):
            raise ValueError(
                "Thumbnail context path mismatch."
            )

    audio_reference = get_production_reference(
        context,
        "audio_assembly"
    )

    if audio_reference:
        audio_data = load_json(
            resolve_reference(
                audio_reference,
                project_root
            )
        )

        for section in audio_data.get(
            "audio",
            {}
        ).get("source_sections", []):
            if not section.get("sha256"):
                raise ValueError(
                    "Narration section has no SHA-256."
                )

            validate_asset(
                reference=section["relative_path"],
                expected_sha256=section["sha256"],
                label=f"audio_section_{section.get('sequence')}"
            )

        combined = audio_data.get(
            "audio",
            {}
        ).get("combined_audio", {})

        if not combined.get("sha256"):
            raise ValueError(
                "Combined narration has no SHA-256."
            )

        validate_asset(
            reference=combined["relative_path"],
            expected_sha256=combined["sha256"],
            label="narration_audio"
        )

        if (
            context.get(
                "outputs",
                {}
            ).get("narration_audio")
            != combined["relative_path"]
        ):
            raise ValueError(
                "Narration context path mismatch."
            )

    hybrid_reference = get_production_reference(
        context,
        "hybrid_video_assembly"
    )

    if hybrid_reference:
        hybrid_data = load_json(
            resolve_reference(
                hybrid_reference,
                project_root
            )
        )

        video_data = hybrid_data.get("video", {})

        if not video_data.get("sha256"):
            raise ValueError(
                "Final video has no SHA-256."
            )

        validate_asset(
            reference=video_data["relative_path"],
            expected_sha256=video_data["sha256"],
            label="final_video"
        )

        if (
            context.get("outputs", {}).get("final_video")
            != video_data["relative_path"]
        ):
            raise ValueError(
                "Final video context path mismatch."
            )

    video_qa_reference = get_production_reference(
        context,
        "video_qa"
    )

    if video_qa_reference:
        video_qa = load_json(
            resolve_reference(
                video_qa_reference,
                project_root
            )
        )

        qa_video_path = (
            video_qa.get("summary", {}).get(
                "video_path"
            )
            or video_qa.get("source", {}).get(
                "video_reference"
            )
        )

        qa_video_hash = (
            video_qa.get("summary", {}).get(
                "video_sha256"
            )
            or video_qa.get("source", {}).get(
                "video_sha256"
            )
        )

        if (
            qa_video_path
            != context.get(
                "outputs",
                {}
            ).get("final_video")
        ):
            raise ValueError(
                "Video QA final video path mismatch."
            )

        validate_asset(
            reference=qa_video_path,
            expected_sha256=qa_video_hash,
            label="video_qa_final_video"
        )

    publisher_reference = get_production_reference(
        context,
        "publisher"
    )

    if publisher_reference:
        publisher = load_json(
            resolve_reference(
                publisher_reference,
                project_root
            )
        )

        assets = publisher.get(
            "publishing_package",
            {}
        ).get("assets", {})

        publisher_video = assets.get(
            "video_file_path"
        )
        publisher_thumbnail = assets.get(
            "thumbnail_image_path"
        )

        if (
            publisher_video
            != context.get(
                "outputs",
                {}
            ).get("final_video")
        ):
            raise ValueError(
                "Publisher final video path mismatch."
            )

        if (
            publisher_thumbnail
            != context.get(
                "outputs",
                {}
            ).get("thumbnail")
        ):
            raise ValueError(
                "Publisher thumbnail path mismatch."
            )

        validate_asset(
            reference=publisher_video,
            expected_sha256=None,
            label="publisher_video"
        )

        validate_asset(
            reference=publisher_thumbnail,
            expected_sha256=None,
            label="publisher_thumbnail"
        )

    content_result = (
        assert_context_content_registered(
            context=context,
            project_root=project_root
        )
    )

    return {
        "channel": context["channel"],
        "video_id": context["video_id"],
        "run_id": context["run_id"],
        "validated_json_record_count": (
            validated_json_records
        ),
        "validated_asset_count": validated_assets,
        "validated_content_record_count": (
            content_result["record_count"]
        ),
        "status": "passed"
    }
