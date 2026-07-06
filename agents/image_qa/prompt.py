import json
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent.parent


def load_text_file(filename: str) -> str:
    file_path = BASE_DIR / filename

    if not file_path.exists():
        raise FileNotFoundError(f"Required file not found: {file_path}")

    return file_path.read_text(encoding="utf-8")


def load_standard() -> str:
    standard_path = PROJECT_ROOT / "docs" / "standards" / "image-generation.md"

    if not standard_path.exists():
        raise FileNotFoundError(f"Required standard not found: {standard_path}")

    return standard_path.read_text(encoding="utf-8")


def build_prompt(image_generation_data: dict, technical_checks: dict) -> str:
    system_prompt = load_text_file("system.md")
    workflow = load_text_file("workflow.md")
    image_standard = load_standard()

    required_schema = {
        "overall_score": 0,
        "visual_checks": {
            "subject_visibility": {"status": "pass, warning, or fail", "score": 0},
            "composition_quality": {"status": "pass, warning, or fail", "score": 0},
            "lighting_quality": {"status": "pass, warning, or fail", "score": 0},
            "text_absence": {"status": "pass, warning, or fail", "score": 0},
            "logo_absence": {"status": "pass, warning, or fail", "score": 0},
            "standard_alignment": {"status": "pass, warning, or fail", "score": 0}
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
- Check whether the main subject is clear and dominant.
- Check whether the composition is mobile-readable.
- Check whether lighting is cinematic and realistic.
- Check whether unwanted generated text exists.
- Check whether logos, watermarks, or fake signage exist.
- overall_score must be an integer between 0 and 100.
- Recommendations must be actionable.
- Do not suggest publishing if the image has major visual issues.

Return JSON only.
""".strip()