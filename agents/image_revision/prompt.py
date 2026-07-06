import json
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent


def load_text_file(filename: str) -> str:
    file_path = BASE_DIR / filename

    if not file_path.exists():
        raise FileNotFoundError(f"Required file not found: {file_path}")

    return file_path.read_text(encoding="utf-8")


def build_prompt(
    image_prompt_data: dict,
    image_generation_data: dict,
    image_qa_data: dict
) -> str:
    system_prompt = load_text_file("system.md")
    workflow = load_text_file("workflow.md")

    required_schema = {
        "revision_reason": "string",
        "providers": {
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
    }

    return f"""
{system_prompt}

{workflow}

--------------------------------------------------
ORIGINAL IMAGE PROMPT OUTPUT
--------------------------------------------------

{json.dumps(image_prompt_data, ensure_ascii=False, indent=2)}

--------------------------------------------------
IMAGE GENERATION OUTPUT
--------------------------------------------------

{json.dumps(image_generation_data, ensure_ascii=False, indent=2)}

--------------------------------------------------
IMAGE QA OUTPUT
--------------------------------------------------

{json.dumps(image_qa_data, ensure_ascii=False, indent=2)}

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

- revision_reason must summarize why the image prompt is being revised.
- Fix every issue reported by Image QA.
- Preserve the original Visual Brief intent.
- Make the main subject larger and clearer if subject visibility is weak.
- Reduce clutter if composition quality is weak.
- Remove all text, numbers, signage, logos, or watermarks if text_absence or logo_absence is weak.
- Reduce UI-like overlays if standard_alignment is weak.
- Keep OpenAI prompt detailed and natural-language.
- Keep Flux prompt concise, dense, and visual.
- Keep Midjourney prompt provider-appropriate with parameters.
- Do not generate an image.
- Do not create a new visual strategy.
- Do not ignore QA feedback.

Return JSON only.
""".strip()