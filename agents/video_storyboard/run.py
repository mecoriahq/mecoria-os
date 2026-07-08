import argparse
import json
from pathlib import Path

from dotenv import load_dotenv
from jsonschema import validate
from openai import OpenAI

from output import save_output


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent.parent

DEFAULT_CHANNEL = "hiddenova"


def load_json(file_path: Path) -> dict:
    if not file_path.exists():
        raise FileNotFoundError(f"Required file not found: {file_path}")

    return json.loads(file_path.read_text(encoding="utf-8"))


def load_optional_json(file_path: Path) -> dict | None:
    if not file_path.exists():
        return None

    return json.loads(file_path.read_text(encoding="utf-8"))


def load_schema() -> dict:
    return load_json(BASE_DIR / "schema.json")


def get_script_latest_path(channel: str) -> Path:
    return PROJECT_ROOT / "agents" / "script" / "output" / channel.lower() / "latest.json"


def get_publisher_latest_path(channel: str) -> Path:
    return PROJECT_ROOT / "agents" / "publisher" / "output" / channel.lower() / "latest.json"


def get_voice_latest_path(channel: str) -> Path:
    return PROJECT_ROOT / "agents" / "voice" / "output" / channel.lower() / "latest.json"


def get_latest_review_path(channel: str) -> Path | None:
    review_dir = PROJECT_ROOT / "records" / "reviews" / channel.lower()

    if not review_dir.exists():
        return None

    review_files = sorted(
        review_dir.glob("*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True
    )

    if not review_files:
        return None

    return review_files[0]


def get_relative_path(path: Path | None) -> str | None:
    if path is None:
        return None

    return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")


def extract_sections(script_data: dict, voice_data: dict) -> list[dict]:
    voice_sections = voice_data["voice_package"]["narration"]["sections"]
    section_map = {
        section["title"]: section
        for section in voice_sections
    }

    script = script_data["script"]

    sections = []

    sections.append({
        "sequence": 1,
        "section_type": "hook",
        "title": "Hook",
        "narration": script["hook"]["narration"],
        "visual_direction": None,
        "word_count": section_map.get("Hook", {}).get("word_count")
    })

    sections.append({
        "sequence": 2,
        "section_type": "introduction",
        "title": "Introduction",
        "narration": script["introduction"]["narration"],
        "visual_direction": None,
        "word_count": section_map.get("Introduction", {}).get("word_count")
    })

    sequence = 3

    for section in script["main_sections"]:
        sections.append({
            "sequence": sequence,
            "section_type": "main_section",
            "title": section["title"],
            "narration": section["narration"],
            "visual_direction": section["visual_direction"],
            "word_count": section_map.get(section["title"], {}).get("word_count")
        })
        sequence += 1

    sections.append({
        "sequence": sequence,
        "section_type": "conclusion",
        "title": "Conclusion",
        "narration": script["conclusion"]["narration"],
        "visual_direction": None,
        "word_count": section_map.get("Conclusion", {}).get("word_count")
    })
    sequence += 1

    sections.append({
        "sequence": sequence,
        "section_type": "call_to_action",
        "title": "Call to Action",
        "narration": script["call_to_action"]["narration"],
        "visual_direction": None,
        "word_count": section_map.get("Call to Action", {}).get("word_count")
    })

    return sections


def build_prompt(
    script_data: dict,
    publisher_data: dict,
    voice_data: dict,
    review_data: dict | None
) -> str:
    sections = extract_sections(
        script_data=script_data,
        voice_data=voice_data
    )

    title = publisher_data["publishing_package"]["video_metadata"]["title"]
    review_summary = review_data["quality_assessment"] if review_data else {}

    return f"""
You are the Video Storyboard Agent for Mecoria Media's Hiddenova channel.

Goal:
Create a premium YouTube documentary storyboard that fixes the main weakness of the first test video: it had narration and one animated image, but no real video flow, b-roll, graphics, or animations.

Channel style:
- Hidden systems behind everyday life
- Premium documentary feel
- Serious but not boring
- Visually clear, cinematic, explanatory
- Avoid generic AI slideshow look
- Avoid using fake readable text in generated visuals
- Use section-based scene planning

Video title:
{title}

Review feedback:
{json.dumps(review_summary, indent=2, ensure_ascii=False)}

Script sections:
{json.dumps(sections, indent=2, ensure_ascii=False)}

Return valid JSON only.

Required JSON shape:
{{
  "storyboard_summary": "...",
  "visual_strategy": {{
    "overall_style": "...",
    "editing_pace": "...",
    "asset_mix": ["..."],
    "quality_notes": ["..."]
  }},
  "sections": [
    {{
      "sequence": 1,
      "section_type": "hook",
      "title": "Hook",
      "estimated_duration_seconds": 45,
      "section_goal": "...",
      "scenes": [
        {{
          "scene_number": 1,
          "visual_type": "b_roll | motion_graphic | map_animation | diagram | generated_image | stock_video | text_overlay",
          "scene_description": "...",
          "asset_strategy": "...",
          "camera_motion": "...",
          "on_screen_text": "...",
          "transition": "...",
          "quality_notes": "..."
        }}
      ]
    }}
  ],
  "production_notes": {{
    "minimum_assets_needed": 0,
    "priority_assets": ["..."],
    "next_agent": "visual_asset_plan"
  }}
}}

Rules:
- Create 2 to 5 scenes per section depending on section length.
- Use more than one visual type across the video.
- Include b-roll, motion graphics, diagrams, and map/system animations where useful.
- On-screen text must be short and intentional.
- Do not create fake labels, fake UI, fake barcodes, fake brand logos, or fake documents.
- Make the video feel like a real documentary, not a static narrated image.
"""


def extract_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}") + 1

        if start == -1 or end == 0:
            raise ValueError("OpenAI response does not contain valid JSON.")

        return json.loads(text[start:end])


def generate_storyboard(prompt: str) -> dict:
    client = OpenAI()

    response = client.chat.completions.create(
        model="gpt-5.5",
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ],
        max_completion_tokens=12000,
        response_format={
            "type": "json_object"
        }
    )

    content = response.choices[0].message.content

    if not content:
        raise ValueError("OpenAI returned an empty response.")

    return extract_json(content)


def normalize_output(
    channel: str,
    storyboard_data: dict,
    script_path: Path,
    publisher_path: Path,
    voice_path: Path,
    review_path: Path | None
) -> dict:
    sections = storyboard_data["sections"]

    total_scenes = sum(
        len(section["scenes"])
        for section in sections
    )

    return {
        "agent": "video_storyboard",
        "version": "1.0",
        "channel": channel,
        "status": "storyboard_ready",
        "storyboard": {
            "storyboard_summary": storyboard_data["storyboard_summary"],
            "visual_strategy": storyboard_data["visual_strategy"],
            "sections": sections,
            "production_notes": storyboard_data["production_notes"]
        },
        "summary": {
            "section_count": len(sections),
            "scene_count": total_scenes,
            "next_agent": "visual_asset_plan"
        },
        "source": {
            "source_agents": [
                "script",
                "publisher",
                "voice",
                "review"
            ],
            "script_reference": get_relative_path(script_path),
            "publisher_reference": get_relative_path(publisher_path),
            "voice_reference": get_relative_path(voice_path),
            "review_reference": get_relative_path(review_path)
        },
        "metadata": {
            "next_agent": "visual_asset_plan"
        }
    }


def dry_run(
    script_data: dict,
    publisher_data: dict,
    voice_data: dict,
    review_data: dict | None
) -> None:
    sections = extract_sections(
        script_data=script_data,
        voice_data=voice_data
    )

    print("Video Storyboard Agent dry-run completed.")
    print(f"Channel: {script_data['channel']}")
    print(f"Video title: {publisher_data['publishing_package']['video_metadata']['title']}")
    print(f"Sections available: {len(sections)}")
    print(f"Review loaded: {review_data is not None}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a section-based video storyboard for premium documentary production."
    )

    parser.add_argument(
        "--channel",
        default=DEFAULT_CHANNEL,
        help="Channel name. Default: hiddenova"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate inputs without calling OpenAI."
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    load_dotenv(PROJECT_ROOT / ".env")

    script_path = get_script_latest_path(args.channel)
    publisher_path = get_publisher_latest_path(args.channel)
    voice_path = get_voice_latest_path(args.channel)
    review_path = get_latest_review_path(args.channel)

    script_data = load_json(script_path)
    publisher_data = load_json(publisher_path)
    voice_data = load_json(voice_path)
    review_data = load_optional_json(review_path) if review_path else None

    if args.dry_run:
        dry_run(
            script_data=script_data,
            publisher_data=publisher_data,
            voice_data=voice_data,
            review_data=review_data
        )
        return

    prompt = build_prompt(
        script_data=script_data,
        publisher_data=publisher_data,
        voice_data=voice_data,
        review_data=review_data
    )

    raw_storyboard = generate_storyboard(prompt)

    final_output = normalize_output(
        channel=args.channel,
        storyboard_data=raw_storyboard,
        script_path=script_path,
        publisher_path=publisher_path,
        voice_path=voice_path,
        review_path=review_path
    )

    schema = load_schema()
    validate(instance=final_output, schema=schema)

    latest_path = save_output(
        channel=final_output["channel"],
        data=final_output
    )

    print("Video Storyboard Agent completed successfully.")
    print(f"Output saved to: {latest_path}")


if __name__ == "__main__":
    main()
