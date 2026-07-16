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


def build_prompt(script_data: dict) -> str:
    system_prompt = load_text_file("system.md")
    workflow = load_text_file("workflow.md")

    script = script_data["script"]

    required_schema = {
        "video_title": "string",
        "description": "string",
        "tags": [
            "string"
        ],
        "keywords": [
            "string"
        ],
        "hashtags": [
            "#string"
        ],
        "thumbnail_text": "string",
        "chapters": [],
        "seo_score": 0
    }

    return f"""
{system_prompt}

{workflow}

--------------------------------------------------
SCRIPT DATA
--------------------------------------------------

Script Title:
{script["title"]}

Format:
{script["format"]}

Estimated Duration:
{script["estimated_duration"]}

Hook:
{script["hook"]["narration"]}

Introduction:
{script["introduction"]["narration"]}

Main Sections:
{json.dumps(
    script["main_sections"],
    ensure_ascii=False,
    indent=2
)}

Conclusion:
{script["conclusion"]["narration"]}

Call To Action:
{script["call_to_action"]["narration"]}

--------------------------------------------------
TITLE AND THUMBNAIL STANDARD
--------------------------------------------------

- The title must communicate a clear viewer question,
  consequence, conflict, or surprising mechanism.
- Prefer direct language over abstract documentary
  phrases.
- The title must accurately promise what the script
  delivers.
- The thumbnail text must be 2 to 4 words.
- The thumbnail text must be ALL CAPS.
- It must communicate one direct tension, decision,
  consequence, or reveal that is visually understandable
  without reading the title.
- Do not repeat the full title in the thumbnail.
- Avoid vague phrases such as "THE HIDDEN TRUTH",
  "SECRET SYSTEM", or "WHAT THEY DON'T TELL YOU".
- Title and thumbnail must work as one package:
  one creates the question and the other sharpens the
  tension.

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

- video_title must be optimized for YouTube discovery,
  clarity, and curiosity.
- description must be clear, engaging, and suitable for
  YouTube.
- Do not add estimated timestamps to the description.
- tags must contain 10 to 20 relevant YouTube tags.
- keywords must contain 8 to 15 SEO keywords.
- hashtags must contain 3 to 5 hashtags and each must
  start with #.
- thumbnail_text must follow the title and thumbnail
  standard above.
- chapters MUST be an empty array. Actual chapter times
  are generated only after narration audio is assembled.
- seo_score must be an integer between 0 and 100.

Never rename any field.

Return JSON only.
""".strip()
