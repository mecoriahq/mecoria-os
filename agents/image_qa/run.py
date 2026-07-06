import base64
import json
import sys
from pathlib import Path

from dotenv import load_dotenv
from jsonschema import validate
from openai import OpenAI

from output import save_output
from prompt import build_prompt


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent.parent

sys.path.insert(0, str(PROJECT_ROOT))

from core.execution.context import load_or_create_context, apply_image_qa_result, save_context


DEFAULT_CHANNEL = "hiddenova"
APPROVAL_THRESHOLD = 80


def load_json(file_path: Path) -> dict:
    if not file_path.exists():
        raise FileNotFoundError(f"Required file not found: {file_path}")

    return json.loads(file_path.read_text(encoding="utf-8"))


def load_schema() -> dict:
    return load_json(BASE_DIR / "schema.json")


def get_image_generation_latest_path(channel: str) -> Path:
    return PROJECT_ROOT / "agents" / "image_generation" / "output" / channel.lower() / "latest.json"


def get_image_path(image_generation_data: dict) -> Path:
    relative_path = image_generation_data["image"]["relative_path"]
    return PROJECT_ROOT / relative_path


def get_png_dimensions(image_path: Path) -> tuple[int, int]:
    data = image_path.read_bytes()

    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("Image is not a valid PNG file.")

    width = int.from_bytes(data[16:20], "big")
    height = int.from_bytes(data[20:24], "big")

    return width, height


def make_check(status: str, score: int) -> dict:
    return {
        "status": status,
        "score": score
    }


def run_technical_checks(image_path: Path, expected_size: str) -> dict:
    file_exists = image_path.exists()
    file_readable = False
    format_valid = False
    size_valid = False

    if file_exists:
        try:
            width, height = get_png_dimensions(image_path)
            file_readable = True
            format_valid = image_path.suffix.lower() == ".png"

            actual_size = f"{width}x{height}"
            size_valid = actual_size == expected_size
        except Exception:
            file_readable = False

    return {
        "file_exists": make_check("pass" if file_exists else "fail", 100 if file_exists else 0),
        "file_readable": make_check("pass" if file_readable else "fail", 100 if file_readable else 0),
        "format_valid": make_check("pass" if format_valid else "fail", 100 if format_valid else 0),
        "size_valid": make_check("pass" if size_valid else "warning", 100 if size_valid else 70)
    }


def technical_checks_passed(technical_checks: dict) -> bool:
    return all(check["status"] != "fail" for check in technical_checks.values())


def extract_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}") + 1

        if start == -1 or end == 0:
            raise ValueError("OpenAI response does not contain valid JSON.")

        return json.loads(text[start:end])


def encode_image_as_data_url(image_path: Path) -> str:
    image_base64 = base64.b64encode(image_path.read_bytes()).decode("utf-8")
    return f"data:image/png;base64,{image_base64}"


def generate_visual_qa(prompt: str, image_path: Path) -> dict:
    client = OpenAI()
    image_data_url = encode_image_as_data_url(image_path)

    response = client.chat.completions.create(
        model="gpt-5.5",
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": prompt
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": image_data_url
                        }
                    }
                ]
            }
        ],
        max_completion_tokens=4000,
        response_format={
            "type": "json_object"
        }
    )

    content = response.choices[0].message.content

    if not content:
        raise ValueError("OpenAI returned an empty response.")

    return extract_json(content)


def build_rejected_output(image_generation_data: dict, image_path: Path, technical_checks: dict) -> dict:
    return {
        "agent": "image_qa",
        "version": "1.0",
        "channel": image_generation_data["channel"],
        "status": "rejected",
        "overall_score": 0,
        "technical_checks": technical_checks,
        "visual_checks": {
            "subject_visibility": make_check("fail", 0),
            "composition_quality": make_check("fail", 0),
            "lighting_quality": make_check("fail", 0),
            "text_absence": make_check("fail", 0),
            "logo_absence": make_check("fail", 0),
            "standard_alignment": make_check("fail", 0)
        },
        "issues": [
            {
                "field": "technical_checks",
                "severity": "high",
                "message": "Image failed technical validation."
            }
        ],
        "recommendations": [
            {
                "field": "image_generation",
                "suggestion": "Regenerate the image and verify the output file."
            }
        ],
        "source": {
            "agent": image_generation_data["agent"],
            "image_path": str(image_path.relative_to(PROJECT_ROOT)).replace("\\", "/")
        },
        "metadata": {
            "source_agents": [
                "image_generation"
            ],
            "next_agent": None
        }
    }


def normalize_output(
    image_generation_data: dict,
    image_path: Path,
    technical_checks: dict,
    visual_qa_data: dict
) -> dict:
    overall_score = visual_qa_data["overall_score"]
    status = "approved" if overall_score >= APPROVAL_THRESHOLD else "rejected"
    next_agent = "publisher" if status == "approved" else None

    return {
        "agent": "image_qa",
        "version": "1.0",
        "channel": image_generation_data["channel"],
        "status": status,
        "overall_score": overall_score,
        "technical_checks": technical_checks,
        "visual_checks": visual_qa_data["visual_checks"],
        "issues": visual_qa_data["issues"],
        "recommendations": visual_qa_data["recommendations"],
        "source": {
            "agent": image_generation_data["agent"],
            "image_path": str(image_path.relative_to(PROJECT_ROOT)).replace("\\", "/")
        },
        "metadata": {
            "source_agents": [
                "image_generation"
            ],
            "next_agent": next_agent
        }
    }


def update_execution_context(image_qa_data: dict) -> None:
    context = load_or_create_context(
        channel=image_qa_data["channel"],
        pipeline="image",
        max_attempts=3
    )

    context = apply_image_qa_result(
        context=context,
        image_qa_data=image_qa_data
    )

    save_context(context)


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")

    image_generation_path = get_image_generation_latest_path(DEFAULT_CHANNEL)
    image_generation_data = load_json(image_generation_path)

    image_path = get_image_path(image_generation_data)
    expected_size = image_generation_data["image"]["size"]

    technical_checks = run_technical_checks(
        image_path=image_path,
        expected_size=expected_size
    )

    if not technical_checks_passed(technical_checks):
        final_output = build_rejected_output(
            image_generation_data=image_generation_data,
            image_path=image_path,
            technical_checks=technical_checks
        )
    else:
        prompt = build_prompt(
            image_generation_data=image_generation_data,
            technical_checks=technical_checks
        )

        visual_qa_data = generate_visual_qa(
            prompt=prompt,
            image_path=image_path
        )

        final_output = normalize_output(
            image_generation_data=image_generation_data,
            image_path=image_path,
            technical_checks=technical_checks,
            visual_qa_data=visual_qa_data
        )

    schema = load_schema()
    validate(instance=final_output, schema=schema)

    update_execution_context(final_output)

    latest_path = save_output(
        channel=image_generation_data["channel"],
        data=final_output
    )

    print("Image QA Agent completed successfully.")
    print(f"Output saved to: {latest_path}")


if __name__ == "__main__":
    main()