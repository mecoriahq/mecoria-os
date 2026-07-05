def build_research_prompt(channel_name: str, channel_description: str) -> str:
    return f"""
Generate exactly 10 high-potential YouTube video ideas.

Channel Name:
{channel_name}

Channel Description:
{channel_description}

Return ONLY valid JSON.

Do not include Markdown.
Do not include explanations.
Do not wrap the JSON in code blocks.

JSON format:

{{
  "ideas": [
    {{
      "id": 1,
      "title": "string",
      "summary": "string",
      "target_audience": "string",
      "potential": "string",
      "difficulty": "Easy | Medium | Hard"
    }}
  ]
}}

Rules:
- Return exactly 10 ideas.
- Each id must be unique from 1 to 10.
- Titles must be specific and clickable.
- Summaries must be one sentence.
- Avoid duplicate ideas.
- Write in English.
"""