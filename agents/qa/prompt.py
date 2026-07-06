import json
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent


def load_text_file(filename: str) -> str:
    file_path = BASE_DIR / filename

    if not file_path.exists():
        raise FileNotFoundError(f"Required file not found: {file_path}")

    return file_path.read_text(encoding="utf-8")


def build_prompt(script_data: dict, seo_data: dict) -> str:
    system_prompt = load_text_file("system.md")
    workflow = load_text_file("workflow.md")

    required_schema = {
        "status": "approved or rejected",
        "overall_score": 0,
        "checks": {
            "script_quality": {
                "status": "pass, warning, or fail",
                "score": 0
            },
            "seo_alignment": {
                "status": "pass, warning, or fail",
                "score": 0
            },
            "title_quality": {
                "status": "pass, warning, or fail",
                "score": 0
            },
            "description_quality": {
                "status": "pass, warning, or fail",
                "score": 0
            },
            "tags_quality": {
                "status": "pass, warning, or fail",
                "score": 0
            },
            "thumbnail_text_quality": {
                "status": "pass, warning, or fail",
                "score": 0
            }
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
SCRIPT AGENT OUTPUT
--------------------------------------------------

{json.dumps(script_data, ensure_ascii=False, indent=2)}

--------------------------------------------------
SEO AGENT OUTPUT
--------------------------------------------------

{json.dumps(seo_data, ensure_ascii=False, indent=2)}

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

- status must be either "approved" or "rejected".
- overall_score must be an integer between 0 and 100.
- Each check status must be one of: "pass", "warning", "fail".
- Each check score must be an integer between 0 and 100.
- If status is "approved", issues can be an empty array.
- If status is "rejected", issues must explain why.
- Recommendations must be actionable.
- Do not rewrite the script.
- Do not create new SEO metadata.
- Only evaluate quality and readiness.

Return JSON only.
""".strip()