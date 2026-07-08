import json
from pathlib import Path

from dotenv import load_dotenv
from jsonschema import validate

from output import save_output


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent.parent

DEFAULT_CHANNEL = "hiddenova"
MIN_SVG_BYTES = 100


def load_json(file_path: Path) -> dict:
    if not file_path.exists():
        raise FileNotFoundError(f"Required file not found: {file_path}")

    return json.loads(file_path.read_text(encoding="utf-8"))


def load_schema() -> dict:
    return load_json(BASE_DIR / "schema.json")


def get_internal_visual_production_latest_path(channel: str) -> Path:
    return PROJECT_ROOT / "agents" / "internal_visual_production" / "output" / channel.lower() / "latest.json"


def get_relative_path(path: Path) -> str:
    return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")


def check_svg_file(file_data: dict) -> dict:
    relative_path = file_data["relative_path"]
    svg_path = PROJECT_ROOT / relative_path

    file_exists = svg_path.exists()
    file_readable = False
    size_bytes = None
    has_svg_tag = False

    if file_exists:
        try:
            size_bytes = svg_path.stat().st_size
            content = svg_path.read_text(encoding="utf-8")
            file_readable = True
            has_svg_tag = "<svg" in content and "</svg>" in content
        except OSError:
            file_readable = False
        except UnicodeDecodeError:
            file_readable = False

    format_valid = (
        file_data.get("format") == "svg"
        and svg_path.suffix.lower() == ".svg"
    )

    size_valid = size_bytes is not None and size_bytes >= MIN_SVG_BYTES

    passed_checks = sum([
        file_exists,
        file_readable,
        format_valid,
        size_valid,
        has_svg_tag
    ])

    score = round((passed_checks / 5) * 100)
    status = "pass" if score == 100 else "fail"

    return {
        "filename": file_data["filename"],
        "relative_path": relative_path,
        "file_exists": file_exists,
        "file_readable": file_readable,
        "format_valid": format_valid,
        "size_bytes": size_bytes,
        "size_valid": size_valid,
        "has_svg_tag": has_svg_tag,
        "status": status,
        "score": score
    }


def check_asset(asset: dict) -> dict:
    file_checks = [
        check_svg_file(file_data)
        for file_data in asset["output_files"]
    ]

    expected_files = len(asset["output_files"])
    valid_files = sum(
        1 for check in file_checks
        if check["status"] == "pass"
    )

    production_status_valid = asset["production_status"] == "internal_asset_ready"
    files_valid = expected_files > 0 and valid_files == expected_files

    approved = production_status_valid and files_valid

    return {
        "asset_id": asset["asset_id"],
        "asset_type": asset["asset_type"],
        "production_method": asset["production_method"],
        "production_status": asset["production_status"],
        "production_status_valid": production_status_valid,
        "expected_files": expected_files,
        "valid_files": valid_files,
        "status": "pass" if approved else "fail",
        "file_checks": file_checks
    }


def build_issues(asset_checks: list[dict]) -> list[dict]:
    issues = []

    for asset_check in asset_checks:
        if asset_check["status"] == "pass":
            continue

        if not asset_check["production_status_valid"]:
            issues.append({
                "field": asset_check["asset_id"],
                "severity": "high",
                "message": "Asset production status is not internal_asset_ready."
            })

        for file_check in asset_check["file_checks"]:
            if file_check["status"] == "pass":
                continue

            issues.append({
                "field": f'{asset_check["asset_id"]}:{file_check["filename"]}',
                "severity": "high",
                "message": (
                    "SVG file failed technical validation. "
                    f"file_exists={file_check['file_exists']}, "
                    f"file_readable={file_check['file_readable']}, "
                    f"format_valid={file_check['format_valid']}, "
                    f"size_valid={file_check['size_valid']}, "
                    f"has_svg_tag={file_check['has_svg_tag']}."
                )
            })

    return issues


def build_output(production_data: dict, production_path: Path) -> dict:
    assets = production_data["internal_visual_assets"]["assets"]

    asset_checks = [
        check_asset(asset)
        for asset in assets
    ]

    expected_assets = len(asset_checks)
    approved_assets = sum(
        1 for asset_check in asset_checks
        if asset_check["status"] == "pass"
    )

    total_files = sum(asset_check["expected_files"] for asset_check in asset_checks)
    valid_files = sum(asset_check["valid_files"] for asset_check in asset_checks)

    issues = build_issues(asset_checks)
    approved = expected_assets > 0 and approved_assets == expected_assets and not issues

    overall_score = round((approved_assets / expected_assets) * 100) if expected_assets else 0

    recommendations = []

    if approved:
        recommendations.append({
            "field": "visual_asset_integration",
            "suggestion": "Proceed to visual asset integration or motion/PNG rendering layer."
        })
    else:
        recommendations.append({
            "field": "internal_visual_production",
            "suggestion": "Fix failed SVG files and rerun internal visual production."
        })

    return {
        "agent": "internal_visual_qa",
        "version": "1.0",
        "channel": production_data["channel"],
        "status": "approved" if approved else "rejected",
        "overall_score": overall_score,
        "summary": {
            "expected_assets": expected_assets,
            "approved_assets": approved_assets,
            "total_files": total_files,
            "valid_files": valid_files,
            "next_agent": "visual_asset_integration" if approved else "internal_visual_production"
        },
        "asset_checks": asset_checks,
        "issues": issues,
        "recommendations": recommendations,
        "source": {
            "source_agents": [
                "internal_visual_production"
            ],
            "internal_visual_production_reference": get_relative_path(production_path)
        },
        "metadata": {
            "next_agent": "visual_asset_integration" if approved else "internal_visual_production"
        }
    }


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")

    production_path = get_internal_visual_production_latest_path(DEFAULT_CHANNEL)
    production_data = load_json(production_path)

    final_output = build_output(
        production_data=production_data,
        production_path=production_path
    )

    schema = load_schema()
    validate(instance=final_output, schema=schema)

    latest_path = save_output(
        channel=final_output["channel"],
        data=final_output
    )

    print("Internal Visual QA Agent completed successfully.")
    print(f"Output saved to: {latest_path}")


if __name__ == "__main__":
    main()
