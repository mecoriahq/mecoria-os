import hashlib
import json
import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXPECTED_STANDARD_NAME = "hiddenova_cinematic_v3"
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
        "concept_system",
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

    concept_system = standard["concept_system"]
    required_concept_fields = {
        "candidate_count",
        "finalist_count",
        "required_concept_types",
        "minimum_preflight_score",
        "minimum_vision_score",
        "minimum_final_score",
    }
    concept_missing = (
        required_concept_fields
        - set(concept_system)
    )

    if concept_missing:
        raise ValueError(
            "Thumbnail concept system is missing fields: "
            + ", ".join(sorted(concept_missing))
        )

    candidate_count = int(
        concept_system["candidate_count"]
    )
    finalist_count = int(
        concept_system["finalist_count"]
    )
    required_types = concept_system[
        "required_concept_types"
    ]

    if candidate_count != 3:
        raise ValueError(
            "Hiddenova thumbnail v3 requires exactly 3 concepts."
        )

    if not 1 <= finalist_count < candidate_count:
        raise ValueError(
            "Thumbnail finalist count must be below candidate count."
        )

    if (
        not isinstance(required_types, list)
        or len(required_types) != candidate_count
        or len(set(required_types)) != candidate_count
    ):
        raise ValueError(
            "Thumbnail concept types must define 3 unique concepts."
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



THUMBNAIL_GENERIC_WORDS = {
    "system",
    "hidden",
    "inside",
    "secret",
    "truth",
    "world",
    "thing",
    "story",
    "video",
    "documentary",
    "network",
    "process",
}


def concept_text(value) -> str:
    return " ".join(
        str(value or "").strip().split()
    )


def concept_words(value) -> list[str]:
    return [
        item.lower()
        for item in re.findall(
            r"[A-Za-z0-9]+",
            concept_text(value)
        )
    ]


def score_thumbnail_concept(
    concept: dict,
    video_topic: str,
    standard: dict | None = None
) -> dict:
    standard = standard or load_thumbnail_standard()
    required_types = set(
        standard["concept_system"][
            "required_concept_types"
        ]
    )

    overlay_result = validate_thumbnail_text(
        concept.get("overlay_text", ""),
        standard
    )
    concept_type = concept_text(
        concept.get("concept_type")
    )
    subject = concept_text(
        concept.get("dominant_subject")
    )
    conflict = concept_text(
        concept.get("conflict")
    )
    emotion = concept_text(
        concept.get("emotional_trigger")
    )
    visual_hook = concept_text(
        concept.get("visual_hook")
    )
    differentiation = concept_text(
        concept.get("differentiation")
    )
    prompt = concept_text(
        concept.get("background_prompt")
    )
    topic_keywords = [
        concept_text(item).lower()
        for item in concept.get(
            "topic_keywords",
            []
        )
        if concept_text(item)
    ]

    combined = " ".join([
        subject,
        conflict,
        visual_hook,
        prompt,
        " ".join(topic_keywords),
    ]).lower()
    prompt_words = concept_words(prompt)
    subject_words = concept_words(subject)
    conflict_words = concept_words(conflict)
    hook_words = concept_words(visual_hook)
    differentiation_words = concept_words(
        differentiation
    )

    topic_tokens = {
        item
        for item in concept_words(video_topic)
        if len(item) >= 4
        and item not in THUMBNAIL_GENERIC_WORDS
    }
    keyword_tokens = {
        token
        for keyword in topic_keywords
        for token in concept_words(keyword)
        if len(token) >= 3
    }
    topic_overlap = sum(
        1
        for token in (
            topic_tokens | keyword_tokens
        )
        if token in combined
    )

    composition_terms = {
        "right",
        "center-right",
        "left",
        "negative space",
        "dominant subject",
        "single subject",
        "no text",
    }
    cinematic_terms = {
        "cinematic",
        "dramatic",
        "high contrast",
        "rim light",
        "rim lighting",
        "focal glow",
        "depth",
        "realistic",
        "premium",
        "urgent",
        "tension",
    }

    components = {
        "headline_contract": (
            15 if overlay_result["approved"] else 0
        ),
        "concept_type": (
            10 if concept_type in required_types else 0
        ),
        "topic_specificity": (
            20 if topic_overlap >= 3
            else 15 if topic_overlap == 2
            else 8 if topic_overlap == 1
            else 0
        ),
        "dominant_subject": (
            15
            if 4 <= len(subject_words) <= 22
            else 8
            if 2 <= len(subject_words) <= 30
            else 0
        ),
        "conflict_and_emotion": (
            10
            if len(conflict_words) >= 4
            and len(concept_words(emotion)) >= 1
            else 5
            if len(conflict_words) >= 2
            else 0
        ),
        "visual_hook": (
            10 if len(hook_words) >= 4 else 0
        ),
        "composition_contract": min(
            10,
            2 * sum(
                1
                for term in composition_terms
                if term in prompt.lower()
            )
        ),
        "cinematic_impact": min(
            5,
            sum(
                1
                for term in cinematic_terms
                if term in prompt.lower()
            )
        ),
        "differentiation": (
            5
            if len(differentiation_words) >= 4
            else 0
        ),
    }

    score = sum(components.values())
    minimum = int(
        standard["concept_system"][
            "minimum_preflight_score"
        ]
    )

    return {
        "score": score,
        "minimum_score": minimum,
        "approved": score >= minimum,
        "components": components,
        "topic_overlap_count": topic_overlap,
        "normalized_overlay_text": (
            overlay_result["normalized_text"]
        ),
    }


def validate_thumbnail_concepts(
    concepts: list[dict],
    video_topic: str,
    standard: dict | None = None
) -> list[dict]:
    standard = standard or load_thumbnail_standard()
    concept_system = standard["concept_system"]
    expected_count = int(
        concept_system["candidate_count"]
    )

    if len(concepts) != expected_count:
        raise ValueError(
            f"Expected {expected_count} thumbnail concepts, "
            f"received {len(concepts)}."
        )

    required_fields = {
        "concept_id",
        "concept_type",
        "overlay_text",
        "dominant_subject",
        "conflict",
        "emotional_trigger",
        "visual_hook",
        "differentiation",
        "topic_keywords",
        "background_prompt",
    }
    required_types = set(
        concept_system["required_concept_types"]
    )
    seen_ids = set()
    seen_types = set()
    seen_headlines = set()
    seen_subjects = set()
    scored = []

    for concept in concepts:
        missing = required_fields - set(concept)

        if missing:
            raise ValueError(
                "Thumbnail concept is missing fields: "
                + ", ".join(sorted(missing))
            )

        concept_id = concept_text(
            concept["concept_id"]
        ).upper()
        concept_type = concept_text(
            concept["concept_type"]
        )
        headline = normalize_thumbnail_text(
            concept["overlay_text"]
        )
        subject_key = " ".join(
            concept_words(
                concept["dominant_subject"]
            )
        )

        if not concept_id:
            raise ValueError(
                "Thumbnail concept_id cannot be empty."
            )

        if concept_type not in required_types:
            raise ValueError(
                "Unexpected thumbnail concept_type: "
                f"{concept_type}"
            )

        if concept_id in seen_ids:
            raise ValueError(
                "Thumbnail concept IDs must be unique."
            )

        if concept_type in seen_types:
            raise ValueError(
                "Thumbnail concept types must be unique."
            )

        if headline in seen_headlines:
            raise ValueError(
                "Thumbnail headlines must be unique."
            )

        if subject_key in seen_subjects:
            raise ValueError(
                "Thumbnail dominant subjects must be unique."
            )

        score = score_thumbnail_concept(
            concept=concept,
            video_topic=video_topic,
            standard=standard
        )

        if not score["approved"]:
            raise ValueError(
                f"Thumbnail concept {concept_id} failed "
                f"preflight score: {score['score']} < "
                f"{score['minimum_score']}."
            )

        normalized = dict(concept)
        normalized["concept_id"] = concept_id
        normalized["concept_type"] = concept_type
        normalized["overlay_text"] = score[
            "normalized_overlay_text"
        ]
        normalized["preflight_score"] = score[
            "score"
        ]
        normalized["preflight_breakdown"] = score[
            "components"
        ]
        normalized["preflight_approved"] = True
        scored.append(normalized)

        seen_ids.add(concept_id)
        seen_types.add(concept_type)
        seen_headlines.add(headline)
        seen_subjects.add(subject_key)

    if seen_types != required_types:
        raise ValueError(
            "Thumbnail concepts do not cover all required types."
        )

    return scored


def normalize_thumbnail_vision_qa(
    raw_result: dict,
    standard: dict | None = None
) -> dict:
    standard = standard or load_thumbnail_standard()
    score_names = [
        "topic_match",
        "dominant_subject",
        "visual_tension",
        "mobile_readability",
        "clean_composition",
        "cinematic_quality",
        "ctr_strength",
    ]
    raw_scores = raw_result.get("scores", {})
    scores = {}

    for name in score_names:
        value = raw_scores.get(name, 0)

        try:
            value = float(value)
        except (TypeError, ValueError):
            value = 0.0

        scores[name] = max(
            0.0,
            min(100.0, value)
        )

    average_score = round(
        sum(scores.values()) / len(scores),
        2
    )
    minimum = float(
        standard["concept_system"][
            "minimum_vision_score"
        ]
    )
    critical_floor = float(
        standard["concept_system"].get(
            "minimum_critical_dimension_score",
            72
        )
    )
    critical_dimensions = {
        "topic_match",
        "dominant_subject",
        "mobile_readability",
        "ctr_strength",
    }
    critical_passed = all(
        scores[name] >= critical_floor
        for name in critical_dimensions
    )
    verdict = concept_text(
        raw_result.get("verdict")
    ).lower()
    approved = (
        average_score >= minimum
        and critical_passed
        and verdict == "approved"
    )

    return {
        "scores": scores,
        "average_score": average_score,
        "minimum_score": minimum,
        "critical_floor": critical_floor,
        "critical_dimensions_passed": critical_passed,
        "approved": approved,
        "verdict": (
            "approved"
            if approved
            else "rejected"
        ),
        "issues": [
            concept_text(item)
            for item in raw_result.get("issues", [])
            if concept_text(item)
        ],
        "summary": concept_text(
            raw_result.get("summary")
        ),
    }


def combine_thumbnail_scores(
    preflight_score: float,
    vision_score: float,
    standard: dict | None = None
) -> dict:
    standard = standard or load_thumbnail_standard()
    weights = standard["concept_system"].get(
        "score_weights",
        {
            "preflight": 0.30,
            "vision": 0.70,
        }
    )
    preflight_weight = float(
        weights.get("preflight", 0.30)
    )
    vision_weight = float(
        weights.get("vision", 0.70)
    )
    total_weight = (
        preflight_weight
        + vision_weight
    )

    if total_weight <= 0:
        raise ValueError(
            "Thumbnail score weights must be positive."
        )

    final_score = round(
        (
            float(preflight_score)
            * preflight_weight
            + float(vision_score)
            * vision_weight
        )
        / total_weight,
        2
    )
    minimum = float(
        standard["concept_system"][
            "minimum_final_score"
        ]
    )

    return {
        "final_score": final_score,
        "minimum_score": minimum,
        "approved": final_score >= minimum,
        "weights": {
            "preflight": preflight_weight,
            "vision": vision_weight,
        },
    }

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
- match the approved Hiddenova cinematic gold-reference structure
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
    standard: dict | None = None,
    concept_type: str = "",
    conflict: str = "",
    emotional_trigger: str = "",
    visual_hook: str = ""
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
Use the approved Hiddenova gold-reference thumbnail as the exact style and layout reference. Reproduce its composition discipline, emotional intensity, lighting hierarchy, depth, and mobile readability. Do not reproduce its payment-terminal subject unless the current topic requires it.

VIDEO_TOPIC:
{video_topic}

CONCEPT_TYPE:
{concept_type or "topic_specific"}

DOMINANT_MAIN_SUBJECT:
{main_subject}

CONFLICT_OR_STAKES:
{conflict or "clear topic-specific tension"}

EMOTIONAL_TRIGGER:
{emotional_trigger or "curiosity and urgency"}

VISUAL_HOOK:
{visual_hook or "one instantly understandable visual idea"}

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
        "standard_is_hiddenova_cinematic_v3": (
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
