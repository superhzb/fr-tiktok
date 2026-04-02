import json
from pathlib import Path

from tk_comment_translator.batcher import load_prompt_template, translate_all_batches


def parse_comments(raw_items: list[dict]) -> list[dict]:
    if not isinstance(raw_items, list):
        raise ValueError("Input must be a JSON array")

    parsed = []
    for index, item in enumerate(raw_items, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Comment #{index} is not an object")

        for field in ("user", "username", "text", "likes"):
            if field not in item:
                raise ValueError(f"Comment #{index} missing field: {field}")

        parsed.append(
            {
                "id": index,
                "user": item["user"],
                "username": item["username"],
                "text": str(item["text"]),
                "likes": item["likes"],
            }
        )
    return parsed


def preprocess_comments(comments: list[dict]) -> tuple[list[dict], list[dict]]:
    translation_items = []

    for comment in comments:
        comment["text"] = comment["text"].strip()
        if comment["text"]:
            translation_items.append(
                {
                    "id": comment["id"],
                    "text": comment["text"],
                }
            )

    return comments, translation_items


def merge_translations(comments: list[dict], translations: dict[int, str]) -> list[dict]:
    merged = []

    for comment in comments:
        item = {
            "user": comment["user"],
            "username": comment["username"],
            "text": comment["text"],
            "likes": comment["likes"],
        }

        if comment["id"] in translations:
            item["zh"] = translations[comment["id"]]
        else:
            item["zh"] = ""

        merged.append(item)

    return merged


def translate_comments_file(
    input_path: Path,
    output_path: Path,
    config,
    prompt_file: Path | None = None,
    description_file: Path | None = None,
) -> Path:
    raw_items = json.loads(input_path.read_text(encoding="utf-8"))
    prompt_template = load_prompt_template(prompt_file)
    context = description_file.read_text(encoding="utf-8").strip() if description_file else ""

    comments = parse_comments(raw_items)
    prepared_comments, translation_items = preprocess_comments(comments)
    translations = translate_all_batches(translation_items, config, prompt_template, context)
    merged = merge_translations(prepared_comments, translations)

    output_path.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_path
