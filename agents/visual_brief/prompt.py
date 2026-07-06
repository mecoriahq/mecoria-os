import json
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent


def load_text_file(filename: str) -> str:
    file_path = BASE_DIR / filename

    if not file_path.exists():
        raise FileNotFoundError(f"Required file not found: {file_path}")

    return file_path.read_text(encoding="utf-8")


def build_prompt(script_data: dict, seo_data: dict, qa_data: dict) -> str:
    system_prompt = load_text_file("system.md")
    workflow = load_text_file("workflow.md")

    required_schema = {
        "objective": "string",
        "target_emotion": "string",
        "audience": "string",
        "story_moment": "string",
        "headline_candidates": [
            "string",
            "string",
            "string"
        ],
        "subject": {
            "description": "string",
            "style": "string",
            "details": "string"
        },
        "background": {
            "description": "string",
            "environment": "string",
            "depth": "string"
        },
        "composition": {
            "layout": "string",
            "camera_angle": "string",
            "framing": "string",
            "visual_focus": "string"
        },
        "lighting": {
            "style": "string",
            "direction": "string",
            "contrast": "string"
        },
        "color": {
            "palette": "string",
            "accent": "string"
        },
        "constraints": {
            "avoid": [
                "string",
                "string"
            ],
            "must_include": [
                "string",
                "string"
            ]
        }
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

- objective must explain the visual goal.
- target_emotion must be one primary viewer emotion.
- audience must describe who the visual is designed for.
- story_moment must describe the exact visual moment to capture.
- headline_candidates must contain 3 to 5 short visual text options.
- subject.description must describe the main visual subject.
- subject.style must describe the visual style of the subject.
- subject.details must provide concrete image-ready details.
- background.description must describe the environment.
- background.environment must describe the setting type.
- background.depth must describe foreground/background depth.
- composition.layout must describe object placement.
- composition.camera_angle must describe perspective.
- composition.framing must describe crop and spacing.
- composition.visual_focus must describe where the viewer looks first.
- lighting.style must describe lighting mood.
- lighting.direction must describe light source direction.
- lighting.contrast must describe contrast level.
- color.palette must describe the main palette.
- color.accent must describe accent colors.
- constraints.avoid must contain 2 to 6 things to avoid.
- constraints.must_include must contain 2 to 6 required visual elements.
- Do not generate an image prompt.
- Do not generate SEO metadata.
- Do not rewrite the script.
- Use the QA issues and recommendations when creating the visual brief.

Return JSON only.
""".strip()