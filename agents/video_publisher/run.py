import argparse
import json
import sys
from pathlib import Path

from jsonschema import validate


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
    assert_asset_registered,
)


from core.content_usage_registry import (
    register_context_content,
)
from core.media_context_integrity import (
    validate_media_context,
)


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


def resolve_context_asset(
    context: dict,
    key: str
) -> Path:
    if key in context.get("outputs", {}):
        return resolve_output(
            context=context,
            key=key
        )

    if key in context.get("sources", {}):
        return resolve_source(
            context=context,
            key=key
        )

    raise KeyError(f"Context asset is missing: {key}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a video-specific YouTube publishing package."
    )

    parser.add_argument("--channel", default="hiddenova")
    parser.add_argument("--video-id", required=True)
    parser.add_argument("--dry-run", action="store_true")

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    channel = args.channel.lower()
    video_id = args.video_id.lower()

    context_path = (
        PROJECT_ROOT
        / "records"
        / "run_contexts"
        / channel
        / f"{video_id}.json"
    )

    context = load_context(
        channel=channel,
        video_id=video_id
    )

    content_registration = register_context_content(
        context=context
    )

    integrity_result = validate_media_context(
        context=context
    )

    print(
        "CONTENT_FINGERPRINT_RECORDS: "
        f"{content_registration['record_count']}"
    )
    print(
        "MEDIA_CONTEXT_VALIDATED_ASSETS: "
        f"{integrity_result['validated_asset_count']}"
    )


    script_path = resolve_context_asset(
        context,
        "script"
    )
    seo_path = resolve_context_asset(
        context,
        "seo"
    )
    visual_qa_path = resolve_context_asset(
        context,
        "ai_visual_qa"
    )

    thumbnail_record_path = None

    if "thumbnail_record" in context.get("outputs", {}):
        thumbnail_record_path = resolve_context_asset(
            context,
            "thumbnail_record"
        )
        thumbnail_record = load_json(
            thumbnail_record_path
        )
        thumbnail_path = (
            PROJECT_ROOT
            / thumbnail_record["thumbnail"]["relative_path"]
        )
    else:
        thumbnail_record = None
        thumbnail_path = resolve_context_asset(
            context,
            "thumbnail"
        )

    video_qa_reference = context.get(
        "outputs",
        {}
    ).get("video_qa")

    if not video_qa_reference:
        raise ValueError(
            "Run context has no video_qa output."
        )

    if video_qa_reference.replace("\\", "/").lower().endswith(
        "/latest.json"
    ):
        raise ValueError(
            "Production publisher cannot use video_qa latest.json."
        )

    video_qa_path = PROJECT_ROOT / video_qa_reference

    script_data = load_json(script_path)
    seo_data = load_json(seo_path)
    visual_qa_data = load_json(visual_qa_path)
    video_qa_data = load_json(video_qa_path)

    if script_data.get("channel") != channel:
        raise ValueError("Script channel mismatch.")

    for name, data in (
        ("script", script_data),
        ("seo", seo_data)
    ):
        source_video_id = data.get("video_id")
        source_run_id = data.get("run_id")

        if (
            name in context.get("outputs", {})
            and source_video_id != video_id
        ):
            raise ValueError(f"{name} video_id mismatch.")

        if (
            name in context.get("outputs", {})
            and source_run_id != context["run_id"]
        ):
            raise ValueError(f"{name} run_id mismatch.")

    if thumbnail_record:
        if thumbnail_record.get("video_id") != video_id:
            raise ValueError("Thumbnail video_id mismatch.")

        if thumbnail_record.get("run_id") != context["run_id"]:
            raise ValueError("Thumbnail run_id mismatch.")

    if visual_qa_data.get("status") != "approved":
        raise ValueError("AI Visual QA is not approved.")

    visual_video_id = (
        visual_qa_data.get("video_id")
        or visual_qa_data.get("source", {}).get("video_id")
    )
    visual_run_id = (
        visual_qa_data.get("run_id")
        or visual_qa_data.get("source", {}).get("run_id")
    )

    if visual_video_id != video_id:
        raise ValueError("AI Visual QA video_id mismatch.")

    if visual_run_id != context["run_id"]:
        raise ValueError("AI Visual QA run_id mismatch.")

    if video_qa_data.get("status") != "approved":
        raise ValueError("Video QA is not approved.")

    seo = seo_data.get("seo", {})
    title = str(seo.get("video_title", "")).strip()
    description = str(seo.get("description", "")).strip()
    tags = seo.get("tags", [])

    if not title or not description or not tags:
        raise ValueError("SEO metadata is incomplete.")

    video_path_text = (
        video_qa_data.get("summary", {}).get("video_path")
        or video_qa_data.get("source", {}).get("video_reference")
    )

    if not video_path_text:
        raise ValueError("Approved video path is missing.")

    video_path = PROJECT_ROOT / video_path_text

    if not thumbnail_path.exists():
        raise FileNotFoundError(
            f"Thumbnail file not found: {thumbnail_path}"
        )

    if not video_path.exists():
        raise FileNotFoundError(
            f"Video file not found: {video_path}"
        )

    if not thumbnail_record:
        raise ValueError(
            "Production publisher requires thumbnail_record."
        )

    thumbnail_sha256 = thumbnail_record.get(
        "thumbnail",
        {}
    ).get("sha256")

    if not thumbnail_sha256:
        raise ValueError(
            "Thumbnail SHA-256 fingerprint is missing."
        )

    video_sha256 = (
        video_qa_data.get(
            "summary",
            {}
        ).get("video_sha256")
        or video_qa_data.get(
            "source",
            {}
        ).get("video_sha256")
    )

    if not video_sha256:
        raise ValueError(
            "Final video SHA-256 fingerprint is missing."
        )

    qa_video_id = video_qa_data.get(
        "source",
        {}
    ).get("video_id")
    qa_run_id = video_qa_data.get(
        "source",
        {}
    ).get("run_id")

    if qa_video_id != video_id:
        raise ValueError("Video QA video_id mismatch.")

    if qa_run_id != context["run_id"]:
        raise ValueError("Video QA run_id mismatch.")

    assert_asset_registered(
        path=thumbnail_path,
        channel=channel,
        video_id=video_id,
        expected_sha256=thumbnail_sha256
    )

    assert_asset_registered(
        path=video_path,
        channel=channel,
        video_id=video_id,
        expected_sha256=video_sha256
    )

    package = {
        "agent": "publisher",
        "version": "2.0",
        "channel": channel,
        "platform": "youtube",
        "status": "upload_ready",
        "publishing_package": {
            "video_metadata": {
                "title": title,
                "description": description,
                "tags": tags,
                "hashtags": seo.get("hashtags", []),
                "chapters": seo.get("chapters", [])
            },
            "assets": {
                "script_reference": relative_path(script_path),
                "seo_reference": relative_path(seo_path),
                "thumbnail_image_path": relative_path(
                    thumbnail_path
                ),
                "video_file_path": relative_path(video_path)
            },
            "readiness": {
                "metadata_ready": True,
                "thumbnail_ready": True,
                "video_ready": True,
                "upload_ready": True,
                "blocking_notes": []
            }
        },
        "source": {
            "video_id": video_id,
            "run_id": context["run_id"],
            "source_agents": [
                "script",
                "seo",
                "video_visual_pipeline",
                "ai_visual_qa",
                "video_qa"
            ],
            "execution_context_status": context["status"],
            "execution_context_next_agent": "youtube_upload",
            "video_qa_status": video_qa_data["status"],
            "video_qa_reference": relative_path(video_qa_path)
        },
        "metadata": {
            "next_agent": "youtube_upload"
        }
    }

    schema = load_json(
        PROJECT_ROOT / "agents" / "publisher" / "schema.json"
    )
    validate(instance=package, schema=schema)

    print(f"VIDEO_CONTEXT_ID: {video_id}")
    print(f"TITLE: {title}")
    print(
        "THUMBNAIL: "
        f"{package['publishing_package']['assets']['thumbnail_image_path']}"
    )
    print(
        "VIDEO: "
        f"{package['publishing_package']['assets']['video_file_path']}"
    )
    print(
        "DURATION: "
        f"{video_qa_data['summary']['duration_seconds']}s"
    )
    print("STATUS: upload_ready")

    if args.dry_run:
        return

    video_output_path = (
        BASE_DIR
        / "output"
        / channel
        / video_id
        / context["run_id"]
        / "publisher.json"
    )

    legacy_latest_path = (
        PROJECT_ROOT
        / "agents"
        / "publisher"
        / "output"
        / channel
        / "latest.json"
    )

    save_json(video_output_path, package)
    save_json(legacy_latest_path, package)

    context = register_output(
        context=context,
        agent="publisher",
        reference=relative_path(video_output_path),
        status="upload_ready"
    )

    if context.get("status") not in {
        "uploaded_for_founder_review",
        "published",
        "public"
    }:
        context = set_status(
            context=context,
            status="publisher_ready",
            next_agent="youtube_upload"
        )

    save_context(context)

    print(
        "VIDEO_PUBLISHER_OUTPUT: "
        f"{relative_path(video_output_path)}"
    )
    print(
        "LEGACY_PUBLISHER_LATEST_REFRESHED: "
        f"{relative_path(legacy_latest_path)}"
    )


if __name__ == "__main__":
    main()
