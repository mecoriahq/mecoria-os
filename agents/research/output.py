import json
from pathlib import Path
from datetime import datetime


def build_output(channel_name: str, response_text: str) -> str:
    """
    Validates the JSON returned by OpenAI,
    saves the latest output,
    archives every run,
    and returns formatted JSON.
    """

    data = json.loads(response_text)

    output = {
        "agent": "research",
        "version": "1.0",
        "channel": channel_name,
        "ideas": data["ideas"]
    }

    channel_folder = Path(__file__).parent / "output" / channel_name.lower()
    archive_folder = channel_folder / "archive"

    channel_folder.mkdir(parents=True, exist_ok=True)
    archive_folder.mkdir(parents=True, exist_ok=True)

    latest_file = channel_folder / "latest.json"

    latest_file.write_text(
        json.dumps(output, indent=4, ensure_ascii=False),
        encoding="utf-8"
    )

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    archive_file = archive_folder / f"{timestamp}.json"

    archive_file.write_text(
        json.dumps(output, indent=4, ensure_ascii=False),
        encoding="utf-8"
    )

    return json.dumps(output, indent=4, ensure_ascii=False)