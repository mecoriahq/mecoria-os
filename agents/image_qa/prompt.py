import json
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent.parent


def load_text_file(filename: str) -> str:
    file_path = BASE_DIR / filename

    if not file_path.exists():
        raise FileNotFoundError(f"Required file not found: {file_path}")

    return file_path.read_text(encoding="utf-8-sig")


def load_standard() -> str:
    standard_path = PROJECT_ROOT / "docs" / "standards" / "image-generation.md"

    if not standard_path.exists():
        raise FileNotFoundError(f"Required standard not found: {standard_path}")

    return standard_path.read_text(encoding="utf-8-sig")


def load_thumbnail_rules(channel: str) -> dict:
    rules_path = PROJECT_ROOT / "config" / "thumbnail_rules" / f"{channel.lower()}.json"

    if not rules_path.exists():
        raise FileNotFoundError(f"Required thumbnail rules not found: {rules_path}")

    return json.loads(rules_path.read_text(encoding="utf-8-sig"))


def build_prompt(image_generation_data: dict, technical_checks: dict) -> str:
    system_prompt = load_text_file("system.md")
    workflow = load_text_file("workflow.md")
    image_standard = load_standard()
    thumbnail_rules = load_thumbnail_rules(image_generation_data["channel"])

    required_schema = {
        "overall_score": 0,
        "visual_checks": {
            "subject_visibility": {"status": "pass, warning, or fail", "score": 0},
            "composition_quality": {"status": "pass, warning, or fail", "score": 0},
            "lighting_quality": {"status": "pass, warning, or fail", "score": 0},
            "thumbnail_text_presence": {"status": "pass, warning, or fail", "score": 0},
            "thumbnail_text_readability": {"status": "pass, warning, or fail", "score": 0},
            "thumbnail_text_word_count": {"status": "pass, warning, or fail", "score": 0},
            "thumbnail_text_contrast": {"status": "pass, warning, or fail", "score": 0},
            "thumbnail_text_not_covering_subject": {"status": "pass, warning, or fail", "score": 0},
            "logo_absence": {"status": "pass, warning, or fail", "score": 0},
            "standard_alignment": {"status": "pass, warning, or fail", "score": 0},
            "ctr_potential": {"status": "pass, warning, or fail", "score": 0}
        },
        "issues": [
            {
                "field": "string",
                "severity": "low, medium, or high",
                "message": "string"
            }
        ],
        "recommendations": [
            {
                "field": "string",
                "suggestion": "string"
            }
        ]
    }

    return f"""
{system_prompt}

{workflow}

--------------------------------------------------
MECORIA IMAGE GENERATION STANDARD
--------------------------------------------------

{image_standard}

--------------------------------------------------
HIDDENOVA THUMBNAIL TEXT STANDARD
--------------------------------------------------

{json.dumps(thumbnail_rules, ensure_ascii=False, indent=2)}

--------------------------------------------------
IMAGE GENERATION OUTPUT
--------------------------------------------------

{json.dumps(image_generation_data, ensure_ascii=False, indent=2)}

--------------------------------------------------
TECHNICAL CHECKS
--------------------------------------------------

{json.dumps(technical_checks, ensure_ascii=False, indent=2)}

--------------------------------------------------
OUTPUT REQUIREMENTS
--------------------------------------------------

Return ONLY valid JSON.

Do NOT return markdown.

Do NOT wrap JSON inside code blocks.

Do NOT explain anything.

Use EXACTLY this structure:

{json.dumps(required_schema, indent=2)}

Rules:

- Evaluate the image against Mecoria Image Generation Standard.
- Evaluate the thumbnail against Hiddenova Thumbnail Text Standard.
- The thumbnail should include a short English text hook unless there is a strong reason not to.
- Text should ideally be 1 to 4 words.
- Text should be bold, high contrast, and readable on mobile.
- Text should create curiosity and support CTR.
- Text must not repeat the full video title.
- Text must not cover the main subject.
- The main subject must remain clear and dominant.
- Check whether the composition is mobile-readable.
- Check whether lighting is cinematic and realistic.
- Check whether logos, watermarks, fake signage, readable labels, private data, or unwanted text exist.
- The only acceptable readable text should be the intentional short thumbnail hook.
- overall_score must be an integer between 0 and 100.
- Recommendations must be actionable.
- Do not approve if the thumbnail has major visual issues or unreadable/cluttered text.

Return JSON only.
""".strip()
