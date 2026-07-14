import argparse
import json
import time
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


def load_schema() -> dict:
    return load_json(BASE_DIR / "schema.json")


def get_storyboard_latest_path(channel: str) -> Path:
    return PROJECT_ROOT / "agents" / "video_storyboard" / "output" / channel.lower() / "latest.json"


def get_relative_path(path: Path) -> str:
    return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")


def get_all_scenes(storyboard_data: dict) -> list[dict]:
    scenes = []

    for section in storyboard_data["storyboard"]["sections"]:
        for scene in section["scenes"]:
            scenes.append({
                "section_sequence": section["sequence"],
                "section_title": section["title"],
                "scene_number": scene["scene_number"],
                "visual_type": scene["visual_type"],
                "scene_description": scene["scene_description"],
                "asset_strategy": scene["asset_strategy"],
                "camera_motion": scene["camera_motion"],
                "on_screen_text": scene["on_screen_text"],
                "transition": scene["transition"],
                "quality_notes": scene["quality_notes"]
            })

    return scenes


def count_visual_types(scenes: list[dict]) -> dict:
    counts = {}

    for scene in scenes:
        visual_type = scene["visual_type"]
        counts[visual_type] = counts.get(visual_type, 0) + 1

    return counts


def build_prompt(storyboard_data: dict) -> str:
    scenes = get_all_scenes(storyboard_data)

    return f"""
You are the Visual Asset Plan Agent for Mecoria Media's Hiddenova channel.

Goal:
Convert a 54-scene documentary storyboard into a practical reusable visual asset plan.

Important:
Do not create one asset per scene.
Group scenes into reusable assets where possible.
Target 15 to 30 reusable assets for the first public-quality MVP.
Prioritize assets that make the video feel like a real documentary, not a static AI slideshow.

Channel quality bar:
- Premium documentary style
- Real b-roll where possible
- Clean motion graphics
- Simple explanatory diagrams
- Minimal text overlays
- No fake readable labels, fake barcodes, fake UI, fake brand logos, fake documents, or fake private data
- Use generated images only when real/stock footage is unavailable or for atmospheric inserts
- Stock footage must be licensed before public use

Storyboard summary:
{json.dumps(storyboard_data["summary"], indent=2, ensure_ascii=False)}

Visual strategy:
{json.dumps(storyboard_data["storyboard"]["visual_strategy"], indent=2, ensure_ascii=False)}

Scenes:
{json.dumps(scenes, indent=2, ensure_ascii=False)}

Return valid JSON only.

Required JSON shape:
{{
  "plan_summary": "...",
  "production_strategy": {{
    "target_asset_count": 24,
    "asset_reuse_strategy": "...",
    "recommended_first_build": "...",
    "quality_risks": ["..."]
  }},
  "reusable_assets": [
    {{
      "asset_id": "A001",
      "asset_type": "stock_video | b_roll | generated_image | motion_graphic | diagram | map_animation | text_overlay",
      "priority": "high | medium | low",
      "scenes_covered": [1, 2, 3],
      "purpose": "...",
      "production_method": "licensed_stock | ai_generated | internal_graphic | simple_text_overlay | manual_edit",
      "creative_brief": "...",
      "ai_image_prompt": null,
      "stock_search_query": null,
      "motion_graphic_instructions": null,
      "diagram_instructions": null,
      "editing_notes": "...",
      "quality_constraints": ["..."]
    }}
  ],
  "scene_asset_map": [
    {{
      "section_sequence": 1,
      "scene_number": 1,
      "primary_asset_id": "A001",
      "supporting_asset_ids": ["A002"]
    }}
  ],
  "next_steps": {{
    "next_agent": "visual_asset_production",
    "first_assets_to_create": ["A001", "A002"],
    "manual_assets_needed": ["..."]
  }}
}}

Rules:
- Every storyboard scene must be mapped in scene_asset_map.
- reusable_assets must be fewer than total scenes.
- Prefer reusable asset groups.
- For stock_video/b_roll assets, include clear stock_search_query.
- For generated_image assets, include safe AI prompt with no readable text/logos/barcodes.
- For motion_graphic assets, include clear animation instructions.
- For diagram/map assets, include clear layout instructions.
- Keep on-screen text short and intentional.
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


def generate_asset_plan(prompt: str) -> dict:
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
    asset_plan_data: dict,
    storyboard_path: Path,
    storyboard_data: dict
) -> dict:
    reusable_assets = asset_plan_data["reusable_assets"]
    scene_asset_map = asset_plan_data["scene_asset_map"]

    high_priority_count = sum(
        1 for asset in reusable_assets
        if asset["priority"] == "high"
    )

    return {
        "agent": "visual_asset_plan",
        "version": "1.0",
        "channel": channel,
        "status": "asset_plan_ready",
        "asset_plan": {
            "plan_summary": asset_plan_data["plan_summary"],
            "production_strategy": asset_plan_data["production_strategy"],
            "reusable_assets": reusable_assets,
            "scene_asset_map": scene_asset_map,
            "next_steps": asset_plan_data["next_steps"]
        },
        "summary": {
            "storyboard_scene_count": storyboard_data["summary"]["scene_count"],
            "reusable_asset_count": len(reusable_assets),
            "mapped_scene_count": len(scene_asset_map),
            "high_priority_asset_count": high_priority_count,
            "next_agent": "visual_asset_production"
        },
        "source": {
            "source_agents": [
                "video_storyboard"
            ],
            "storyboard_reference": get_relative_path(storyboard_path)
        },
        "metadata": {
            "next_agent": "visual_asset_production"
        }
    }


def dry_run(storyboard_data: dict) -> None:
    scenes = get_all_scenes(storyboard_data)
    visual_type_counts = count_visual_types(scenes)

    print("Visual Asset Plan Agent dry-run completed.")
    print(f"Channel: {storyboard_data['channel']}")
    print(f"Storyboard sections: {storyboard_data['summary']['section_count']}")
    print(f"Storyboard scenes: {storyboard_data['summary']['scene_count']}")
    print("Visual type distribution:")

    for visual_type, count in sorted(visual_type_counts.items()):
        print(f"- {visual_type}: {count}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a reusable visual asset plan from video storyboard output."
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



def normalize_scene_references(payload: dict) -> None:
    def normalize_scene_list(values):
        normalized = []

        if not isinstance(values, list):
            return normalized

        for value in values:
            scene_number = None

            if isinstance(value, bool):
                continue

            if isinstance(value, int):
                scene_number = value

            elif isinstance(value, float):
                scene_number = int(value)

            elif isinstance(value, str):
                cleaned = value.strip()

                if not cleaned:
                    continue

                try:
                    scene_number = int(float(cleaned))
                except ValueError:
                    continue

            if scene_number is None:
                continue

            if scene_number not in normalized:
                normalized.append(scene_number)

        return normalized

    def walk(obj):
        if isinstance(obj, dict):
            if "scenes_covered" in obj:
                obj["scenes_covered"] = normalize_scene_list(obj.get("scenes_covered"))

            for value in obj.values():
                walk(value)

        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    walk(payload)

def main() -> None:
    args = parse_args()

    load_dotenv(PROJECT_ROOT / ".env")

    storyboard_path = get_storyboard_latest_path(args.channel)
    storyboard_data = load_json(storyboard_path)

    if args.dry_run:
        dry_run(storyboard_data=storyboard_data)
        return

    prompt = build_prompt(storyboard_data=storyboard_data)
    raw_asset_plan = None
    last_generation_error = None

    for generation_attempt in range(1, 4):
        try:
            raw_asset_plan = generate_asset_plan(prompt)

            if raw_asset_plan:
                break

        except ValueError as error:
            last_generation_error = error
            error_text = str(error).lower()

            if "empty response" not in error_text or generation_attempt == 3:
                raise

            print(
                "VISUAL_ASSET_PLAN_EMPTY_RESPONSE_RETRY:"
                f" attempt={generation_attempt}"
            )
            time.sleep(5)

    if raw_asset_plan is None:
        raise last_generation_error or ValueError("Visual asset plan generation failed.")


    final_output = normalize_output(
        channel=args.channel,
        asset_plan_data=raw_asset_plan,
        storyboard_path=storyboard_path,
        storyboard_data=storyboard_data
    )

    schema = load_schema()
    normalize_scene_references(final_output)
    validate(instance=final_output, schema=schema)

    latest_path = save_output(
        channel=final_output["channel"],
        data=final_output
    )

    print("Visual Asset Plan Agent completed successfully.")
    print(f"Output saved to: {latest_path}")


if __name__ == "__main__":
    main()
