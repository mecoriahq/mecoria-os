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
    research_data: dict,
    selected_idea: dict,
    target_word_count_min: int = 1250,
    target_word_count_max: int = 1650,
    revision_feedback: dict | None = None,
    editorial_profile: dict | None = None,
    factual_research: dict | None = None,
    claims_ledger: dict | None = None,
) -> str:
    system_prompt = load_text_file("system.md")
    workflow = load_text_file("workflow.md")
    profile = editorial_profile or {
        "display_name": "Hiddenova",
        "profile_name": "hiddenova_editorial_v2",
        "script": {
            "estimated_duration_label": "8-12 minutes",
            "main_section_min": 5,
            "main_section_max": 7,
            "brand_intro": {
                "required": True,
                "brand_name": "Hiddenova",
                "scan_word_limit": 25,
            },
            "cta": {
                "required": True,
            },
            "story_rules": [],
        },
        "factuality": {
            "pipeline_required": False,
        },
    }
    script_policy = profile["script"]
    factual_required = bool(
        profile.get("factuality", {}).get(
            "pipeline_required",
            False,
        )
    )

    narration_block = {
        "narration": "string",
        "claim_ids": ["C01"],
    } if factual_required else {
        "narration": "string",
    }

    section_block = {
        "title": "string",
        "narration": "string",
        "visual_direction": "string",
    }

    if factual_required:
        section_block["claim_ids"] = ["C01"]

    required_schema = {
        "title": "string",
        "format": "string",
        "estimated_duration": "string",
        "hook": narration_block,
        "introduction": narration_block,
        "main_sections": [section_block],
        "conclusion": narration_block,
        "call_to_action": {
            "narration": "string",
            **(
                {"claim_ids": []}
                if factual_required
                else {}
            ),
        },
    }

    revision_section = ""

    if revision_feedback:
        revision_section = f"""
--------------------------------------------------
MANDATORY EDITORIAL REVISION BRIEF
--------------------------------------------------

This is a regeneration attempt. Correct every relevant
issue below. Do not mention the revision process in the
script.

{json.dumps(
    revision_feedback,
    ensure_ascii=False,
    indent=2
)}
"""

    brand_intro = script_policy["brand_intro"]
    brand_rule = (
        f'- The introduction MUST contain the exact word '
        f'"{brand_intro["brand_name"]}" within its first '
        f'{brand_intro["scan_word_limit"]} words, then '
        "immediately advance the story."
        if brand_intro["required"]
        else (
            "- Do not force a channel-name sentence into the opening. "
            "Start with the story immediately."
        )
    )

    factual_section = ""

    if factual_required:
        if not factual_research or not claims_ledger:
            raise ValueError(
                "Factual research and claims ledger are required."
            )

        approved_claims = [
            item
            for item in claims_ledger.get("claims", [])
            if item.get("verification_status") == "approved"
        ]

        factual_section = f"""
--------------------------------------------------
APPROVED FACTUAL SOURCE PACK
--------------------------------------------------

RESEARCH DOSSIER:
{json.dumps(
    factual_research,
    ensure_ascii=True,
    indent=2
)}

APPROVED CLAIMS LEDGER:
{json.dumps(
    approved_claims,
    ensure_ascii=True,
    indent=2
)}

FACTUAL GROUNDING RULES:
- Use only claims marked verification_status="approved".
- Attach the supporting claim IDs to every factual narration block.
- Every non-CTA narration block must include at least one claim ID.
- Do not add facts that are absent from the approved claims ledger.
- Preserve attribution for allegations, disputed claims, quotations,
  interpretations, and legal conclusions.
- Never intensify certainty or infer private motive.
- Never invent dialogue, quotations, precise numbers, dates, or events.
"""

    # Legacy Hiddenova profile rule uses the exact word "Hiddenova".
    # Keep this comment so the original contract remains traceable.

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

STORY RULES:
{json.dumps(
    script_policy.get("story_rules", []),
    indent=2,
    ensure_ascii=True
)}

--------------------------------------------------
SELECTED IDEA
--------------------------------------------------

Title:
{selected_idea["title"]}

Summary:
{selected_idea["summary"]}

Target Audience:
{selected_idea["target_audience"]}

Potential:
{selected_idea["potential"]}

Difficulty:
{selected_idea["difficulty"]}

{factual_section}

{revision_section}

--------------------------------------------------
EDITORIAL STANDARD
--------------------------------------------------

Build the documentary around ONE clear narrative spine.

- Open with one concrete event, object, decision, or
  moment the viewer can visualize immediately.
- Reveal the strongest counterintuitive fact, paradox,
  turning point, or consequence within the first
  120 narration words.
- The hook must create tension. The introduction must
  advance the story instead of restating the hook.
{brand_rule}
- Organize every main section as the next causal step,
  escalation, consequence, turning point, or reveal.
- Prefer specific mechanisms, decisions, constraints,
  and consequences over broad descriptions.
- Use only facts supported by the approved source pack.
- Explain jargon at first use and keep the language
  accessible to a global English-speaking audience.
- Avoid generic documentary filler and repeated summaries.
- Do not use list-like exposition when a cause-and-effect
  sequence can carry the explanation.
- End each section with a reason to continue into the next.
- The conclusion must deliver a final implication, not
  merely summarize every section.

--------------------------------------------------
OUTPUT REQUIREMENTS
--------------------------------------------------

NARRATION LENGTH REQUIREMENTS:

- Total narration word count across hook, introduction,
  all main sections, conclusion, and call_to_action
  MUST be between {target_word_count_min} and
  {target_word_count_max} words.
- Target runtime: {script_policy["estimated_duration_label"]}.
- Set estimated_duration to exactly
  "{script_policy["estimated_duration_label"]}".
- Hook target: 70 to 110 words.
- Introduction target: 90 to 140 words.
- Use {script_policy["main_section_min"]} to
  {script_policy["main_section_max"]} main sections.
- Conclusion target: 80 to 120 words.
- Call to action target: 25 to 45 words.
- The call to action MUST explicitly ask viewers to comment,
  like, and subscribe. Keep it natural and concise.
- Do not repeat explanations merely to increase length.
- Visual direction text does not count toward narration
  length.

Return ONLY valid JSON.
Do NOT return markdown.
Do NOT wrap JSON inside code blocks.
Do NOT explain anything.

Use EXACTLY this structure:

{json.dumps(required_schema, indent=2)}

Every narration field MUST be a single string.
Never return narration as an array.
Never rename any field.
Return JSON only.
""".strip()
