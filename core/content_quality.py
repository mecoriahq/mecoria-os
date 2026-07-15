import re
from typing import Any


DEFAULT_SCRIPT_WORD_MIN = 800
DEFAULT_SCRIPT_WORD_MAX = 1300


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
