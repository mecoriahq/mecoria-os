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
    revision_feedback: dict | None = None
) -> str:
    system_prompt = load_text_file("system.md")
    workflow = load_text_file("workflow.md")

    required_schema = {
        "title": "string",
        "format": "string",
        "estimated_duration": "string",
        "hook": {
            "narration": "string"
        },
        "introduction": {
            "narration": "string"
        },
        "main_sections": [
            {
                "title": "string",
                "narration": "string",
                "visual_direction": "string"
            }
        ],
        "conclusion": {
            "narration": "string"
        },
        "call_to_action": {
            "narration": "string"
        }
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

    return f"""
{system_prompt}

{workflow}

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

{revision_section}

--------------------------------------------------
EDITORIAL STANDARD
--------------------------------------------------

Build the documentary around ONE clear narrative spine.

- Open with one concrete event, object, decision, or
  moment the viewer can visualize immediately.
- Reveal the strongest counterintuitive fact, paradox,
  or consequence within the first 120 narration words.
- The hook must create tension. The introduction must
  advance the story instead of restating the hook.
- The introduction MUST begin with a very short brand/context
  line containing the exact word "Hiddenova" within its first
  25 words, then immediately advance the story.
- Organize every main section as the next causal step,
  escalation, consequence, or reveal.
- Prefer specific mechanisms, decisions, constraints,
  and consequences over broad descriptions.
- Use only facts supported by the supplied research and
  selected idea. Never invent statistics, companies,
  quotations, case studies, regulations, or technical
  details merely to sound specific.
- Explain jargon at first use and keep the language
  accessible to a global English-speaking audience.
- Avoid generic documentary filler such as repeated use
  of "hidden system", "quiet technology",
  "beneath the surface", "modern world",
  "deceptively simple", "invisible", or "trust".
- Avoid repeating the same abstract point using
  different words.
- Do not use list-like exposition when a cause-and-effect
  sequence can carry the explanation.
- End each section with a reason to continue into the
  next section.
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
- Target runtime: 8 to 12 minutes.
- Set estimated_duration to exactly "8-12 minutes".
- Hook target: 70 to 110 words.
- Introduction target: 90 to 140 words.
- Use 5 to 7 main sections.
- Combined main section narration target:
  950 to 1300 words.
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
