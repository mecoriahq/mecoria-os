from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI
import os

from prompt import build_research_prompt
from output import build_output


load_dotenv()


def load_file(filename: str) -> str:
    return (Path(__file__).parent / filename).read_text(encoding="utf-8")


def main():
    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        print("OpenAI API Key: Not Found")
        return

    client = OpenAI(api_key=api_key)

    system_prompt = load_file("system.md")
    workflow = load_file("workflow.md")

    channel_name = input("Channel Name: ")
    channel_description = input("Channel Description: ")

    user_prompt = build_research_prompt(
        channel_name=channel_name,
        channel_description=channel_description,
    )

    response = client.responses.create(
        model="gpt-5.5",
        instructions=system_prompt + "\n\n" + workflow,
        input=user_prompt,
    )

    ideas = response.output_text

    result = build_output(
        channel_name=channel_name,
        response_text=ideas,
    )

    print(result)


if __name__ == "__main__":
    main()