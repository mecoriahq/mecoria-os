import argparse
import hashlib
import html
import json
import math
import re
import shutil
import subprocess
import sys
import time
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent.parent
VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".mkv"}
BRIDGE_VERSION = "1.0"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agents.stock_asset_ingest.run import (
    build_role_catalog,
)
from core.video_run_context import (
    load_context,
    resolve_output,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict:
    return json.loads(
        path.read_text(encoding="utf-8-sig")
    )


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )


def repo_relative(path: Path) -> str:
    return str(
        path.resolve().relative_to(PROJECT_ROOT.resolve())
    ).replace("\\", "/")


def normalize_slug(value: str) -> str:
    value = value.lower().replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-+", "-", value)
    return value.strip("-") or "stock-footage"


def safe_filename(value: str) -> str:
    name = Path(value).name
    stem = re.sub(
        r"[^A-Za-z0-9._-]+",
        "-",
        Path(name).stem,
    ).strip("-_.")
    suffix = Path(name).suffix.lower()
    return (stem[:72] or "storyblocks-clip") + suffix


def storyblocks_search_url(query: str) -> str:
    slug = normalize_slug(query)
    encoded = quote(slug, safe="-")
    return (
        "https://www.storyblocks.com/video/search/"
        f"{encoded}?media-type=footage"
    )


def extract_script_sections(script_data: dict) -> list[dict]:
    script = script_data.get("script", script_data)
    sections = []

    for index, section in enumerate(
        script.get("main_sections", []),
        start=1,
    ):
        title = str(
            section.get("title", f"Section {index}")
        ).strip()
        visual_direction = str(
            section.get("visual_direction", "")
        ).strip()
        narration = str(
            section.get("narration", "")
        ).strip()

        sections.append({
            "index": index,
            "title": title,
            "visual_direction": visual_direction,
            "narration": narration,
        })

    return sections


def role_title_tokens(value: str) -> set[str]:
    return {
        token
        for token in normalize_slug(value).split("-")
        if len(token) >= 3
        and token not in {
            "the",
            "and",
            "into",
            "from",
            "when",
            "with",
            "without",
            "that",
            "this",
            "becomes",
        }
    }


def match_role(
    section: dict,
    role_catalog: list[dict],
) -> dict:
    section_tokens = role_title_tokens(section["title"])
    ranked = []

    for role in role_catalog:
        role_tokens = role_title_tokens(
            " ".join([
                str(role.get("role_id", "")),
                str(role.get("title", "")),
                " ".join(role.get("keywords", [])),
            ])
        )
        overlap = len(section_tokens.intersection(role_tokens))
        ranked.append((
            -overlap,
            int(role.get("usage_priority", 99)),
            str(role.get("role_id", "")),
            role,
        ))

    ranked.sort()
    return ranked[0][-1]


def query_from_section(section: dict) -> str:
    visual = section["visual_direction"]
    phrases = [
        phrase.strip()
        for phrase in re.split(r"[,.;]", visual)
        if phrase.strip()
    ]

    source = " ".join(
        phrases[:2]
        if phrases
        else [section["title"]]
    )

    tokens = [
        token
        for token in re.findall(
            r"[A-Za-z0-9]+",
            source.lower(),
        )
        if len(token) >= 3
        and token not in {
            "shot",
            "shots",
            "close",
            "wide",
            "showing",
            "view",
            "views",
            "moving",
            "across",
            "inside",
            "then",
            "with",
            "over",
            "onto",
            "from",
        }
    ]

    unique = []
    for token in tokens:
        if token not in unique:
            unique.append(token)

    if not unique:
        unique = list(
            role_title_tokens(section["title"])
        )

    return " ".join(unique[:8])


def allocate_clip_counts(
    target_clip_count: int,
    role_count: int,
) -> list[int]:
    if target_clip_count < role_count:
        raise ValueError(
            "target_clip_count must be at least role_count."
        )

    base = target_clip_count // role_count
    remainder = target_clip_count % role_count

    return [
        base + (1 if index < remainder else 0)
        for index in range(role_count)
    ]


def build_search_groups(
    script_data: dict,
    role_catalog: list[dict],
    target_clip_count: int = 30,
    minimum_roles: int = 6,
) -> list[dict]:
    sections = extract_script_sections(script_data)

    if len(sections) < minimum_roles:
        raise ValueError(
            "Script does not contain enough main sections "
            "for Storyblocks coverage."
        )

    selected = sections[:minimum_roles]
    counts = allocate_clip_counts(
        target_clip_count=target_clip_count,
        role_count=len(selected),
    )

    groups = []

    for position, (section, clip_count) in enumerate(
        zip(selected, counts),
        start=1,
    ):
        catalog_role = match_role(
            section=section,
            role_catalog=role_catalog,
        )
        role_id = (
            f"sb_{position:02d}_"
            + normalize_slug(
                section["title"]
            ).replace("-", "_")[:24]
        )
        query = query_from_section(section)

        groups.append({
            "group_index": position,
            "role_id": role_id,
            "catalog_role_id": str(
                catalog_role["role_id"]
            ),
            "role_title": section["title"],
            "query": query,
            "search_url": storyblocks_search_url(query),
            "target_clip_count": clip_count,
            "visual_direction": section[
                "visual_direction"
            ],
        })

    return groups


def output_dir(context: dict) -> Path:
    return (
        BASE_DIR
        / "output"
        / context["channel"]
        / context["video_id"]
        / context["run_id"]
    )


def source_dir(context: dict) -> Path:
    return (
        PROJECT_ROOT
        / "assets"
        / "stock"
        / context["channel"]
        / context["video_id"]
        / "storyblocks"
    )


def group_dir(
    context: dict,
    group: dict,
) -> Path:
    return (
        source_dir(context)
        / (
            f"{group['group_index']:02d}_"
            f"{normalize_slug(group['role_id']).replace('-', '_')}"
        )
    )


def video_files(path: Path) -> list[Path]:
    if not path.exists():
        return []

    return sorted(
        [
            item
            for item in path.rglob("*")
            if item.is_file()
            and item.suffix.lower() in VIDEO_EXTENSIONS
        ],
        key=lambda item: (
            item.stat().st_mtime_ns,
            item.name.lower(),
        ),
    )


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(
            lambda: stream.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)
    return digest.hexdigest()


def snapshot_downloads(
    downloads_dir: Path,
) -> dict[str, tuple[int, int]]:
    return {
        str(path.resolve()): (
            path.stat().st_size,
            path.stat().st_mtime_ns,
        )
        for path in video_files(downloads_dir)
    }


def new_downloads(
    downloads_dir: Path,
    before: dict[str, tuple[int, int]],
) -> list[Path]:
    candidates = []

    for path in video_files(downloads_dir):
        key = str(path.resolve())
        state = (
            path.stat().st_size,
            path.stat().st_mtime_ns,
        )

        if key not in before or before[key] != state:
            candidates.append(path)

    return candidates


def wait_for_downloads_to_settle(
    downloads_dir: Path,
    before: dict[str, tuple[int, int]],
    timeout_seconds: int = 90,
) -> list[Path]:
    deadline = time.time() + timeout_seconds
    previous = None
    stable_rounds = 0

    while time.time() < deadline:
        partials = list(
            downloads_dir.glob("*.crdownload")
        ) + list(
            downloads_dir.glob("*.part")
        )
        current = [
            (
                str(path.resolve()),
                path.stat().st_size,
                path.stat().st_mtime_ns,
            )
            for path in new_downloads(
                downloads_dir,
                before,
            )
        ]

        if current and not partials and current == previous:
            stable_rounds += 1
        else:
            stable_rounds = 0

        if stable_rounds >= 2:
            return [
                Path(item[0])
                for item in current
            ]

        previous = current
        time.sleep(1)

    return new_downloads(
        downloads_dir,
        before,
    )


def current_hashes(context: dict) -> set[str]:
    return {
        file_sha256(path)
        for path in video_files(
            source_dir(context)
        )
    }


def import_group_downloads(
    context: dict,
    group: dict,
    downloads: list[Path],
    required_count: int,
) -> list[Path]:
    destination = group_dir(
        context=context,
        group=group,
    )
    destination.mkdir(
        parents=True,
        exist_ok=True,
    )

    known_hashes = current_hashes(context)
    imported = []

    for path in downloads:
        if len(imported) >= required_count:
            break

        digest = file_sha256(path)

        if digest in known_hashes:
            continue

        role_prefix = (
            "mecoria-role-"
            + normalize_slug(group["role_id"]).replace(
                "-",
                "_",
            )
        )
        sequence = len(
            video_files(destination)
        ) + len(imported) + 1
        target = destination / (
            f"{role_prefix}__{sequence:03d}__"
            f"{safe_filename(path.name)}"
        )

        shutil.copy2(path, target)
        imported.append(target)
        known_hashes.add(digest)

    return imported


def group_progress(
    context: dict,
    group: dict,
) -> int:
    return len(
        video_files(
            group_dir(
                context=context,
                group=group,
            )
        )
    )


def plan_payload(
    context: dict,
    groups: list[dict],
    downloads_dir: Path,
) -> dict:
    return {
        "agent": "storyblocks_bridge",
        "version": BRIDGE_VERSION,
        "channel": context["channel"],
        "video_id": context["video_id"],
        "run_id": context["run_id"],
        "provider": "storyblocks",
        "mode": "manual_download_bridge",
        "topic": context["topic_title"],
        "downloads_dir": str(downloads_dir),
        "source_dir": repo_relative(
            source_dir(context)
        ),
        "target_clip_count": sum(
            group["target_clip_count"]
            for group in groups
        ),
        "group_count": len(groups),
        "groups": groups,
        "created_at": utc_now(),
    }


def render_dashboard(plan: dict) -> str:
    rows = []

    for group in plan["groups"]:
        rows.append(
            "<tr>"
            f"<td>{group['group_index']}</td>"
            f"<td>{html.escape(group['role_title'])}</td>"
            f"<td>{group['target_clip_count']}</td>"
            f"<td>{html.escape(group['query'])}</td>"
            "<td>"
            f"<a href=\"{html.escape(group['search_url'])}\" "
            "target=\"_blank\">Open Storyblocks search</a>"
            "</td>"
            "</tr>"
        )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Storyblocks Bridge - {html.escape(plan['video_id'])}</title>
<style>
body {{ font-family: Arial, sans-serif; max-width: 1100px; margin: 32px auto; line-height: 1.5; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border: 1px solid #bbb; padding: 10px; text-align: left; }}
th {{ background: #eee; }}
.notice {{ padding: 14px; background: #fff4c2; margin-bottom: 18px; }}
</style>
</head>
<body>
<h1>Storyblocks Download Queue</h1>
<p><strong>Video:</strong> {html.escape(plan['video_id'])}</p>
<p><strong>Topic:</strong> {html.escape(plan['topic'])}</p>
<div class="notice">
Run <code>python scripts\\mecoria_media.py run {html.escape(plan['channel'])}</code>.
The runner opens each search in order, collects the new downloads automatically,
renames them, builds the license manifest, and resumes production.
</div>
<table>
<thead>
<tr><th>#</th><th>Visual role</th><th>Clips</th><th>Search query</th><th>Link</th></tr>
</thead>
<tbody>
{''.join(rows)}
</tbody>
</table>
</body>
</html>
"""


def write_plan(
    context: dict,
    plan: dict,
) -> tuple[Path, Path]:
    directory = output_dir(context)
    plan_path = directory / "storyblocks_plan.json"
    dashboard_path = directory / "storyblocks_dashboard.html"

    save_json(plan_path, plan)
    dashboard_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    dashboard_path.write_text(
        render_dashboard(plan),
        encoding="utf-8",
    )

    return plan_path, dashboard_path


def run_stock_ingest(
    context: dict,
) -> None:
    command = [
        sys.executable,
        str(
            PROJECT_ROOT
            / "agents"
            / "stock_asset_ingest"
            / "run.py"
        ),
        "--channel",
        context["channel"],
        "--video-id",
        context["video_id"],
        "--source",
        repo_relative(source_dir(context)),
        "--source-name",
        "storyblocks",
        "--license-status",
        (
            "storyblocks_active_subscription_"
            "manual_download"
        ),
    ]

    result = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        check=False,
    )

    if result.returncode != 0:
        raise RuntimeError(
            "Storyblocks stock ingest failed with exit code "
            f"{result.returncode}."
        )


def interactive_collect(
    context: dict,
    groups: list[dict],
    downloads_dir: Path,
    open_browser: bool,
) -> bool:
    downloads_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    for group in groups:
        target = int(
            group["target_clip_count"]
        )

        while True:
            current = group_progress(
                context=context,
                group=group,
            )
            remaining = target - current

            if remaining <= 0:
                print(
                    "STORYBLOCKS_GROUP_READY: "
                    f"{group['group_index']}/{len(groups)} "
                    f"{group['role_title']} "
                    f"{current}/{target}"
                )
                break

            print("")
            print(
                "STORYBLOCKS_GROUP: "
                f"{group['group_index']}/{len(groups)}"
            )
            print(
                f"VISUAL_ROLE: {group['role_title']}"
            )
            print(f"SEARCH_QUERY: {group['query']}")
            print(
                f"DOWNLOAD_REQUIRED: {remaining}"
            )
            print(
                f"SEARCH_URL: {group['search_url']}"
            )

            before = snapshot_downloads(
                downloads_dir
            )

            if open_browser:
                webbrowser.open(
                    group["search_url"]
                )

            response = input(
                "Download the requested unique horizontal "
                "clips, then press Enter. "
                "Type STOP to pause: "
            ).strip().upper()

            if response == "STOP":
                return False

            candidates = wait_for_downloads_to_settle(
                downloads_dir=downloads_dir,
                before=before,
            )

            imported = import_group_downloads(
                context=context,
                group=group,
                downloads=candidates,
                required_count=remaining,
            )

            print(
                f"NEW_DOWNLOADS_FOUND: {len(candidates)}"
            )
            print(
                f"CLIPS_IMPORTED: {len(imported)}"
            )

            if not imported:
                print(
                    "NO_NEW_STORYBLOCKS_CLIPS: "
                    "Download clips from the opened search "
                    "and try again."
                )

    return True


def print_plan_summary(
    context: dict,
    plan: dict,
    plan_path: Path | None,
    dashboard_path: Path | None,
) -> None:
    print("STORYBLOCKS_BRIDGE_VERSION: 1.0")
    print(f"VIDEO_CONTEXT_ID: {context['video_id']}")
    print(f"RUN_ID: {context['run_id']}")
    print("PROVIDER: storyblocks")
    print(
        f"SEARCH_GROUP_COUNT: {plan['group_count']}"
    )
    print(
        f"TARGET_CLIP_COUNT: {plan['target_clip_count']}"
    )

    for group in plan["groups"]:
        print(
            f"- {group['group_index']:02d} | "
            f"{group['role_title']} | "
            f"{group['target_clip_count']} clips | "
            f"{group['query']}"
        )

    if plan_path:
        print(
            "STORYBLOCKS_PLAN: "
            f"{repo_relative(plan_path)}"
        )

    if dashboard_path:
        print(
            "STORYBLOCKS_DASHBOARD: "
            f"{repo_relative(dashboard_path)}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare Storyblocks searches, collect manual "
            "downloads, create the stock manifest, and "
            "hand production back to the Mecoria runner."
        )
    )
    parser.add_argument(
        "--channel",
        default="hiddenova",
    )
    parser.add_argument(
        "--video-id",
        required=True,
    )
    parser.add_argument(
        "--downloads-dir",
        default=str(
            Path.home() / "Downloads"
        ),
    )
    parser.add_argument(
        "--target-clips",
        type=int,
        default=30,
    )
    parser.add_argument(
        "--minimum-roles",
        type=int,
        default=6,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
    )
    parser.add_argument(
        "--no-open",
        action="store_true",
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    channel = args.channel.strip().lower()
    video_id = args.video_id.strip().lower()
    context = load_context(
        channel=channel,
        video_id=video_id,
    )

    if context.get("status") != "stock_source_required":
        raise ValueError(
            "Storyblocks Bridge requires "
            "stock_source_required status."
        )

    script_data = load_json(
        resolve_output(
            context=context,
            key="script",
        )
    )
    visual_plan_data = None

    if "visual_plan" in context.get("outputs", {}):
        try:
            visual_plan_data = load_json(
                resolve_output(
                    context=context,
                    key="visual_plan",
                )
            )
        except FileNotFoundError:
            visual_plan_data = None
    role_catalog = build_role_catalog(
        script_data=script_data,
        visual_plan_data=visual_plan_data,
    )
    groups = build_search_groups(
        script_data=script_data,
        role_catalog=role_catalog,
        target_clip_count=args.target_clips,
        minimum_roles=args.minimum_roles,
    )
    downloads_dir = Path(
        args.downloads_dir
    ).expanduser().resolve()
    plan = plan_payload(
        context=context,
        groups=groups,
        downloads_dir=downloads_dir,
    )

    if args.dry_run:
        print_plan_summary(
            context=context,
            plan=plan,
            plan_path=None,
            dashboard_path=None,
        )
        print("BROWSER_OPENED: false")
        print("CONTEXT_CHANGED: false")
        print("STATUS: storyblocks_bridge_dry_run_ready")
        return

    plan_path, dashboard_path = write_plan(
        context=context,
        plan=plan,
    )
    print_plan_summary(
        context=context,
        plan=plan,
        plan_path=plan_path,
        dashboard_path=dashboard_path,
    )

    if args.non_interactive:
        ready = all(
            group_progress(
                context=context,
                group=group,
            ) >= int(group["target_clip_count"])
            for group in groups
        )
    else:
        ready = interactive_collect(
            context=context,
            groups=groups,
            downloads_dir=downloads_dir,
            open_browser=not args.no_open,
        )

    imported_count = len(
        video_files(source_dir(context))
    )
    print(
        f"STORYBLOCKS_IMPORTED_CLIP_COUNT: "
        f"{imported_count}"
    )

    if not ready:
        print("CONTEXT_CHANGED: false")
        print(
            "STATUS: storyblocks_downloads_required"
        )
        return

    run_stock_ingest(context)

    print("STOCK_MANIFEST_ATTACHED: true")
    print("STATUS: storyblocks_manifest_ready")


if __name__ == "__main__":
    main()
