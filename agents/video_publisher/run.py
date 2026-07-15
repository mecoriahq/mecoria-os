import argparse
import json
from pathlib import Path

from jsonschema import validate


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent.parent


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

    context = load_json(context_path)

    if context.get("video_id") != video_id:
        raise ValueError("Run context video_id mismatch.")

    script_path = PROJECT_ROOT / context["sources"]["script"]
    seo_path = PROJECT_ROOT / context["sources"]["seo"]

    visual_output_dir = (
        PROJECT_ROOT
        / "agents"
        / "video_visual_pipeline"
        / "output"
        / channel
        / video_id
    )

    thumbnail_record_path = visual_output_dir / "thumbnail.json"
    visual_qa_path = visual_output_dir / "ai_visual_qa.json"

    video_qa_path = (
        PROJECT_ROOT
        / "agents"
        / "video_qa"
        / "output"
        / channel
        / "latest.json"
    )

    script_data = load_json(script_path)
    seo_data = load_json(seo_path)
    thumbnail_record = load_json(thumbnail_record_path)
    visual_qa_data = load_json(visual_qa_path)
    video_qa_data = load_json(video_qa_path)

    if script_data.get("channel") != channel:
        raise ValueError("Script channel mismatch.")

    if thumbnail_record.get("video_id") != video_id:
        raise ValueError("Thumbnail video_id mismatch.")

    if visual_qa_data.get("status") != "approved":
        raise ValueError("AI Visual QA is not approved.")

    if (
        visual_qa_data.get("source", {}).get("video_id")
        != video_id
    ):
        raise ValueError("AI Visual QA video_id mismatch.")

    if video_qa_data.get("status") != "approved":
        raise ValueError("Video QA is not approved.")

    seo = seo_data.get("seo", {})
    title = str(seo.get("video_title", "")).strip()
    description = str(seo.get("description", "")).strip()
    tags = seo.get("tags", [])

    if not title or not description or not tags:
        raise ValueError("SEO metadata is incomplete.")

    thumbnail_path = (
        PROJECT_ROOT
        / thumbnail_record["thumbnail"]["relative_path"]
    )

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

    context["status"] = "publisher_ready"
    context["outputs"]["publisher"] = relative_path(
        video_output_path
    )
    save_json(context_path, context)

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
