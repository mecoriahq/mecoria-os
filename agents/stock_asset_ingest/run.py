import argparse
import json
import re
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent.parent
VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".mkv"}

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.asset_usage_registry import (
    calculate_sha256,
    load_registry,
)
from core.video_run_context import (
    load_context,
    resolve_output,
    save_context,
    utc_now,
)


GENERIC_STOPWORDS = {
    "and",
    "about",
    "after",
    "again",
    "against",
    "along",
    "also",
    "among",
    "another",
    "because",
    "before",
    "being",
    "between",
    "card",
    "cards",
    "customer",
    "customers",
    "during",
    "each",
    "every",
    "from",
    "into",
    "more",
    "most",
    "other",
    "over",
    "payment",
    "payments",
    "purchase",
    "purchases",
    "same",
    "than",
    "that",
    "their",
    "them",
    "then",
    "there",
    "these",
    "they",
    "this",
    "through",
    "under",
    "when",
    "where",
    "which",
    "while",
    "with",
    "without",
    "would",
    "the",
    "are",
    "has",
    "have",
    "its",
    "not",
    "only",
    "one",
    "how",
    "can",
    "will",
    "video",
    "cinematic",
    "documentary",
}

CANONICAL_ROLE_RULES = [
    (
        "clearing_settlement",
        {
            "clearing",
            "settlement",
            "settles",
            "settled",
            "ledger",
            "ledgers",
            "batch",
            "batches",
        },
    ),
    (
        "authorization_hold",
        {
            "hold",
            "pending",
            "reserved",
            "reserve",
            "authorization",
            "authorisation",
        },
    ),
    (
        "payment_network",
        {
            "network",
            "routing",
            "route",
            "switch",
            "switchboard",
            "infrastructure",
            "server",
            "servers",
            "datacenter",
            "data-center",
            "datacentre",
        },
    ),
    (
        "issuer_risk_decision",
        {
            "fraud",
            "risk",
            "issuer",
            "issuing",
            "decision",
            "decline",
            "declined",
            "approve",
            "approved",
        },
    ),
    (
        "merchant_acquirer",
        {
            "merchant",
            "acquirer",
            "acquiring",
            "processor",
            "gateway",
            "store",
            "shop",
            "retail",
            "cashier",
            "checkout",
        },
    ),
    (
        "payment_terminal",
        {
            "terminal",
            "tap",
            "contactless",
            "reader",
            "chip",
            "swipe",
            "pin",
            "pos",
        },
    ),
]

ROLE_ALIASES = {
    "payment_context": {
        "banking",
        "buying",
        "cash",
        "checkout",
        "credit",
        "debit",
        "mobile",
        "online",
        "phone",
        "retail",
        "shopping",
        "store",
        "transaction",
        "wallet",
    },
    "payment_terminal": {
        "card-machine",
        "card-reader",
        "cashier",
        "checkout",
        "chip",
        "contactless",
        "finger",
        "hand",
        "machine",
        "pin",
        "pos",
        "reader",
        "screen",
        "tap",
        "terminal",
    },
    "merchant_acquirer": {
        "buying",
        "cash-desk",
        "cashier",
        "checkout",
        "department-store",
        "gateway",
        "merchant",
        "processor",
        "retail",
        "shop",
        "store",
    },
    "payment_network": {
        "code",
        "data",
        "data-center",
        "datacenter",
        "datacentre",
        "infrastructure",
        "network",
        "rack",
        "racks",
        "routing",
        "server",
        "servers",
        "switch",
    },
    "issuer_risk_decision": {
        "analyst",
        "bank",
        "code",
        "computer",
        "dashboard",
        "data",
        "decline",
        "fraud",
        "monitor",
        "monitoring",
        "risk",
        "screen",
    },
    "authorization_hold": {
        "app",
        "banking",
        "credit",
        "debit",
        "hold",
        "mobile",
        "pending",
        "phone",
        "transaction",
    },
    "clearing_settlement": {
        "bank",
        "batch",
        "clearing",
        "financial",
        "ledger",
        "money",
        "settlement",
        "transfer",
    },
}


PAYMENT_PROFILE_TOKENS = {
    "card",
    "cards",
    "payment",
    "payments",
    "terminal",
    "merchant",
    "acquirer",
    "issuer",
    "authorization",
    "settlement",
    "clearing",
}


def detect_role_profile(script_data: dict) -> str:
    script = script_data.get("script", script_data)
    text_parts = []

    for key in ("hook", "introduction", "conclusion"):
        value = script.get(key, {})
        if isinstance(value, dict):
            text_parts.append(str(value.get("narration", "")))

    for section in script.get("main_sections", []):
        text_parts.extend([
            str(section.get("title", "")),
            str(section.get("narration", "")),
            str(section.get("visual_direction", "")),
        ])

    tokens = set(
        normalize_text(" ".join(text_parts)).split("-")
    )
    payment_matches = tokens.intersection(PAYMENT_PROFILE_TOKENS)

    return "payment" if len(payment_matches) >= 3 else "generic"


def load_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(
            f"Required file not found: {path}"
        )

    return json.loads(
        path.read_text(encoding="utf-8-sig")
    )


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    path.write_text(
        json.dumps(
            data,
            indent=2,
            ensure_ascii=True,
        ),
        encoding="utf-8",
    )


def relative_path(path: Path) -> str:
    resolved_path = path.resolve()
    resolved_root = PROJECT_ROOT.resolve()

    try:
        relative = resolved_path.relative_to(
            resolved_root
        )
    except ValueError as exc:
        raise ValueError(
            "Stock source must be inside the repository."
        ) from exc

    return str(relative).replace("\\", "/")


def validate_video_id(video_id: str) -> str:
    normalized = video_id.lower()

    if not re.fullmatch(
        r"video_\d{3,}",
        normalized,
    ):
        raise ValueError(
            "video_id must use format video_004."
        )

    return normalized


def get_storyblocks_id(
    filename: str,
) -> str | None:
    match = re.search(
        r"SBV-\d+",
        filename,
        flags=re.IGNORECASE,
    )

    if not match:
        return None

    return match.group(0).upper()


def get_explicit_role_hint(
    filename: str,
) -> str | None:
    match = re.search(
        r"mecoria-role-([a-z0-9_]+?)__",
        filename,
        flags=re.IGNORECASE,
    )

    if not match:
        return None

    return match.group(1).lower()


def normalize_text(value: str) -> str:
    value = value.lower()
    value = value.replace("&", " and ")
    value = re.sub(
        r"[^a-z0-9]+",
        "-",
        value,
    )
    value = re.sub(
        r"-+",
        "-",
        value,
    )
    return value.strip("-")


def tokenize(value: str) -> set[str]:
    normalized = normalize_text(value)

    tokens = {
        token
        for token in normalized.split("-")
        if len(token) >= 3
        and token not in GENERIC_STOPWORDS
        and not token.isdigit()
    }

    return tokens


def slugify(value: str) -> str:
    normalized = normalize_text(value)
    return normalized.replace("-", "_")[:60] or "stock_role"


def canonical_role_id(text: str) -> str:
    tokens = tokenize(text)

    for role_id, keywords in CANONICAL_ROLE_RULES:
        normalized_keywords = {
            normalize_text(keyword)
            for keyword in keywords
        }

        if tokens.intersection(
            normalized_keywords
        ):
            return role_id

    return slugify(text)


def role_priority(
    role_id: str,
) -> int:
    order = [
        "payment_context",
        "payment_terminal",
        "merchant_acquirer",
        "payment_network",
        "issuer_risk_decision",
        "authorization_hold",
        "clearing_settlement",
    ]

    try:
        return order.index(role_id) + 1
    except ValueError:
        return len(order) + 1


def merge_role(
    catalog: dict[str, dict],
    role_id: str,
    title: str,
    text: str,
    usage_priority: int | None = None,
) -> None:
    role = catalog.setdefault(
        role_id,
        {
            "role_id": role_id,
            "title": title,
            "keywords": set(),
            "priority_keywords": set(
                ROLE_ALIASES.get(
                    role_id,
                    set(),
                )
            ),
            "usage_priority": (
                int(usage_priority)
                if usage_priority is not None
                else role_priority(role_id)
            ),
        },
    )

    role["keywords"].update(
        tokenize(text)
    )


def build_role_catalog(
    script_data: dict,
    visual_plan_data: dict | None = None,
) -> list[dict]:
    script = script_data.get(
        "script",
        script_data,
    )
    profile = detect_role_profile(script_data)
    catalog: dict[str, dict] = {}

    intro_text = " ".join([
        str(
            script.get(
                "hook",
                {},
            ).get(
                "narration",
                "",
            )
        ),
        str(
            script.get(
                "introduction",
                {},
            ).get(
                "narration",
                "",
            )
        ),
    ])

    intro_role_id = (
        "payment_context"
        if profile == "payment"
        else "topic_context"
    )
    intro_title = (
        "Payment Context"
        if profile == "payment"
        else "Topic Context"
    )

    merge_role(
        catalog=catalog,
        role_id=intro_role_id,
        title=intro_title,
        text=intro_text,
        usage_priority=1,
    )

    for index, section in enumerate(
        script.get("main_sections", []),
        start=2,
    ):
        title = str(
            section.get(
                "title",
                "Topic Support",
            )
        ).strip()

        text = " ".join([
            title,
            str(
                section.get(
                    "visual_direction",
                    "",
                )
            ),
            str(
                section.get(
                    "narration",
                    "",
                )
            ),
        ])

        if profile == "payment":
            role_id = canonical_role_id(title)
            if role_id == slugify(title):
                role_id = canonical_role_id(text)
        else:
            role_id = slugify(title)

        merge_role(
            catalog=catalog,
            role_id=role_id,
            title=title,
            text=text,
            usage_priority=index,
        )

    if visual_plan_data:
        plan = visual_plan_data.get(
            "ai_visual_insert_plan",
            visual_plan_data,
        )

        for item in plan.get(
            "items",
            [],
        ):
            text = " ".join([
                str(
                    item.get(
                        "section_hint",
                        "",
                    )
                ),
                str(
                    item.get(
                        "visual_role",
                        "",
                    )
                ),
                str(
                    item.get(
                        "prompt",
                        "",
                    )
                ),
            ])

            section_hint = str(
                item.get(
                    "section_hint",
                    "",
                )
            ).strip()

            if not section_hint:
                continue

            if profile == "payment":
                role_id = canonical_role_id(section_hint)
                if role_id == slugify(section_hint):
                    role_id = canonical_role_id(text)
            else:
                role_id = slugify(section_hint)

            merge_role(
                catalog=catalog,
                role_id=role_id,
                title=section_hint,
                text=text,
            )

    output = []

    for role in sorted(
        catalog.values(),
        key=lambda item: (
            item["usage_priority"],
            item["role_id"],
        ),
    ):
        output.append({
            "role_id": role["role_id"],
            "title": role["title"],
            "keywords": sorted(
                role["keywords"]
            ),
            "priority_keywords": sorted(
                role["priority_keywords"]
            ),
            "usage_priority": role[
                "usage_priority"
            ],
            "profile": profile,
        })

    return output


def score_role(
    filename: str,
    role: dict,
) -> dict:
    normalized_filename = normalize_text(
        Path(filename).stem
    )
    filename_tokens = tokenize(
        normalized_filename
    )

    priority_keywords = set()

    for keyword in role.get(
        "priority_keywords",
        [],
    ):
        priority_keywords.update(
            tokenize(keyword)
        )

    context_keywords = set()

    for keyword in role.get(
        "keywords",
        [],
    ):
        context_keywords.update(
            tokenize(keyword)
        )

    matched_priority = sorted(
        filename_tokens.intersection(
            priority_keywords
        )
    )
    matched_context = sorted(
        filename_tokens.intersection(
            context_keywords
        )
    )

    score = (
        len(matched_priority) * 4
        + len(matched_context)
    )

    role_phrase = normalize_text(
        role.get(
            "title",
            "",
        )
    )

    if (
        role_phrase
        and role_phrase in normalized_filename
    ):
        score += 5

    return {
        "role_id": role["role_id"],
        "role_title": role["title"],
        "usage_priority": role[
            "usage_priority"
        ],
        "score": score,
        "matched_keywords": sorted(
            set(
                matched_priority
                + matched_context
            )
        ),
    }


def strip_bridge_role_prefix(filename: str) -> str:
    match = re.match(
        r"^mecoria-role-[a-z0-9_]+__\d+__(.+)$",
        filename,
        flags=re.IGNORECASE,
    )
    return match.group(1) if match else filename


def classify_file(
    filename: str,
    role_catalog: list[dict],
) -> dict:
    if not role_catalog:
        raise ValueError(
            "Role catalog cannot be empty."
        )

    explicit_role = get_explicit_role_hint(
        filename
    )

    if explicit_role:
        matching_role = next(
            (
                role
                for role in role_catalog
                if str(
                    role.get("role_id", "")
                ).lower() == explicit_role
            ),
            None,
        )

        if matching_role is None:
            return {
                "role": "needs_manual_review",
                "role_title": "Needs Manual Review",
                "usage_priority": 99,
                "classification_score": 0,
                "classification_confidence": "low",
                "matched_keywords": [],
                "status": "review_required",
                "risk_level": "medium",
                "notes": (
                    "Storyblocks Bridge role prefix does not "
                    "match the video-specific role catalog."
                ),
            }

        original_filename = strip_bridge_role_prefix(
            filename
        )
        evidence = score_role(
            filename=original_filename,
            role=matching_role,
        )
        score = int(evidence["score"])

        if score <= 0:
            return {
                "role": "needs_manual_review",
                "role_title": "Needs Manual Review",
                "usage_priority": 99,
                "classification_score": score,
                "classification_confidence": "low",
                "matched_keywords": [],
                "status": "review_required",
                "risk_level": "medium",
                "notes": (
                    "The role prefix is routing metadata only; "
                    "the original filename contains no evidence "
                    "for the assigned visual role."
                ),
            }

        confidence = "high" if score >= 4 else "medium"

        return {
            "role": matching_role["role_id"],
            "role_title": matching_role["title"],
            "usage_priority": matching_role["usage_priority"],
            "classification_score": score,
            "classification_confidence": confidence,
            "matched_keywords": sorted(
                set(
                    evidence["matched_keywords"]
                    + ["mecoria_explicit_role_hint"]
                )
            ),
            "status": "approved_pending_stock_qa",
            "risk_level": "low",
            "notes": (
                "Role prefix matched the locked catalog and "
                "the original filename supplied relevance evidence."
            ),
        }

    ranked = sorted(
        (
            score_role(
                filename=filename,
                role=role,
            )
            for role in role_catalog
        ),
        key=lambda item: (
            -item["score"],
            item["usage_priority"],
            item["role_id"],
        ),
    )

    best = ranked[0]
    score = best["score"]

    if score >= 12:
        confidence = "high"
    elif score >= 4:
        confidence = "medium"
    else:
        confidence = "low"

    if confidence == "low":
        return {
            "role": "needs_manual_review",
            "role_title": "Needs Manual Review",
            "usage_priority": 99,
            "classification_score": score,
            "classification_confidence": confidence,
            "matched_keywords": best[
                "matched_keywords"
            ],
            "status": "review_required",
            "risk_level": "medium",
            "notes": (
                "The filename did not match the "
                "video-specific role catalog strongly enough."
            ),
        }

    risk_level = (
        "medium"
        if any(
            keyword
            in normalize_text(filename)
            for keyword in {
                "screen",
                "computer",
                "phone",
                "app",
                "banking",
                "card",
            }
        )
        else "low"
    )

    return {
        "role": best["role_id"],
        "role_title": best["role_title"],
        "usage_priority": best[
            "usage_priority"
        ],
        "classification_score": score,
        "classification_confidence": confidence,
        "matched_keywords": best[
            "matched_keywords"
        ],
        "status": "approved_pending_stock_qa",
        "risk_level": risk_level,
        "notes": (
            "Auto-classified against the locked "
            "video script and visual plan."
        ),
    }


def find_source_videos(
    source_dir: Path,
) -> list[Path]:
    if not source_dir.exists():
        raise FileNotFoundError(
            f"Source folder not found: {source_dir}"
        )

    files = [
        path
        for path in source_dir.rglob("*")
        if path.is_file()
        and path.suffix.lower()
        in VIDEO_EXTENSIONS
    ]

    return sorted(
        files,
        key=lambda path: path.name.lower(),
    )


def load_optional_visual_plan(
    context: dict,
) -> dict | None:
    if "visual_plan" not in context.get(
        "outputs",
        {},
    ):
        return None

    try:
        return load_json(
            resolve_output(
                context=context,
                key="visual_plan",
            )
        )
    except FileNotFoundError:
        return None


def registered_hash_owners() -> dict[str, set[tuple[str, str]]]:
    registry = load_registry()
    owners: dict[
        str,
        set[tuple[str, str]],
    ] = {}

    for asset_hash, asset in registry.get(
        "assets",
        {},
    ).items():
        for usage in asset.get(
            "usages",
            [],
        ):
            owners.setdefault(
                asset_hash,
                set(),
            ).add((
                str(
                    usage.get(
                        "channel",
                        "",
                    )
                ).lower(),
                str(
                    usage.get(
                        "video_id",
                        "",
                    )
                ).lower(),
            ))

    return owners


def build_manifest(
    context: dict,
    source_dir: Path,
    role_catalog: list[dict],
    source_name: str,
    license_status: str,
) -> dict:
    source_files = find_source_videos(
        source_dir
    )

    if not source_files:
        raise ValueError(
            "Stock source folder contains no video files."
        )

    owners = registered_hash_owners()
    seen_hashes: set[str] = set()
    seen_storyblocks_ids: set[str] = set()

    items = []
    skipped_items = []

    for index, source_path in enumerate(
        source_files,
        start=1,
    ):
        reference = relative_path(
            source_path
        )
        storyblocks_id = get_storyblocks_id(
            source_path.name
        )
        sha256 = calculate_sha256(
            source_path
        )

        if sha256 in seen_hashes:
            skipped_items.append({
                "source_filename": source_path.name,
                "relative_path": reference,
                "reason": "duplicate_hash_inside_source_folder",
            })
            continue

        if (
            storyblocks_id
            and storyblocks_id
            in seen_storyblocks_ids
        ):
            skipped_items.append({
                "source_filename": source_path.name,
                "relative_path": reference,
                "storyblocks_id": storyblocks_id,
                "reason": (
                    "duplicate_storyblocks_id_inside_source_folder"
                ),
            })
            continue

        foreign_owners = {
            owner
            for owner in owners.get(
                sha256,
                set(),
            )
            if owner != (
                context["channel"],
                context["video_id"],
            )
        }

        if foreign_owners:
            skipped_items.append({
                "source_filename": source_path.name,
                "relative_path": reference,
                "sha256": sha256,
                "reason": "cross_video_asset_reuse_blocked",
                "existing_owners": [
                    f"{channel}/{video_id}"
                    for channel, video_id
                    in sorted(
                        foreign_owners
                    )
                ],
            })
            continue

        classification = classify_file(
            filename=source_path.name,
            role_catalog=role_catalog,
        )

        candidate_id = (
            f"{context['video_id'].upper()}"
            f"-C{len(items) + 1:03d}"
        )

        items.append({
            "asset_id": (
                f"STOCK-{len(items) + 1:03d}"
            ),
            "candidate_id": candidate_id,
            "channel": context["channel"],
            "video_id": context["video_id"],
            "run_id": context["run_id"],
            "filename": source_path.name,
            "source_filename": source_path.name,
            "storyblocks_id": storyblocks_id,
            "relative_path": reference,
            "sha256": sha256,
            "size_bytes": source_path.stat().st_size,
            "source": source_name,
            "license_status": license_status,
            **classification,
        })

        seen_hashes.add(
            sha256
        )

        if storyblocks_id:
            seen_storyblocks_ids.add(
                storyblocks_id
            )

    if not items:
        raise ValueError(
            "No usable stock files remain after duplicate checks."
        )

    approved_count = sum(
        1
        for item in items
        if str(
            item.get(
                "status",
                "",
            )
        ).startswith("approved")
    )
    review_count = len(items) - approved_count
    role_count = len({
        item["role"]
        for item in items
        if str(
            item.get(
                "status",
                "",
            )
        ).startswith("approved")
    })

    return {
        "record_type": "video_stock_source_manifest",
        "version": "2.0",
        "channel": context["channel"],
        "video_id": context["video_id"],
        "run_id": context["run_id"],
        "video_number": int(
            context["video_id"].split(
                "_"
            )[-1]
        ),
        "status": "approved_source_ready",
        "topic": context["topic_title"],
        "source": source_name,
        "license_status": license_status,
        "source_folder": relative_path(
            source_dir
        ),
        "role_catalog": role_catalog,
        "summary": {
            "source_video_count": len(
                source_files
            ),
            "manifest_item_count": len(items),
            "approved_item_count": approved_count,
            "review_required_count": review_count,
            "skipped_count": len(
                skipped_items
            ),
            "distinct_role_count": role_count,
        },
        "items": items,
        "skipped_items": skipped_items,
        "created_at": utc_now(),
    }


def attach_manifest_to_context(
    context: dict,
    manifest_path: Path,
) -> dict:
    reference = relative_path(
        manifest_path
    )

    context.setdefault(
        "sources",
        {},
    )["stock_manifest"] = reference

    context.setdefault(
        "history",
        [],
    ).append({
        "agent": "stock_asset_ingest",
        "status": "stock_manifest_attached",
        "output_reference": reference,
        "recorded_at": utc_now(),
    })

    context["next_agent"] = "video_stock_pipeline"

    return context


def print_summary(
    manifest: dict,
    dry_run: bool,
) -> None:
    summary = manifest["summary"]

    print(
        f"VIDEO_CONTEXT_ID: "
        f"{manifest['video_id']}"
    )
    print(
        f"RUN_ID: {manifest['run_id']}"
    )
    print(
        "CLASSIFICATION_MODE: "
        "video_context"
    )
    print(
        f"SOURCE_VIDEOS: "
        f"{summary['source_video_count']}"
    )
    print(
        f"APPROVED_ITEMS: "
        f"{summary['approved_item_count']}"
    )
    print(
        f"REVIEW_REQUIRED: "
        f"{summary['review_required_count']}"
    )
    print(
        f"SKIPPED_ITEMS: "
        f"{summary['skipped_count']}"
    )
    print(
        f"DISTINCT_ROLES: "
        f"{summary['distinct_role_count']}"
    )

    print("CLASSIFIED_ITEMS:")

    for item in manifest["items"]:
        print(
            f"- {item['candidate_id']} | "
            f"{item['role']} | "
            f"{item['classification_confidence']} | "
            f"{item['source_filename']}"
        )

    if manifest["skipped_items"]:
        print("SKIPPED_ITEMS_DETAIL:")

        for item in manifest[
            "skipped_items"
        ]:
            print(
                f"- {item['source_filename']} | "
                f"{item['reason']}"
            )

    print(
        "STATUS: "
        + (
            "video_stock_ingest_dry_run_ready"
            if dry_run
            else "video_stock_manifest_attached"
        )
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create and attach a video-specific "
            "stock footage source manifest."
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
        "--source",
        required=True,
        help=(
            "Repo-relative folder containing "
            "stock video files."
        ),
    )
    parser.add_argument(
        "--source-name",
        default="storyblocks",
    )
    parser.add_argument(
        "--license-status",
        default=(
            "public_use_confirmation_required"
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    channel = args.channel.lower()
    video_id = validate_video_id(
        args.video_id
    )

    source_dir = Path(
        args.source
    )

    if not source_dir.is_absolute():
        source_dir = (
            PROJECT_ROOT
            / source_dir
        )

    source_dir = source_dir.resolve()
    relative_path(
        source_dir
    )

    context = load_context(
        channel=channel,
        video_id=video_id,
    )

    script_data = load_json(
        resolve_output(
            context=context,
            key="script",
        )
    )
    visual_plan_data = (
        load_optional_visual_plan(
            context
        )
    )

    role_catalog = build_role_catalog(
        script_data=script_data,
        visual_plan_data=visual_plan_data,
    )

    manifest = build_manifest(
        context=context,
        source_dir=source_dir,
        role_catalog=role_catalog,
        source_name=args.source_name,
        license_status=args.license_status,
    )

    print_summary(
        manifest=manifest,
        dry_run=args.dry_run,
    )

    if args.dry_run:
        return

    output_dir = (
        PROJECT_ROOT
        / "records"
        / "run_contexts"
        / channel
        / video_id
        / "inputs"
    )

    manifest_path = (
        output_dir
        / "stock_source_manifest.json"
    )
    ingest_path = (
        output_dir
        / "stock_ingest.json"
    )

    save_json(
        manifest_path,
        manifest,
    )
    save_json(
        ingest_path,
        {
            "agent": "stock_asset_ingest",
            "version": "2.0",
            "channel": channel,
            "video_id": video_id,
            "run_id": context["run_id"],
            "status": (
                "stock_manifest_attached"
            ),
            "manifest_reference": relative_path(
                manifest_path
            ),
            "summary": manifest[
                "summary"
            ],
            "created_at": utc_now(),
        },
    )

    context = attach_manifest_to_context(
        context=context,
        manifest_path=manifest_path,
    )
    save_context(
        context
    )

    print(
        "STOCK_SOURCE_MANIFEST: "
        f"{relative_path(manifest_path)}"
    )
    print(
        "CONTEXT_SOURCE_ATTACHED: true"
    )


if __name__ == "__main__":
    main()
