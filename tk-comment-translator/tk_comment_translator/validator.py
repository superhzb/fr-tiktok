import json
import re


def parse_model_json(raw_response: str) -> list[dict]:
    text = raw_response.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if not match:
            raise ValueError("Model output does not contain a JSON array")
        return json.loads(match.group(0))


def validate_translation_rows(rows: list[dict], batch: list[dict]) -> None:
    if not isinstance(rows, list):
        raise ValueError("Model output must be a JSON array")

    if len(rows) != len(batch):
        raise ValueError(
            f"Output count ({len(rows)}) does not match input count ({len(batch)})"
        )

    for row, source in zip(rows, batch):
        if not isinstance(row, dict):
            raise ValueError("Each output item must be an object")

        if row.get("id") != source["id"]:
            raise ValueError(
                f"Output id {row.get('id')!r} does not match expected {source['id']}"
            )

        translation = row.get("zh")
        if not isinstance(translation, str) or not translation.strip():
            raise ValueError(f"Missing translation text for id={source['id']}")
