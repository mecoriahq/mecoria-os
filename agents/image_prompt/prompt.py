import json
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent


def load_text_file(filename: str) -> str:
    file_path = BASE_DIR / filename

    if not file_path.exists():
        raise FileNotFoundError(f"Required file not found: {file_path}")

    return file_path.read_text(encoding="utf-8")


def build_prompt(visual_brief_data: dict, qa_data: dict) -> str:
    system_prompt = load_text_file("system.md")
    workflow = load_text_file("workflow.md")

    required_schema = {
        "openai": {
            "model": "gpt-image-1",
            "prompt": "string",
            "size": "1536x1024",
            "quality": "high",
            "style": "cinematic"
        },
        "flux": {
            "model": "flux-kontext-pro",
            "prompt": "string",
            "negative_prompt": "string"
        },
        "midjourney": {
            "model": "v7",
            "prompt": "string",
            "aspect_ratio": "16:9",
            "stylize": "250"
        }
    }

    return f"""
{system_prompt}

{workflow}

--------------------------------------------------
VISUAL BRIEF AGENT OUTPUT
--------------------------------------------------

{json.dumps(visual_brief_data, ensure_ascii=False, indent=2)}

--------------------------------------------------
QA AGENT OUTPUT
--------------------------------------------------

{json.dumps(qa_data, ensure_ascii=False, indent=2)}

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

- openai.prompt must be a detailed natural-language image prompt.
- openai.size must be one of: 1024x1024, 1536x1024, 1024x1536.
- openai.quality should be "high".
- openai.style should describe the overall image style.
- flux.prompt should be concise, dense, and visual.
- flux.negative_prompt should describe unwanted visual artifacts and mistakes.
- midjourney.prompt should include the visual concept and Midjourney-style parameters naturally.
- midjourney.aspect_ratio should be "16:9".
- midjourney.stylize should be a string number.
- Preserve the Visual Brief intent.
- Do not create a new visual strategy.
- Do not generate an image.
- Do not rewrite the script.
- Do not create SEO metadata.

Return JSON only.
""".strip()