from pathlib import Path
import yaml


def load_config(config_path: str) -> dict:
    path = Path(config_path)

    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with path.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file)