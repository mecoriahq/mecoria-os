import json
from datetime import datetime
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"


def save_output(channel: str, data: dict) -> Path:
    channel_dir = OUTPUT_DIR / channel.lower()
    archive_dir = channel_dir / "archive"

    channel_dir.mkdir(parents=True, exist_ok=True)
    archive_dir.mkdir(parents=True, exist_ok=True)

    latest_path = channel_dir / "latest.json"
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    archive_path = archive_dir / f"{timestamp}.json"

    content = json.dumps(data, indent=2, ensure_ascii=False)

    latest_path.write_text(content, encoding="utf-8")
    archive_path.write_text(content, encoding="utf-8")

    return latest_path
