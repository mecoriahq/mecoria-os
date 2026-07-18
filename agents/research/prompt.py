import json


def build_research_prompt(
    channel_name: str,
    channel_description: str,
    editorial_profile: dict | None = None,
) -> str:
    profile = editorial_profile or {}
    topic_strategy = profile.get("topic_strategy", {})

    required_schema = {
        "ideas": [
            {
                "id": 1,
                "title": "string",
                "summary": "string",
                "target_audience": "string",
                "potential": "string",
                "difficulty": "Easy | Medium | Hard",
                "story_type": "string",
                "subject": "string",
                "core_question": "string",
                "source_feasibility": "High | Medium | Low",
                "risk_level": "Low | Medium | High",
            }
        ]
    }

    return f"""
Generate exactly 10 high-potential YouTube documentary ideas.

CHANNEL NAME:
{channel_name}

CHANNEL DESCRIPTION:
{channel_description}

CHANNEL PROMISE:
{topic_strategy.get("channel_promise", channel_description)}

ALLOWED CONTENT PILLARS:
{json.dumps(
    topic_strategy.get("allowed_pillars", []),
    indent=2,
    ensure_ascii=True,
)}

SELECTION RULES:
{json.dumps(
    topic_strategy.get("selection_rules", []),
    indent=2,
    ensure_ascii=True,
)}

FORBIDDEN ANGLES:
{json.dumps(
    topic_strategy.get("forbidden_angles", []),
    indent=2,
    ensure_ascii=True,
)}

Return ONLY valid JSON.
Do not include Markdown.
Do not include explanations.
Do not wrap JSON in code blocks.

Use this structure:

{json.dumps(required_schema, indent=2)}

Rules:
- Return exactly 10 ideas.
- Each id must be unique from 1 to 10.
- Titles must be specific, accurate, and clickable.
- Summaries must be one sentence.
- Avoid duplicate subjects and duplicate story angles.
- Prefer source-rich stories that can support a serious documentary.
- risk_level must reflect factual, reputational, legal, or privacy risk.
- Do not invent people, companies, scandals, or historical events.
- Write in English.
""".strip()
