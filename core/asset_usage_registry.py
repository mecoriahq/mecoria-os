import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REGISTRY_PATH = (
    PROJECT_ROOT
    / "records"
    / "assets"
    / "asset_usage_registry.json"
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_registry(
    registry_path: Path = DEFAULT_REGISTRY_PATH
) -> dict:
    if not registry_path.exists():
        return {
            "schema_version": "1.0",
            "updated_at": utc_now(),
            "assets": {}
        }

    return json.loads(
        registry_path.read_text(encoding="utf-8-sig")
    )


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


def calculate_sha256(path: Path) -> str:
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(
            f"Asset file not found: {path}"
        )

    digest = hashlib.sha256()

    with path.open("rb") as file:
        while True:
            chunk = file.read(1024 * 1024)

            if not chunk:
                break

            digest.update(chunk)

    return digest.hexdigest()


def normalize_reference(
    path: Path,
    project_root: Path = PROJECT_ROOT
) -> str:
    resolved_path = path.resolve()
    resolved_root = project_root.resolve()

    try:
        relative = resolved_path.relative_to(
            resolved_root
        )
    except ValueError as exc:
        raise ValueError(
            "Asset must be inside the repository."
        ) from exc

    return str(relative).replace("\\", "/")


def build_asset_record(
    path: Path,
    asset_type: str,
    channel: str,
    video_id: str,
    run_id: str,
    shared_brand_asset: bool = False,
    project_root: Path = PROJECT_ROOT
) -> dict:
    return {
        "sha256": calculate_sha256(path),
        "size_bytes": path.stat().st_size,
        "asset_type": asset_type,
        "channel": channel.lower(),
        "video_id": video_id.lower(),
        "run_id": run_id,
        "relative_path": normalize_reference(
            path,
            project_root=project_root
        ),
        "shared_brand_asset": shared_brand_asset
    }


def _iter_usages(registry: dict):
    for asset_hash, asset in registry.get(
        "assets",
        {}
    ).items():
        for usage in asset.get("usages", []):
            yield asset_hash, asset, usage


def validate_asset_batch(
    records: list[dict],
    registry_path: Path = DEFAULT_REGISTRY_PATH
) -> None:
    registry = load_registry(registry_path)

    batch_hashes = {}
    batch_paths = {}

    for record in records:
        asset_hash = record["sha256"]
        relative_path = record["relative_path"]
        identity = (
            record["channel"],
            record["video_id"]
        )

        existing_batch_hash = batch_hashes.get(
            asset_hash
        )

        if (
            existing_batch_hash
            and existing_batch_hash != identity
            and not record["shared_brand_asset"]
        ):
            raise ValueError(
                "Cross-video duplicate hash detected "
                "inside the asset batch."
            )

        existing_batch_path = batch_paths.get(
            relative_path
        )

        if (
            existing_batch_path
            and existing_batch_path != identity
            and not record["shared_brand_asset"]
        ):
            raise ValueError(
                "Cross-video duplicate path detected "
                "inside the asset batch."
            )

        batch_hashes[asset_hash] = identity
        batch_paths[relative_path] = identity

        for (
            registered_hash,
            registered_asset,
            usage
        ) in _iter_usages(registry):
            same_video = (
                usage["channel"] == record["channel"]
                and usage["video_id"] == record["video_id"]
            )

            shared_allowed = (
                record["shared_brand_asset"]
                and registered_asset.get(
                    "shared_brand_asset",
                    False
                )
            )

            same_hash = (
                registered_hash == asset_hash
            )
            same_path = (
                usage["relative_path"]
                == relative_path
            )

            if (
                (same_hash or same_path)
                and not same_video
                and not shared_allowed
            ):
                conflict_type = (
                    "hash"
                    if same_hash
                    else "path"
                )

                raise ValueError(
                    "Cross-video asset reuse blocked: "
                    f"{conflict_type} already belongs to "
                    f"{usage['channel']}/{usage['video_id']}."
                )


def register_asset_batch(
    records: list[dict],
    registry_path: Path = DEFAULT_REGISTRY_PATH
) -> Path:
    validate_asset_batch(
        records=records,
        registry_path=registry_path
    )

    registry = load_registry(registry_path)

    for record in records:
        asset_hash = record["sha256"]

        asset = registry["assets"].setdefault(
            asset_hash,
            {
                "sha256": asset_hash,
                "size_bytes": record["size_bytes"],
                "asset_type": record["asset_type"],
                "shared_brand_asset": record[
                    "shared_brand_asset"
                ],
                "first_registered_at": utc_now(),
                "usages": []
            }
        )

        usage = {
            "channel": record["channel"],
            "video_id": record["video_id"],
            "run_id": record["run_id"],
            "relative_path": record[
                "relative_path"
            ],
            "registered_at": utc_now()
        }

        already_registered = any(
            existing["channel"]
            == usage["channel"]
            and existing["video_id"]
            == usage["video_id"]
            and existing["run_id"]
            == usage["run_id"]
            and existing["relative_path"]
            == usage["relative_path"]
            for existing in asset["usages"]
        )

        if not already_registered:
            asset["usages"].append(usage)

    return save_registry(
        registry=registry,
        registry_path=registry_path
    )


def assert_asset_registered(
    path: Path,
    channel: str,
    video_id: str,
    expected_sha256: str | None = None,
    registry_path: Path = DEFAULT_REGISTRY_PATH,
    project_root: Path = PROJECT_ROOT
) -> None:
    registry = load_registry(registry_path)
    actual_hash = calculate_sha256(path)

    if (
        expected_sha256
        and actual_hash != expected_sha256
    ):
        raise ValueError(
            "Asset file hash does not match manifest."
        )

    asset = registry.get(
        "assets",
        {}
    ).get(actual_hash)

    if not asset:
        raise ValueError(
            "Asset is not registered."
        )

    reference = normalize_reference(
        path,
        project_root=project_root
    )

    valid_usage = any(
        usage["channel"] == channel.lower()
        and usage["video_id"] == video_id.lower()
        and usage["relative_path"] == reference
        for usage in asset.get("usages", [])
    )

    if not valid_usage:
        raise ValueError(
            "Asset registry ownership does not match "
            "the current video."
        )
