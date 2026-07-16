import re
from collections import Counter
from typing import Any


DEFAULT_SCRIPT_WORD_MIN = 1250
DEFAULT_SCRIPT_WORD_MAX = 1650
DEFAULT_MEDIA_DURATION_MIN_SECONDS = 480
DEFAULT_MEDIA_DURATION_MAX_SECONDS = 720

DEFAULT_EDITORIAL_OVERALL_MIN = 85
DEFAULT_HOOK_STRENGTH_MIN = 85
DEFAULT_HOOK_INTRO_DISTINCTNESS_MIN = 80
DEFAULT_NARRATIVE_SPINE_MIN = 85
DEFAULT_SPECIFICITY_MIN = 80
DEFAULT_REPETITION_RISK_MIN = 80
DEFAULT_TITLE_THUMBNAIL_SYNERGY_MIN = 85
DEFAULT_HIDDENOVA_BRAND_INTRO_MIN = 100
DEFAULT_STANDARD_CTA_MIN = 100

EDITORIAL_CRITICAL_CHECKS = {
    "hook_strength": DEFAULT_HOOK_STRENGTH_MIN,
    "hook_intro_distinctness": (
        DEFAULT_HOOK_INTRO_DISTINCTNESS_MIN
    ),
    "narrative_spine": DEFAULT_NARRATIVE_SPINE_MIN,
    "specificity": DEFAULT_SPECIFICITY_MIN,
    "repetition_risk": DEFAULT_REPETITION_RISK_MIN,
    "title_thumbnail_synergy": (
        DEFAULT_TITLE_THUMBNAIL_SYNERGY_MIN
    ),
}

CONTENT_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "because",
    "been", "before", "behind", "but", "by", "can", "could",
    "do", "does", "each", "for", "from", "had", "has",
    "have", "he", "her", "here", "him", "his", "how",
    "i", "if", "in", "into", "is", "it", "its", "may",
    "more", "most", "not", "of", "on", "one", "or", "our",
    "out", "over", "she", "so", "some", "than", "that",
    "the", "their", "them", "then", "there", "these",
    "they", "this", "those", "through", "to", "under",
    "up", "us", "was", "we", "were", "what", "when",
    "where", "which", "while", "who", "why", "will",
    "with", "would", "you", "your",
}

ABSTRACT_BOILERPLATE_PHRASES = (
    "beneath the surface",
    "behind the scenes",
    "hidden system",
    "hidden systems",
    "invisible system",
    "invisible systems",
    "quiet technology",
    "quiet moment",
    "modern world",
    "deceptively simple",
    "complex system",
    "carefully coordinated",
    "one of the most",
    "the true achievement",
)

GENERIC_SECTION_TITLES = {
    "introduction",
    "the beginning",
    "how it works",
    "why it matters",
    "the hidden system",
    "the bigger picture",
    "the conclusion",
    "what happens next",
}

CONTRAST_MARKERS = (
    " but ",
    " yet ",
    " however ",
    " actually ",
    " instead ",
    " although ",
    " not ",
    " before ",
    " until ",
)


def count_words(text: str) -> int:
    return len(
        re.findall(
            r"\b[\w'-]+\b",
            str(text)
        )
    )


def get_narration(value: Any) -> str:
    if isinstance(value, dict):
        return str(
            value.get("narration", "")
        ).strip()

    if value is None:
        return ""

    return str(value).strip()


def get_script_narration_parts(
    script_data: dict
) -> list[str]:
    script = script_data.get(
        "script",
        script_data
    )

    parts = [
        get_narration(script.get("hook")),
        get_narration(
            script.get("introduction")
            or script.get("intro")
        ),
    ]

    for section in (
        script.get("main_sections")
        or script.get("sections")
        or []
    ):
        parts.append(
            get_narration(section)
        )

    parts.extend([
        get_narration(script.get("conclusion")),
        get_narration(
            script.get("call_to_action")
        ),
    ])

    return [
        part
        for part in parts
        if part
    ]


def count_script_narration_words(
    script_data: dict
) -> int:
    return sum(
        count_words(part)
        for part in get_script_narration_parts(
            script_data
        )
    )


def evaluate_script_word_count(
    script_data: dict,
    minimum: int = DEFAULT_SCRIPT_WORD_MIN,
    maximum: int = DEFAULT_SCRIPT_WORD_MAX
) -> dict:
    minimum = int(minimum)
    maximum = int(maximum)

    if minimum <= 0:
        raise ValueError(
            "Minimum script word count must be positive."
        )

    if maximum < minimum:
        raise ValueError(
            "Maximum script word count cannot be "
            "lower than minimum."
        )

    word_count = count_script_narration_words(
        script_data
    )

    return {
        "word_count": word_count,
        "minimum": minimum,
        "maximum": maximum,
        "approved": minimum <= word_count <= maximum,
        "status": (
            "pass"
            if minimum <= word_count <= maximum
            else "fail"
        )
    }


def assert_script_word_count(
    script_data: dict,
    minimum: int = DEFAULT_SCRIPT_WORD_MIN,
    maximum: int = DEFAULT_SCRIPT_WORD_MAX
) -> dict:
    result = evaluate_script_word_count(
        script_data=script_data,
        minimum=minimum,
        maximum=maximum
    )

    if not result["approved"]:
        raise ValueError(
            "Script narration word count is outside "
            "the approved range: "
            f"actual={result['word_count']} "
            f"minimum={result['minimum']} "
            f"maximum={result['maximum']}."
        )

    return result


def evaluate_duration_seconds(
    actual_seconds: float,
    minimum: int = DEFAULT_MEDIA_DURATION_MIN_SECONDS,
    maximum: int = DEFAULT_MEDIA_DURATION_MAX_SECONDS
) -> dict:
    actual = float(actual_seconds)
    minimum = int(minimum)
    maximum = int(maximum)

    if actual <= 0:
        raise ValueError(
            "Media duration must be greater than zero."
        )

    if minimum <= 0:
        raise ValueError(
            "Minimum media duration must be positive."
        )

    if maximum < minimum:
        raise ValueError(
            "Maximum media duration cannot be lower "
            "than minimum."
        )

    approved = minimum <= actual <= maximum

    if actual < minimum:
        reason = "too_short"
    elif actual > maximum:
        reason = "too_long"
    else:
        reason = "within_range"

    return {
        "actual_seconds": round(actual, 2),
        "minimum_seconds": minimum,
        "maximum_seconds": maximum,
        "approved": approved,
        "status": "pass" if approved else "fail",
        "reason": reason,
    }


def assert_duration_seconds(
    actual_seconds: float,
    minimum: int = DEFAULT_MEDIA_DURATION_MIN_SECONDS,
    maximum: int = DEFAULT_MEDIA_DURATION_MAX_SECONDS,
    label: str = "Media"
) -> dict:
    result = evaluate_duration_seconds(
        actual_seconds=actual_seconds,
        minimum=minimum,
        maximum=maximum
    )

    if not result["approved"]:
        raise ValueError(
            f"{label} duration is outside the approved "
            "8-12 minute range: "
            f"actual={result['actual_seconds']}s "
            f"minimum={result['minimum_seconds']}s "
            f"maximum={result['maximum_seconds']}s."
        )

    return result


def _content_tokens(text: str) -> list[str]:
    return [
        token.lower()
        for token in re.findall(
            r"\b[a-zA-Z][a-zA-Z'-]{2,}\b",
            str(text)
        )
        if token.lower() not in CONTENT_STOPWORDS
    ]


def _jaccard_similarity(
    first: str,
    second: str
) -> float:
    first_tokens = set(_content_tokens(first))
    second_tokens = set(_content_tokens(second))

    if not first_tokens or not second_tokens:
        return 1.0

    return len(
        first_tokens & second_tokens
    ) / len(
        first_tokens | second_tokens
    )


def _repeated_phrase_excess(text: str) -> int:
    tokens = _content_tokens(text)

    if len(tokens) < 4:
        return 0

    counts = Counter(
        tuple(tokens[index:index + 3])
        for index in range(len(tokens) - 2)
    )

    return sum(
        count - 2
        for phrase, count in counts.items()
        if count > 2
        and len(set(phrase)) > 1
    )


def _score_status(
    score: int,
    minimum: int
) -> str:
    if score >= minimum:
        return "pass"

    if score >= max(0, minimum - 10):
        return "warning"

    return "fail"


def evaluate_editorial_structure(
    script_data: dict
) -> dict:
    script = script_data.get(
        "script",
        script_data
    )

    hook = get_narration(script.get("hook"))
    introduction = get_narration(
        script.get("introduction")
        or script.get("intro")
    )
    sections = (
        script.get("main_sections")
        or script.get("sections")
        or []
    )
    narration = "\n\n".join(
        get_script_narration_parts(script_data)
    )
    narration_lower = narration.lower()

    hook_words = count_words(hook)
    introduction_words = count_words(introduction)
    hook_intro_overlap = _jaccard_similarity(
        hook,
        introduction
    )

    hook_score = 100

    if hook_words < 60 or hook_words > 130:
        hook_score -= 25

    hook_lower = f" {hook.lower()} "

    if (
        "?" not in hook
        and not any(
            marker in hook_lower
            for marker in CONTRAST_MARKERS
        )
    ):
        hook_score -= 20

    if count_words(hook) > 0:
        first_sentence = re.split(
            r"(?<=[.!?])\s+",
            hook,
            maxsplit=1
        )[0]
    else:
        first_sentence = ""

    if count_words(first_sentence) > 28:
        hook_score -= 10

    hook_score = max(0, hook_score)

    if hook_intro_overlap <= 0.12:
        distinctness_score = 100
    else:
        distinctness_score = round(
            max(
                0.0,
                100.0 - (
                    hook_intro_overlap - 0.12
                ) * 260.0
            )
        )

    section_titles = [
        str(
            section.get("title", "")
        ).strip()
        for section in sections
        if isinstance(section, dict)
    ]
    normalized_titles = [
        re.sub(
            r"\s+",
            " ",
            title.lower()
        )
        for title in section_titles
    ]

    narrative_score = 100

    if not 5 <= len(sections) <= 7:
        narrative_score -= 30

    duplicate_title_count = (
        len(normalized_titles)
        - len(set(normalized_titles))
    )
    narrative_score -= duplicate_title_count * 15

    generic_title_count = sum(
        title in GENERIC_SECTION_TITLES
        for title in normalized_titles
    )
    narrative_score -= generic_title_count * 8

    causal_marker_count = sum(
        narration_lower.count(marker)
        for marker in (
            "because",
            "therefore",
            "which means",
            "so that",
            "as a result",
            "but",
            "yet",
        )
    )

    if causal_marker_count < 4:
        narrative_score -= 15

    narrative_score = max(0, narrative_score)

    repeated_phrase_excess = _repeated_phrase_excess(
        narration
    )
    boilerplate_hits = {}

    for phrase in ABSTRACT_BOILERPLATE_PHRASES:
        count = len(
            re.findall(
                rf"\b{re.escape(phrase)}\b",
                narration_lower
            )
        )

        if count:
            boilerplate_hits[phrase] = count

    boilerplate_total = sum(
        boilerplate_hits.values()
    )
    boilerplate_excess = max(
        0,
        boilerplate_total - 3
    )

    repetition_score = max(
        0,
        100
        - min(50, repeated_phrase_excess * 5)
        - min(42, boilerplate_excess * 7)
    )

    issues = []

    if hook_score < DEFAULT_HOOK_STRENGTH_MIN:
        issues.append({
            "field": "script.hook",
            "severity": "high",
            "message": (
                "The hook lacks the required structural "
                "strength, contrast, or opening precision."
            )
        })

    if (
        distinctness_score
        < DEFAULT_HOOK_INTRO_DISTINCTNESS_MIN
    ):
        issues.append({
            "field": "script.introduction",
            "severity": "high",
            "message": (
                "The introduction repeats too much of the "
                "hook instead of advancing the story."
            )
        })

    if narrative_score < DEFAULT_NARRATIVE_SPINE_MIN:
        issues.append({
            "field": "script.main_sections",
            "severity": "high",
            "message": (
                "The section sequence does not form a "
                "strong enough cause-and-effect narrative."
            )
        })

    if repetition_score < DEFAULT_REPETITION_RISK_MIN:
        issues.append({
            "field": "script.repetition",
            "severity": "high",
            "message": (
                "Repeated phrases or abstract documentary "
                "language create a noticeable repetition risk."
            )
        })

    return {
        "approved": (
            hook_score >= DEFAULT_HOOK_STRENGTH_MIN
            and distinctness_score
            >= DEFAULT_HOOK_INTRO_DISTINCTNESS_MIN
            and narrative_score
            >= DEFAULT_NARRATIVE_SPINE_MIN
            and repetition_score
            >= DEFAULT_REPETITION_RISK_MIN
        ),
        "checks": {
            "hook_strength": {
                "score": hook_score,
                "status": _score_status(
                    hook_score,
                    DEFAULT_HOOK_STRENGTH_MIN
                )
            },
            "hook_intro_distinctness": {
                "score": distinctness_score,
                "status": _score_status(
                    distinctness_score,
                    DEFAULT_HOOK_INTRO_DISTINCTNESS_MIN
                )
            },
            "narrative_spine": {
                "score": narrative_score,
                "status": _score_status(
                    narrative_score,
                    DEFAULT_NARRATIVE_SPINE_MIN
                )
            },
            "repetition_risk": {
                "score": repetition_score,
                "status": _score_status(
                    repetition_score,
                    DEFAULT_REPETITION_RISK_MIN
                )
            },
        },
        "metrics": {
            "hook_word_count": hook_words,
            "introduction_word_count": (
                introduction_words
            ),
            "hook_intro_overlap": round(
                hook_intro_overlap,
                4
            ),
            "section_count": len(sections),
            "duplicate_section_title_count": (
                duplicate_title_count
            ),
            "generic_section_title_count": (
                generic_title_count
            ),
            "repeated_phrase_excess": (
                repeated_phrase_excess
            ),
            "boilerplate_hits": boilerplate_hits,
        },
        "issues": issues,
    }



def evaluate_hiddenova_channel_contract(
    script_data: dict,
    require_brand_intro: bool = True,
    require_standard_cta: bool = True
) -> dict:
    script = script_data.get(
        "script",
        script_data
    )
    introduction = get_narration(
        script.get("introduction")
        or script.get("intro")
    )
    call_to_action = get_narration(
        script.get("call_to_action")
    )

    intro_words = re.findall(
        r"\b[\w'-]+\b",
        introduction
    )
    intro_opening = " ".join(
        intro_words[:25]
    ).lower()
    brand_intro_present = bool(
        re.search(
            r"\bhiddenova\b",
            intro_opening
        )
    )

    cta_lower = call_to_action.lower()
    cta_actions = {
        "comment": bool(
            re.search(
                r"\bcomments?\b",
                cta_lower
            )
        ),
        "like": bool(
            re.search(
                r"\blikes?\b",
                cta_lower
            )
        ),
        "subscribe": bool(
            re.search(
                r"\bsubscrib(?:e|es|ed|ing|er|ers)\b",
                cta_lower
            )
        ),
    }
    cta_word_count = count_words(call_to_action)
    cta_length_valid = 20 <= cta_word_count <= 55
    standard_cta_present = (
        all(cta_actions.values())
        and cta_length_valid
    )

    brand_score = (
        100
        if (
            brand_intro_present
            or not require_brand_intro
        )
        else 0
    )
    cta_score = (
        100
        if (
            standard_cta_present
            or not require_standard_cta
        )
        else 0
    )

    issues = []

    if require_brand_intro and not brand_intro_present:
        issues.append({
            "field": "script.introduction",
            "severity": "high",
            "message": (
                "The introduction must include the exact "
                "word Hiddenova within its first 25 words."
            )
        })

    if require_standard_cta and not standard_cta_present:
        missing_actions = [
            name
            for name, present
            in cta_actions.items()
            if not present
        ]
        issues.append({
            "field": "script.call_to_action",
            "severity": "high",
            "message": (
                "The final CTA must explicitly ask viewers "
                "to comment, like, and subscribe in 20 to "
                "55 narration words. Missing actions: "
                f"{', '.join(missing_actions) or 'none'}; "
                f"word_count={cta_word_count}."
            )
        })

    approved = (
        brand_score >= DEFAULT_HIDDENOVA_BRAND_INTRO_MIN
        and cta_score >= DEFAULT_STANDARD_CTA_MIN
    )

    return {
        "approved": approved,
        "checks": {
            "hiddenova_brand_intro": {
                "score": brand_score,
                "status": (
                    "pass"
                    if brand_score >= 100
                    else "fail"
                )
            },
            "standard_cta": {
                "score": cta_score,
                "status": (
                    "pass"
                    if cta_score >= 100
                    else "fail"
                )
            },
        },
        "metrics": {
            "brand_intro_present": brand_intro_present,
            "brand_intro_scan_words": min(
                len(intro_words),
                25
            ),
            "cta_actions": cta_actions,
            "cta_word_count": cta_word_count,
            "cta_length_valid": cta_length_valid,
        },
        "issues": issues,
    }

def evaluate_qa_editorial_gate(
    qa_data: dict,
    minimum_overall: int = DEFAULT_EDITORIAL_OVERALL_MIN,
    critical_thresholds: dict | None = None
) -> dict:
    thresholds = dict(
        EDITORIAL_CRITICAL_CHECKS
    )

    if critical_thresholds:
        thresholds.update({
            key: int(value)
            for key, value
            in critical_thresholds.items()
        })

    checks = qa_data.get("checks", {})
    failures = []

    for name, minimum in thresholds.items():
        check = checks.get(name)

        if not isinstance(check, dict):
            failures.append({
                "check": name,
                "reason": "missing",
                "actual": None,
                "minimum": minimum,
            })
            continue

        score = int(check.get("score", 0))
        status = str(
            check.get("status", "fail")
        ).lower()

        if score < minimum or status != "pass":
            failures.append({
                "check": name,
                "reason": "below_threshold",
                "actual": score,
                "minimum": minimum,
                "status": status,
            })

    overall_score = int(
        qa_data.get("overall_score", 0)
    )

    if overall_score < int(minimum_overall):
        failures.append({
            "check": "overall_score",
            "reason": "below_threshold",
            "actual": overall_score,
            "minimum": int(minimum_overall),
        })

    if qa_data.get("status") != "approved":
        failures.append({
            "check": "qa_status",
            "reason": "not_approved",
            "actual": qa_data.get("status"),
            "minimum": "approved",
        })

    return {
        "approved": not failures,
        "status": "pass" if not failures else "fail",
        "minimum_overall_score": int(
            minimum_overall
        ),
        "critical_thresholds": thresholds,
        "failures": failures,
    }


def assert_qa_editorial_gate(
    qa_data: dict,
    minimum_overall: int = DEFAULT_EDITORIAL_OVERALL_MIN,
    critical_thresholds: dict | None = None
) -> dict:
    result = evaluate_qa_editorial_gate(
        qa_data=qa_data,
        minimum_overall=minimum_overall,
        critical_thresholds=critical_thresholds
    )

    if not result["approved"]:
        failed = ", ".join(
            item["check"]
            for item in result["failures"]
        )

        raise ValueError(
            "Editorial quality gate failed: "
            f"{failed}."
        )

    return result
