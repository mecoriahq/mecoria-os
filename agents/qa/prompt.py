import json
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent


def load_text_file(filename: str) -> str:
    file_path = BASE_DIR / filename

    if not file_path.exists():
        raise FileNotFoundError(
            f"Required file not found: {file_path}"
        )

    return file_path.read_text(encoding="utf-8")


def build_prompt(
    script_data: dict,
    seo_data: dict
) -> str:
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
            "hook_strength": {
                "status": "pass, warning, or fail",
                "score": 0
            },
            "hook_intro_distinctness": {
                "status": "pass, warning, or fail",
                "score": 0
            },
            "narrative_spine": {
                "status": "pass, warning, or fail",
                "score": 0
            },
            "specificity": {
                "status": "pass, warning, or fail",
                "score": 0
            },
            "repetition_risk": {
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
            "title_thumbnail_synergy": {
                "status": "pass, warning, or fail",
                "score": 0
            },
            "hiddenova_brand_intro": {
                "status": "pass, warning, or fail",
                "score": 0
            },
            "standard_cta": {
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

{json.dumps(
    script_data,
    ensure_ascii=False,
    indent=2
)}

--------------------------------------------------
SEO AGENT OUTPUT
--------------------------------------------------

{json.dumps(
    seo_data,
    ensure_ascii=False,
    indent=2
)}

--------------------------------------------------
STRICT EDITORIAL SCORING
--------------------------------------------------

Calibrate scores honestly:

- 90-100: exceptional and highly publishable.
- 85-89: strong and publishable.
- 80-84: usable but needs improvement.
- 70-79: generic, repetitive, or weak.
- Below 70: not production-ready.

A script that is merely clear and factually plausible must
NOT receive a score above 84.

Evaluate these critical checks:

1. hook_strength
   Does the opening create immediate tension, a paradox,
   a consequence, or a question worth answering?

2. hook_intro_distinctness
   Does the introduction advance the story rather than
   rephrase the hook?

3. narrative_spine
   Is there one cause-and-effect journey, escalation, or
   investigation instead of a list of explanations?

4. specificity
   Does the script explain concrete mechanisms,
   decisions, constraints, and consequences?
   Do not reward invented precision.

5. repetition_risk
   A high score means LOW repetition risk.
   Penalize recurring abstract phrases, repeated summaries,
   and AI-style documentary filler.

6. title_thumbnail_synergy
   Do the title and thumbnail work together while each adds
   different information?
   Is the subject immediately clear?

7. hiddenova_brand_intro
   Does the introduction contain the exact word Hiddenova
   within its first 25 words, without weakening the hook?

8. standard_cta
   Does the final CTA explicitly ask viewers to comment,
   like, and subscribe in a concise natural sentence?

Mandatory thresholds for approval:

- overall_score: at least 85
- hook_strength: at least 85
- hook_intro_distinctness: at least 80
- narrative_spine: at least 85
- specificity: at least 80
- repetition_risk: at least 80
- title_thumbnail_synergy: at least 85
- hiddenova_brand_intro: 100
- standard_cta: 100

Any critical check below its threshold requires
status="rejected".

The thumbnail text must be 2 to 4 ALL-CAPS words and must
express a direct, visually understandable tension.

SEO chapters must be an empty array. Actual timestamps are
generated after narration audio assembly.

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
- Each check status must be one of:
  "pass", "warning", "fail".
- Each check score must be an integer between 0 and 100.
- If status is "rejected", issues must explain each
  production-blocking weakness.
- Recommendations must be concrete enough for an automatic
  script regeneration.
- Do not rewrite the script.
- Do not create new SEO metadata.
- Only evaluate quality and readiness.

Return JSON only.
""".strip()
