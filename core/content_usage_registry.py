import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REGISTRY_PATH = (
    PROJECT_ROOT
    / "records"
    / "content"
    / "content_usage_registry.json"
)

CONTENT_REFERENCES = {
    "script": "script",
    "seo": "seo",
    "thumbnail_strategy": "thumbnail_strategy",
    "visual_asset_plan": "visual_asset_plan",
    "visual_plan": "visual_plan",
}

SIMILARITY_THRESHOLDS = {
    "script": 0.90,
    "seo": 0.90,
    "thumbnail_strategy": 0.86,
    "visual_asset_plan": 0.90,
    "visual_plan": 0.88,
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(
            f"Required content file not found: {path}"
        )

    return json.loads(
        path.read_text(encoding="utf-8-sig")
    )


def load_registry(
    registry_path: Path = DEFAULT_REGISTRY_PATH
) -> dict:
    if not registry_path.exists():
        return {
            "schema_version": "1.0",
            "updated_at": utc_now(),
            "records": {}
        }

    return load_json(registry_path)


def save_registry(
    registry: dict,
    registry_path: Path = DEFAULT_REGISTRY_PATH
) -> Path:
    registry_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    registry["updated_at"] = utc_now()

    temporary_path = registry_path.with_suffix(
        registry_path.suffix + ".tmp"
    )

    temporary_path.write_text(
        json.dumps(
            registry,
            indent=2,
            ensure_ascii=True
        ),
        encoding="utf-8"
    )

    temporary_path.replace(registry_path)
    return registry_path


def flatten_values(value: Any) -> list[str]:
    if value is None:
        return []

    if isinstance(value, dict):
        parts = []

        for key in sorted(value):
            parts.extend(
                flatten_values(value[key])
            )

        return parts

    if isinstance(value, list):
        parts = []

        for item in value:
            parts.extend(flatten_values(item))

        return parts

    if isinstance(value, bool):
        return ["true" if value else "false"]

    return [str(value)]


def normalize_text(value: Any) -> str:
    raw_text = " ".join(flatten_values(value))

    raw_text = unicodedata.normalize(
        "NFKC",
        raw_text
    ).casefold()

    raw_text = re.sub(
        r"[^a-z0-9]+",
        " ",
        raw_text
    )

    return re.sub(
        r"\s+",
        " ",
        raw_text
    ).strip()


def extract_content_payload(
    record_type: str,
    data: dict
) -> Any:
    if record_type == "script":
        return data.get("script", {})

    if record_type == "seo":
        seo = data.get("seo", {})

        return {
            "video_title": seo.get("video_title"),
            "description": seo.get("description"),
            "thumbnail_text": seo.get(
                "thumbnail_text"
            ),
            "chapters": seo.get("chapters", []),
            "keywords": seo.get("keywords", []),
            "tags": seo.get("tags", []),
        }

    if record_type == "thumbnail_strategy":
        return {
            "script_title": data.get(
                "script_title"
            ),
            "seo_title": data.get("seo_title"),
            "preferred_thumbnail_text": data.get(
                "preferred_thumbnail_text"
            ),
            "backup_thumbnail_texts": data.get(
                "backup_thumbnail_texts",
                []
            ),
            "click_angle": data.get("click_angle"),
            "visual_direction": data.get(
                "visual_direction",
                {}
            ),
        }

    if record_type == "visual_asset_plan":
        return data.get("asset_plan", {})

    if record_type == "visual_plan":
        insert_plan = data.get(
            "ai_visual_insert_plan",
            {}
        )

        specific_items = []

        for item in insert_plan.get("items", []):
            specific_items.append({
                "section_hint": item.get(
                    "section_hint"
                ),
                "visual_role": item.get(
                    "visual_role"
                ),
                "prompt": item.get("prompt"),
            })

        return {
            "video_title": data.get("video_title"),
            "thumbnail": data.get(
                "thumbnail",
                {}
            ),
            "items": specific_items,
        }

    raise ValueError(
        f"Unsupported content record type: {record_type}"
    )


def build_shingles(
    normalized_text: str,
    size: int = 5
) -> set[str]:
    words = normalized_text.split()

    if not words:
        return set()

    if len(words) < size:
        return {" ".join(words)}

    return {
        " ".join(words[index:index + size])
        for index in range(
            len(words) - size + 1
        )
    }


def calculate_similarity(
    first_text: str,
    second_text: str
) -> float:
    if not first_text or not second_text:
        return 0.0

    if first_text == second_text:
        return 1.0

    sequence_score = SequenceMatcher(
        None,
        first_text,
        second_text,
        autojunk=False
    ).ratio()

    first_tokens = set(first_text.split())
    second_tokens = set(second_text.split())

    token_union = first_tokens | second_tokens

    shared_tokens = (
        first_tokens & second_tokens
    )

    token_score = (
        len(shared_tokens)
        / len(token_union)
        if token_union
        else 0.0
    )

    smaller_token_count = min(
        len(first_tokens),
        len(second_tokens)
    )

    containment_score = (
        len(shared_tokens)
        / smaller_token_count
        if smaller_token_count > 0
        else 0.0
    )

    short_text_containment_score = (
        containment_score
        if (
            smaller_token_count <= 6
            and len(shared_tokens) >= 2
        )
        else 0.0
    )

    first_shingles = build_shingles(first_text)
    second_shingles = build_shingles(second_text)

    shingle_union = (
        first_shingles | second_shingles
    )

    shingle_score = (
        len(first_shingles & second_shingles)
        / len(shingle_union)
        if shingle_union
        else 0.0
    )

    return round(
        max(
            sequence_score,
            token_score,
            shingle_score,
            short_text_containment_score
        ),
        6
    )


def build_content_record(
    record_type: str,
    payload: Any,
    channel: str,
    video_id: str,
    run_id: str,
    source_reference: str
) -> dict:
    normalized_text = normalize_text(payload)

    if not normalized_text:
        raise ValueError(
            f"Content payload is empty: {record_type}"
        )

    return {
        "record_type": record_type,
        "channel": channel.lower(),
        "video_id": video_id.lower(),
        "run_id": run_id,
        "source_reference": source_reference.replace(
            "\\",
            "/"
        ),
        "exact_sha256": hashlib.sha256(
            normalized_text.encode("utf-8")
        ).hexdigest(),
        "normalized_text": normalized_text,
        "word_count": len(
            normalized_text.split()
        ),
        "similarity_threshold": (
            SIMILARITY_THRESHOLDS[record_type]
        )
    }


def resolve_context_reference(
    context: dict,
    key: str
) -> str | None:
    if key in context.get("outputs", {}):
        return context["outputs"][key]

    return context.get("sources", {}).get(key)


def build_context_content_records(
    context: dict,
    project_root: Path = PROJECT_ROOT
) -> list[dict]:
    records = []

    for record_type, key in (
        CONTENT_REFERENCES.items()
    ):
        reference = resolve_context_reference(
            context,
            key
        )

        if not reference:
            continue

        normalized_reference = reference.replace(
            "\\",
            "/"
        ).lower()

        if normalized_reference.endswith(
            "/latest.json"
        ):
            raise ValueError(
                f"Content source cannot use latest.json: {key}"
            )

        if Path(reference).is_absolute():
            raise ValueError(
                f"Content source must be repo-relative: {key}"
            )

        path = project_root / reference
        data = load_json(path)

        payload = extract_content_payload(
            record_type=record_type,
            data=data
        )

        records.append(
            build_content_record(
                record_type=record_type,
                payload=payload,
                channel=context["channel"],
                video_id=context["video_id"],
                run_id=context["run_id"],
                source_reference=reference
            )
        )

    if not records:
        raise ValueError(
            "No fingerprintable content records found."
        )

    return records


def validate_content_batch(
    records: list[dict],
    registry_path: Path = DEFAULT_REGISTRY_PATH
) -> None:
    registry = load_registry(registry_path)

    for record in records:
        existing_records = registry.get(
            "records",
            {}
        ).get(record["record_type"], [])

        for existing in existing_records:
            same_channel = (
                existing["channel"]
                == record["channel"]
            )
            same_video = (
                existing["video_id"]
                == record["video_id"]
            )

            if not same_channel or same_video:
                continue

            if (
                existing["exact_sha256"]
                == record["exact_sha256"]
            ):
                raise ValueError(
                    "Cross-video exact content reuse blocked: "
                    f"{record['record_type']} already belongs "
                    f"to {existing['channel']}/"
                    f"{existing['video_id']}."
                )

            similarity = calculate_similarity(
                existing["normalized_text"],
                record["normalized_text"]
            )

            threshold = min(
                float(
                    existing.get(
                        "similarity_threshold",
                        1.0
                    )
                ),
                float(
                    record["similarity_threshold"]
                )
            )

            if similarity >= threshold:
                raise ValueError(
                    "Cross-video near-duplicate content "
                    "reuse blocked: "
                    f"{record['record_type']} similarity="
                    f"{similarity:.4f} threshold="
                    f"{threshold:.4f} existing_video="
                    f"{existing['video_id']}."
                )


def register_content_batch(
    records: list[dict],
    registry_path: Path = DEFAULT_REGISTRY_PATH
) -> Path:
    validate_content_batch(
        records=records,
        registry_path=registry_path
    )

    registry = load_registry(registry_path)

    for record in records:
        bucket = registry.setdefault(
            "records",
            {}
        ).setdefault(
            record["record_type"],
            []
        )

        already_registered = any(
            existing["channel"]
            == record["channel"]
            and existing["video_id"]
            == record["video_id"]
            and existing["run_id"]
            == record["run_id"]
            and existing["exact_sha256"]
            == record["exact_sha256"]
            and existing["source_reference"]
            == record["source_reference"]
            for existing in bucket
        )

        if already_registered:
            continue

        saved_record = dict(record)
        saved_record["registered_at"] = utc_now()

        bucket.append(saved_record)

    return save_registry(
        registry=registry,
        registry_path=registry_path
    )



def remove_video_content_records(
    channel: str,
    video_id: str,
    record_types: list[str] | None = None,
    registry_path: Path = DEFAULT_REGISTRY_PATH
) -> int:
    registry = load_registry(registry_path)
    requested_types = (
        set(record_types)
        if record_types
        else None
    )

    removed_count = 0

    for record_type, bucket in list(
        registry.get("records", {}).items()
    ):
        if (
            requested_types is not None
            and record_type not in requested_types
        ):
            continue

        retained = []

        for record in bucket:
            same_video = (
                record.get("channel") == channel.lower()
                and record.get("video_id")
                == video_id.lower()
            )

            if same_video:
                removed_count += 1
            else:
                retained.append(record)

        registry["records"][record_type] = retained

    if removed_count:
        save_registry(
            registry=registry,
            registry_path=registry_path
        )

    return removed_count


def assert_content_batch_registered(
    records: list[dict],
    registry_path: Path = DEFAULT_REGISTRY_PATH
) -> None:
    registry = load_registry(registry_path)

    for record in records:
        bucket = registry.get(
            "records",
            {}
        ).get(record["record_type"], [])

        registered = any(
            existing["channel"]
            == record["channel"]
            and existing["video_id"]
            == record["video_id"]
            and existing["run_id"]
            == record["run_id"]
            and existing["exact_sha256"]
            == record["exact_sha256"]
            and existing["source_reference"]
            == record["source_reference"]
            for existing in bucket
        )

        if not registered:
            raise ValueError(
                "Content fingerprint is not registered: "
                f"{record['record_type']}."
            )


def register_context_content(
    context: dict,
    project_root: Path = PROJECT_ROOT,
    registry_path: Path = DEFAULT_REGISTRY_PATH
) -> dict:
    records = build_context_content_records(
        context=context,
        project_root=project_root
    )

    path = register_content_batch(
        records=records,
        registry_path=registry_path
    )

    return {
        "record_count": len(records),
        "registry_path": path,
        "status": "registered"
    }


def assert_context_content_registered(
    context: dict,
    project_root: Path = PROJECT_ROOT,
    registry_path: Path = DEFAULT_REGISTRY_PATH
) -> dict:
    records = build_context_content_records(
        context=context,
        project_root=project_root
    )

    assert_content_batch_registered(
        records=records,
        registry_path=registry_path
    )

    return {
        "record_count": len(records),
        "status": "passed"
    }
