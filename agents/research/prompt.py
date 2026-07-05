def build_research_prompt(channel_name: str, channel_description: str) -> str:
    return f"""
Generate 10 high-potential YouTube video ideas for the following channel.

Channel Name:
{channel_name}

Channel Description:
{channel_description}

Requirements:
- Return exactly 10 ideas.
- Each idea must include title, summary, target audience, potential, and difficulty.
- Avoid generic topics.
- Avoid duplicates.
- Write in English.
"""