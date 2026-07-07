import json
from datetime import datetime
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent


def get_channel_output_dir(channel: str) -> Path:
    output_dir = BASE_DIR / "output" / channel.lower()
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def get_images_dir(channel: str) -> Path:
    images_dir = get_channel_output_dir(channel) / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    return images_dir


def save_image(channel: str, image_bytes: bytes, extension: str = "png") -> Path:
    images_dir = get_images_dir(channel)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    image_path = images_dir / f"{timestamp}.{extension}"
    image_path.write_bytes(image_bytes)
    return image_path


def save_output(channel: str, data: dict) -> Path:
    output_dir = get_channel_output_dir(channel)
    archive_dir = output_dir / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)

    latest_path = output_dir / "latest.json"
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    archive_path = archive_dir / f"{timestamp}.json"

    json_text = json.dumps(data, ensure_ascii=False, indent=2)

    latest_path.write_text(json_text, encoding="utf-8")
    archive_path.write_text(json_text, encoding="utf-8")

    return latest_path