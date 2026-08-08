#file_utils.py
import json
from pathlib import Path


def save_text(text: str, output_path: str) -> None:
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, "w", encoding="utf-8") as file:
        file.write(text)

    print(f"✅ Saved file: {output_file}")


def save_json(data, output_path: str) -> None:
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2)

    print(f"✅ Saved JSON: {output_file}")


def load_json(input_path: str):
    with open(input_path, "r", encoding="utf-8") as file:
        return json.load(file)