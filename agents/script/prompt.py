import json
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent


def load_text_file(filename: str) -> str:
    file_path = BASE_DIR / filename

    if not file_path.exists():
        raise FileNotFoundError(f"Required file not found: {file_path}")

    return file_path.read_text(encoding="utf-8")


def build_prompt(
    research_data: dict,
    selected_idea: dict,
    target_word_count_min: int = 800,
    target_word_count_max: int = 1300
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

--------------------------------------------------
OUTPUT REQUIREMENTS
--------------------------------------------------

NARRATION LENGTH REQUIREMENTS:

- Total narration word count across hook, introduction,
  all main sections, conclusion, and call_to_action
  MUST be between {target_word_count_min} and
  {target_word_count_max} words.
- Target runtime: approximately 6 to 9 minutes.
- Hook target: 60 to 100 words.
- Introduction target: 80 to 140 words.
- Use 5 to 7 main sections.
- Combined main section narration target:
  550 to 900 words.
- Conclusion target: 60 to 100 words.
- Call to action target: 25 to 50 words.
- Do not repeat explanations merely to increase length.
- Visual direction text does not count toward narration length.

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