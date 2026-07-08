import json
from pathlib import Path

from dotenv import load_dotenv
from jsonschema import validate
from PIL import Image

from output import save_output


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent.parent

DEFAULT_CHANNEL = "hiddenova"
EXPECTED_RESOLUTION = "1920x1080"
MIN_PNG_BYTES = 1024


def load_json(file_path: Path) -> dict:
    if not file_path.exists():
        raise FileNotFoundError(f"Required file not found: {file_path}")

    return json.loads(file_path.read_text(encoding="utf-8"))


def load_schema() -> dict:
    return load_json(BASE_DIR / "schema.json")


def get_internal_visual_render_latest_path(channel: str) -> Path:
    return PROJECT_ROOT / "agents" / "internal_visual_render" / "output" / channel.lower() / "latest.json"


def get_relative_path(path: Path) -> str:
    return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")


def check_png_file(file_data: dict) -> dict:
    relative_path = file_data["relative_path"]
    png_path = PROJECT_ROOT / relative_path

    file_exists = png_path.exists()
    file_readable = False
    pillow_readable = False
    format_valid = False
    resolution = None
    resolution_valid = False
    size_bytes = None
    size_valid = False

    if file_exists:
        try:
            size_bytes = png_path.stat().st_size
            size_valid = size_bytes >= MIN_PNG_BYTES

            with png_path.open("rb") as file:
                file.read(1)
            file_readable = True

            with Image.open(png_path) as image:
                pillow_readable = True
                format_valid = image.format == "PNG"
                resolution = f"{image.width}x{image.height}"
                resolution_valid = resolution == EXPECTED_RESOLUTION

        except OSError:
            file_readable = False
        except Exception:
            pillow_readable = False

    suffix_valid = png_path.suffix.lower() == ".png"
    declared_format_valid = file_data.get("format") == "png"

    passed_checks = sum([
        file_exists,
        file_readable,
        pillow_readable,
        format_valid,
        suffix_valid,
        declared_format_valid,
        size_valid,
        resolution_valid
    ])

    score = round((passed_checks / 8) * 100)
    status = "pass" if score == 100 else "fail"

    return {
        "filename": file_data["filename"],
        "relative_path": relative_path,
        "file_exists": file_exists,
        "file_readable": file_readable,
        "pillow_readable": pillow_readable,
        "format_valid": format_valid,
        "suffix_valid": suffix_valid,
        "declared_format_valid": declared_format_valid,
        "size_bytes": size_bytes,
        "size_valid": size_valid,
        "resolution": resolution,
        "expected_resolution": EXPECTED_RESOLUTION,
        "resolution_valid": resolution_valid,
        "status": status,
        "score": score
    }


def check_asset(asset: dict) -> dict:
    file_checks = [
        check_png_file(file_data)
        for file_data in asset["rendered_files"]
    ]

    expected_files = len(asset["rendered_files"])
    valid_files = sum(
        1 for check in file_checks
        if check["status"] == "pass"
    )

    status = "pass" if expected_files > 0 and valid_files == expected_files else "fail"

    return {
        "asset_id": asset["asset_id"],
        "asset_type": asset["asset_type"],
        "render_status": asset["status"],
        "expected_files": expected_files,
        "valid_files": valid_files,
        "status": status,
        "file_checks": file_checks
    }


def build_issues(asset_checks: list[dict]) -> list[dict]:
    issues = []

    for asset_check in asset_checks:
        if asset_check["status"] == "pass":
            continue

        for file_check in asset_check["file_checks"]:
            if file_check["status"] == "pass":
                continue

            issues.append({
                "field": f'{asset_check["asset_id"]}:{file_check["filename"]}',
                "severity": "high",
                "message": (
                    "Rendered PNG failed technical validation. "
                    f"file_exists={file_check['file_exists']}, "
                    f"file_readable={file_check['file_readable']}, "
                    f"pillow_readable={file_check['pillow_readable']}, "
                    f"format_valid={file_check['format_valid']}, "
                    f"size_valid={file_check['size_valid']}, "
                    f"resolution_valid={file_check['resolution_valid']}."
                )
            })

    return issues


def build_output(render_data: dict, render_path: Path) -> dict:
    rendered_assets = render_data["rendered_visual_assets"]["assets"]

    asset_checks = [
        check_asset(asset)
        for asset in rendered_assets
    ]

    expected_assets = len(asset_checks)
    approved_assets = sum(
        1 for asset_check in asset_checks
        if asset_check["status"] == "pass"
    )

    total_files = sum(asset_check["expected_files"] for asset_check in asset_checks)
    valid_files = sum(asset_check["valid_files"] for asset_check in asset_checks)

    issues = build_issues(asset_checks)

    approved = (
        expected_assets > 0
        and approved_assets == expected_assets
        and total_files > 0
        and valid_files == total_files
        and not issues
    )

    overall_score = round((approved_assets / expected_assets) * 100) if expected_assets else 0

    recommendations = []

    if approved:
        recommendations.append({
            "field": "video_assembly_v1",
            "suggestion": "Proceed to visual asset integration and section-based video assembly."
        })
    else:
        recommendations.append({
            "field": "internal_visual_render",
            "suggestion": "Fix invalid PNG renders and rerun internal visual rendering."
        })

    return {
        "agent": "internal_visual_render_qa",
        "version": "1.0",
        "channel": render_data["channel"],
        "status": "approved" if approved else "rejected",
        "overall_score": overall_score,
        "summary": {
            "expected_assets": expected_assets,
            "approved_assets": approved_assets,
            "total_files": total_files,
            "valid_files": valid_files,
            "next_agent": "video_assembly_v1" if approved else "internal_visual_render"
        },
        "asset_checks": asset_checks,
        "issues": issues,
        "recommendations": recommendations,
        "source": {
            "source_agents": [
                "internal_visual_render"
            ],
            "internal_visual_render_reference": get_relative_path(render_path)
        },
        "metadata": {
            "next_agent": "video_assembly_v1" if approved else "internal_visual_render"
        }
    }


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")

    render_path = get_internal_visual_render_latest_path(DEFAULT_CHANNEL)
    render_data = load_json(render_path)

    final_output = build_output(
        render_data=render_data,
        render_path=render_path
    )

    schema = load_schema()
    validate(instance=final_output, schema=schema)

    latest_path = save_output(
        channel=final_output["channel"],
        data=final_output
    )

    print("Internal Visual Render QA Agent completed successfully.")
    print(f"Output saved to: {latest_path}")


if __name__ == "__main__":
    main()
