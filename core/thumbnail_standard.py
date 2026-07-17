import hashlib
import json
import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXPECTED_STANDARD_NAME = "hiddenova_cinematic_v2"
DEFAULT_STANDARD_PATH = (
    PROJECT_ROOT
    / "config"
    / "media"
    / "hiddenova_thumbnail_standard.json"
)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def resolve_gold_reference_path(
    standard: dict | None = None
) -> Path:
    standard = standard or load_thumbnail_standard()
    reference = Path(standard["gold_reference"]["asset_path"])

    if not reference.is_absolute():
        reference = PROJECT_ROOT / reference

    return reference


def load_thumbnail_standard(
    path: Path = DEFAULT_STANDARD_PATH
) -> dict:
    if not path.exists():
        raise FileNotFoundError(
            f"Thumbnail standard not found: {path}"
        )

    standard = json.loads(
        path.read_text(encoding="utf-8-sig")
    )

    required_fields = {
        "standard_name",
        "version",
        "channel",
        "gold_reference",
        "text",
        "layout",
        "overlay",
        "visual_tone",
        "forbidden_elements",
        "qa_gates",
    }

    missing = required_fields - set(standard)

    if missing:
        raise ValueError(
            "Thumbnail standard is missing fields: "
            + ", ".join(sorted(missing))
        )

    if standard["standard_name"] != EXPECTED_STANDARD_NAME:
        raise ValueError(
            "Unexpected Hiddenova thumbnail standard."
        )

    gold = standard["gold_reference"]
    gold_required = {
        "asset_path",
        "sha256",
        "approved_text",
        "layout_signature",
    }
    gold_missing = gold_required - set(gold)

    if gold_missing:
        raise ValueError(
            "Gold reference is missing fields: "
            + ", ".join(sorted(gold_missing))
        )

    reference_path = resolve_gold_reference_path(standard)

    if not reference_path.exists():
        raise FileNotFoundError(
            f"Thumbnail gold reference not found: {reference_path}"
        )

    actual_sha = file_sha256(reference_path)

    if actual_sha != str(gold["sha256"]):
        raise ValueError(
            "Thumbnail gold reference SHA-256 mismatch."
        )

    layout_signature = standard["layout"].get(
        "layout_signature"
    )

    if layout_signature != gold["layout_signature"]:
        raise ValueError(
            "Thumbnail layout signature does not match gold reference."
        )

    return standard


def normalize_thumbnail_text(value: str) -> str:
    words = re.findall(
        r"[A-Za-z0-9]+",
        str(value)
    )

    return " ".join(words).upper()


def validate_thumbnail_text(
    value: str,
    standard: dict | None = None
) -> dict:
    standard = standard or load_thumbnail_standard()
    normalized = normalize_thumbnail_text(value)
    words = normalized.split()
    minimum = int(standard["text"]["min_words"])
    maximum = int(standard["text"]["max_words"])
    word_count_valid = minimum <= len(words) <= maximum
    uppercase_valid = normalized == str(value).strip()
    approved = (
        bool(normalized)
        and word_count_valid
        and uppercase_valid
    )

    return {
        "original_text": str(value),
        "normalized_text": normalized,
        "word_count": len(words),
        "minimum_words": minimum,
        "maximum_words": maximum,
        "word_count_valid": word_count_valid,
        "uppercase_valid": uppercase_valid,
        "approved": approved,
    }


def assert_thumbnail_text(
    value: str,
    standard: dict | None = None
) -> dict:
    result = validate_thumbnail_text(
        value=value,
        standard=standard
    )

    if not result["approved"]:
        raise ValueError(
            "Thumbnail text failed Hiddenova standard: "
            f"text={result['original_text']} "
            f"word_count={result['word_count']} "
            f"required={result['minimum_words']}-"
            f"{result['maximum_words']} "
            f"uppercase={result['uppercase_valid']}."
        )

    return result


def build_thumbnail_lines(
    value: str,
    standard: dict | None = None
) -> list[dict]:
    standard = standard or load_thumbnail_standard()
    result = assert_thumbnail_text(value, standard)
    words = result["normalized_text"].split()

    if len(words) == 2:
        line_texts = [words[0], words[1]]
    elif len(words) == 3:
        line_texts = words
    else:
        line_texts = [" ".join(words[:2]), words[2], words[3]]

    lines = []

    for index, text in enumerate(line_texts):
        color_role = (
            "highlight_yellow"
            if index == len(line_texts) - 1
            else "primary_white"
        )
        lines.append({
            "text": text,
            "color_role": color_role,
        })

    return lines


def build_thumbnail_overlay_spec(
    standard: dict | None = None
) -> dict:
    standard = standard or load_thumbnail_standard()
    overlay = dict(standard["overlay"])
    overlay.update({
        "standard_name": standard["standard_name"],
        "layout_signature": standard["layout"][
            "layout_signature"
        ],
        "text_position": standard["layout"]["text_position"],
        "subject_position": standard["layout"][
            "subject_position"
        ],
        "gold_reference_path": standard["gold_reference"][
            "asset_path"
        ],
        "gold_reference_sha256": standard["gold_reference"][
            "sha256"
        ],
    })
    return overlay


def build_thumbnail_prompt(
    video_topic: str,
    main_subject: str,
    thumbnail_text: str,
    text_position: str = "left",
    standard: dict | None = None
) -> str:
    standard = standard or load_thumbnail_standard()
    text_result = assert_thumbnail_text(thumbnail_text, standard)
    forbidden = ", ".join(standard["forbidden_elements"])
    signature = standard["layout"]["layout_signature"]

    return f"""
Create a premium cinematic YouTube documentary thumbnail for Hiddenova.

THUMBNAIL_STANDARD:
{standard["standard_name"]}

GOLD_REFERENCE_LAYOUT_SIGNATURE:
{signature}

VIDEO_TOPIC:
{video_topic}

MAIN_SUBJECT:
{main_subject}

EXACT_THUMBNAIL_TEXT:
{text_result["normalized_text"]}

NON_NEGOTIABLE_HOUSE_STYLE:
- match the approved TWO SECOND VERDICT series structure
- oversized stacked ALL CAPS headline on the left
- one dominant topic-specific subject on the right
- white headline lines with the final emphasis line in bright yellow
- bold condensed sans-serif appearance
- thick black outline and deep black shadow
- dark blue cinematic high-contrast background
- strong rim lighting, energy, depth, and visual tension
- clean premium documentary composition
- subject must remain instantly recognizable on mobile
- headline must dominate approximately 40 to 52 percent of the frame
- style consistency must be exact while the subject changes by topic

FORBIDDEN:
{forbidden}

Do not add any other text.
Do not change the exact thumbnail text.
Do not copy the payment-terminal subject from the gold reference unless it matches the video topic.
""".strip()


def build_thumbnail_background_prompt(
    video_topic: str,
    main_subject: str,
    thumbnail_text: str,
    text_position: str = "left",
    standard: dict | None = None
) -> str:
    standard = standard or load_thumbnail_standard()
    text_result = assert_thumbnail_text(thumbnail_text, standard)
    layout = standard["layout"]
    visual = standard["visual_tone"]

    return f"""
Create a premium cinematic YouTube documentary thumbnail background for Hiddenova.

THUMBNAIL_STANDARD:
{standard["standard_name"]}

GOLD_REFERENCE:
Use the approved TWO SECOND VERDICT thumbnail as the exact style and layout reference. Reproduce its composition discipline, emotional intensity, lighting hierarchy, depth, and mobile readability. Do not reproduce its payment-terminal subject unless the current topic requires it.

VIDEO_TOPIC:
{video_topic}

DOMINANT_MAIN_SUBJECT:
{main_subject}

TEXT_LAYOUT_REFERENCE_ONLY:
{text_result["normalized_text"]}

LOCKED_COMPOSITION:
- layout signature: {layout["layout_signature"]}
- reserve the left {int(float(layout["text_area_ratio_max"]) * 100)} percent for a huge stacked headline
- place one dominant subject on the right or center-right
- keep the left headline zone dark, simple, and high contrast
- create a clear visual path from headline to subject
- no collage and no competing secondary subject

MANDATORY_BACKGROUND_STYLE:
- dark navy and electric blue cinematic palette
- dramatic high-contrast lighting and bright focal glow
- premium documentary realism
- urgent high-curiosity atmosphere
- strong depth, particles, light trails, or subtle network energy only when topic-relevant
- realistic materials and lighting
- mobile-first clarity
- visual tone: {visual["tone"]}

CRITICAL:
- Generate the background only.
- Do not render any text.
- No logos.
- No watermarks.
- No readable UI labels.
- No unrelated objects.
- No generic stock-poster layout.
""".strip()


def build_thumbnail_qa_checklist(
    thumbnail_text: str,
    standard: dict | None = None
) -> dict:
    standard = standard or load_thumbnail_standard()
    text_result = validate_thumbnail_text(thumbnail_text, standard)
    reference_path = resolve_gold_reference_path(standard)
    reference_sha_valid = (
        reference_path.exists()
        and file_sha256(reference_path)
        == standard["gold_reference"]["sha256"]
    )

    automatic_checks = {
        "text_word_count_valid": text_result["word_count_valid"],
        "text_is_uppercase": text_result["uppercase_valid"],
        "standard_is_hiddenova_cinematic_v2": (
            standard["standard_name"] == EXPECTED_STANDARD_NAME
        ),
        "gold_reference_traceable": reference_sha_valid,
        "text_position_locked_left": (
            standard["layout"]["text_position"] == "left"
        ),
        "subject_position_locked_right": (
            standard["layout"]["subject_position"]
            in {"right", "center_right"}
        ),
        "two_color_emphasis_required": (
            standard["text"]["two_color_required"] is True
        ),
    }

    manual_checks = {
        key: None
        for key in standard["qa_gates"]
        if key not in automatic_checks
    }

    return {
        "standard_name": standard["standard_name"],
        "layout_signature": standard["layout"][
            "layout_signature"
        ],
        "gold_reference": {
            "asset_path": standard["gold_reference"]["asset_path"],
            "sha256": standard["gold_reference"]["sha256"],
        },
        "thumbnail_text": text_result["normalized_text"],
        "word_count": text_result["word_count"],
        "automatic_checks": automatic_checks,
        "manual_checks": manual_checks,
        "automatic_text_checks_passed": (
            text_result["approved"]
            and all(automatic_checks.values())
        ),
        "founder_visual_review_required": True,
    }
