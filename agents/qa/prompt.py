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
    seo_data: dict,
    editorial_profile: dict | None = None,
    fact_qa_data: dict | None = None,
    risk_review_data: dict | None = None,
) -> str:
    system_prompt = load_text_file("system.md")
    workflow = load_text_file("workflow.md")
    profile = editorial_profile or {
        "display_name": "Hiddenova",
        "profile_name": "hiddenova_editorial_v2",
        "script": {
            "brand_intro": {
                "required": True,
                "brand_name": "Hiddenova",
                "scan_word_limit": 25,
            }
        },
        "factuality": {
            "pipeline_required": False,
        },
        "qa": {
            "minimum_overall_score": 85,
            "minimum_hook_strength_score": 85,
            "minimum_hook_intro_distinctness_score": 80,
            "minimum_narrative_spine_score": 85,
            "minimum_specificity_score": 80,
            "minimum_repetition_risk_score": 80,
            "minimum_title_thumbnail_synergy_score": 85,
        },
    }
    brand_intro = profile["script"]["brand_intro"]
    qa = profile["qa"]
    factual_required = bool(
        profile["factuality"]["pipeline_required"]
    )

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

    if brand_intro["required"]:
        brand_rule = (
            f'The introduction must contain the exact word '
            f'"{brand_intro["brand_name"]}" within its first '
            f'{brand_intro["scan_word_limit"]} words.'
        )
    else:
        brand_rule = (
            "A branded introduction is not required for this channel. "
            "Set the legacy hiddenova_brand_intro schema check to "
            'status="pass" and score=100.'
        )

    factual_section = (
        f"""
FACT QA OUTPUT:
{json.dumps(fact_qa_data, indent=2, ensure_ascii=True)}

RISK REVIEW OUTPUT:
{json.dumps(risk_review_data, indent=2, ensure_ascii=True)}

The factual and risk layers are mandatory for this channel.
Reject the editorial package if either supplied output is not approved.
Do not re-litigate sourced facts; evaluate whether the script remains
clear, compelling, and accurately packaged.
"""
        if factual_required
        else "This channel does not require the factual research pipeline."
    )

    return f"""
{system_prompt}

{workflow}

--------------------------------------------------
CHANNEL EDITORIAL PROFILE
--------------------------------------------------

CHANNEL:
{profile["display_name"]}

EDITORIAL STANDARD:
{profile["profile_name"]}

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
FACTUAL AND RISK GATES
--------------------------------------------------

{factual_section}

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
   Is there one cause-and-effect journey, escalation,
   rise, fall, investigation, or turning-point chain?

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
   This is a legacy schema key for the active channel-brand
   introduction contract.
   {brand_rule}

8. standard_cta
   Does the final CTA explicitly ask viewers to comment,
   like, and subscribe in a concise natural sentence?

Mandatory thresholds for approval:

- overall_score: at least {qa["minimum_overall_score"]}
- hook_strength: at least {qa["minimum_hook_strength_score"]}
- hook_intro_distinctness: at least {qa["minimum_hook_intro_distinctness_score"]}
- narrative_spine: at least {qa["minimum_narrative_spine_score"]}
- specificity: at least {qa["minimum_specificity_score"]}
- repetition_risk: at least {qa["minimum_repetition_risk_score"]}
- title_thumbnail_synergy: at least {qa["minimum_title_thumbnail_synergy_score"]}
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
- Each check status must be pass, warning, or fail.
- Each check score must be an integer between 0 and 100.
- If status is rejected, issues must explain each
  production-blocking weakness.
- Recommendations must be concrete enough for an automatic
  script regeneration.
- Do not rewrite the script.
- Do not create new SEO metadata.
- Only evaluate quality and readiness.
- Return JSON only.
""".strip()
