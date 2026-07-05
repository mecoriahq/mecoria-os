from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI
import os


load_dotenv()


def load_file(filename: str) -> str:
    return (Path(__file__).parent / filename).read_text(encoding="utf-8")


def main():
    system_prompt = load_file("system.md")
    workflow = load_file("workflow.md")
    api_key = os.getenv("OPENAI_API_KEY")

    print("=== Research Agent ===")
    print()
    print("System Prompt Loaded:", len(system_prompt), "characters")
    print("Workflow Loaded:", len(workflow), "characters")

    if not api_key:
        print("OpenAI API Key: Not Found")
        return

    print("OpenAI API Key: Loaded")

    client = OpenAI(api_key=api_key)

    response = client.responses.create(
        model="gpt-5.5",
        input="Reply with exactly: Mecoria OS Connected",
    )

    print("OpenAI Response:", response.output_text)


if __name__ == "__main__":
    main()