import json
import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_STANDARD_PATH = (
    PROJECT_ROOT
    / "config"
    / "media"
    / "hiddenova_thumbnail_standard.json"
)


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
        "text",
        "layout",
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

    if (
        standard["standard_name"]
        != "hiddenova_cinematic_v1"
    ):
        raise ValueError(
            "Unexpected Hiddenova thumbnail standard."
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
    standard = (
        standard
        or load_thumbnail_standard()
    )

    normalized = normalize_thumbnail_text(value)
    words = normalized.split()

    minimum = int(
        standard["text"]["min_words"]
    )
    maximum = int(
        standard["text"]["max_words"]
    )

    word_count_valid = (
        minimum <= len(words) <= maximum
    )

    uppercase_valid = (
        normalized == str(value).strip()
    )

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


def build_thumbnail_prompt(
    video_topic: str,
    main_subject: str,
    thumbnail_text: str,
    text_position: str = "auto",
    standard: dict | None = None
) -> str:
    standard = (
        standard
        or load_thumbnail_standard()
    )

    text_result = assert_thumbnail_text(
        value=thumbnail_text,
        standard=standard
    )

    forbidden = ", ".join(
        standard["forbidden_elements"]
    )

    return f"""
Create a premium cinematic YouTube documentary
thumbnail for Hiddenova.

THUMBNAIL_STANDARD:
{standard["standard_name"]}

VIDEO_TOPIC:
{video_topic}

MAIN_SUBJECT:
{main_subject}

EXACT_THUMBNAIL_TEXT:
{text_result["normalized_text"]}

TEXT_POSITION:
{text_position}

MANDATORY_STYLE:
- one dominant main subject
- dramatic cinematic documentary background
- very high contrast
- clean composition
- strong negative space for text
- huge bold ALL CAPS text
- text must occupy approximately 35 to 55 percent
  of the thumbnail
- text must be extremely readable on mobile
- use white and yellow text
- use a very strong black outline and shadow
- create mystery, tension, danger, or hidden-system
  curiosity when relevant
- premium high-CTR documentary appearance
- clarity first, beauty second

FORBIDDEN:
{forbidden}

Do not add any other text.
Do not change the exact thumbnail text.
The final result must feel immediately clickable
at mobile thumbnail size.
""".strip()



def build_thumbnail_background_prompt(
    video_topic: str,
    main_subject: str,
    thumbnail_text: str,
    text_position: str = "left",
    standard: dict | None = None
) -> str:
    standard = (
        standard
        or load_thumbnail_standard()
    )

    text_result = assert_thumbnail_text(
        value=thumbnail_text,
        standard=standard
    )

    return f"""
Create a premium cinematic YouTube documentary
thumbnail background for Hiddenova.

THUMBNAIL_STANDARD:
{standard["standard_name"]}

VIDEO_TOPIC:
{video_topic}

DOMINANT_MAIN_SUBJECT:
{main_subject}

TEXT_LAYOUT_REFERENCE_ONLY:
{text_result["normalized_text"]}

TEXT_POSITION:
{text_position}

MANDATORY_BACKGROUND_STYLE:
- one dominant main subject
- dark cinematic documentary atmosphere
- dramatic high-contrast lighting
- strong mystery and tension
- premium high-CTR composition
- clear visual storytelling
- reserve approximately 35 to 55 percent of the
  frame for a huge text block on the {text_position}
- keep the subject on the opposite side
- preserve strong negative space
- low clutter
- realistic materials and lighting
- mobile readability must be supported

CRITICAL:
- Generate the background only.
- Do not render the text.
- Do not add any other text.
- No logos.
- No watermarks.
- No UI elements.
- No unrelated objects.
""".strip()


def build_thumbnail_qa_checklist(
    thumbnail_text: str,
    standard: dict | None = None
) -> dict:
    standard = (
        standard
        or load_thumbnail_standard()
    )

    text_result = validate_thumbnail_text(
        value=thumbnail_text,
        standard=standard
    )

    automatic_checks = {
        "text_word_count_valid": (
            text_result["word_count_valid"]
        ),
        "text_is_uppercase": (
            text_result["uppercase_valid"]
        )
    }

    manual_checks = {
        key: None
        for key in standard["qa_gates"]
        if key not in automatic_checks
    }

    return {
        "standard_name": standard[
            "standard_name"
        ],
        "thumbnail_text": text_result[
            "normalized_text"
        ],
        "word_count": text_result[
            "word_count"
        ],
        "automatic_checks": automatic_checks,
        "manual_checks": manual_checks,
        "automatic_text_checks_passed": (
            text_result["approved"]
        ),
        "founder_visual_review_required": True
    }
