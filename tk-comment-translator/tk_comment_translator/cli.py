import argparse
import json
import logging
from pathlib import Path

from tk_comment_translator.batcher import load_prompt_template, translate_all_batches
from tk_comment_translator.config import TranslationConfig
from tk_comment_translator.translator import (
    merge_translations,
    parse_comments,
    preprocess_comments,
    translate_comments_file,
)


def main():
    parser = argparse.ArgumentParser(
        prog="tk-comment-translator",
        description="Translate TikTok comment JSON from French to Chinese.",
    )
    parser.add_argument("input", type=Path, help="Input JSON file from tk-comment-checker")
    parser.add_argument("--output", "-o", type=Path, default=None, help="Output JSON file (default: stdout)")
    _defaults = TranslationConfig()
    parser.add_argument("--model", default=_defaults.model_path, help="MLX model path")
    parser.add_argument("--batch-size", type=int, default=_defaults.batch_size)
    parser.add_argument("--max-tokens", type=int, default=_defaults.max_tokens)
    parser.add_argument("--temperature", type=float, default=_defaults.temperature)
    parser.add_argument("--prompt", type=Path, default=None, help="Path to prompt template file (default: prompt.txt)")
    parser.add_argument("--description", type=Path, default=None, help="Path to video description file for translation context")
    parser.add_argument("-v", "--verbose", action="store_true")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )

    config = TranslationConfig(
        model_path=args.model,
        batch_size=args.batch_size,
        max_tokens=args.max_tokens,
        temperature=args.temperature,
    )

    if args.output:
        translate_comments_file(args.input, args.output, config, args.prompt, args.description)
        logging.getLogger(__name__).info("Wrote output to %s", args.output)
    else:
        prompt_template = load_prompt_template(args.prompt)
        context = args.description.read_text(encoding="utf-8").strip() if args.description else ""
        raw_items = json.loads(args.input.read_text(encoding="utf-8"))
        comments = parse_comments(raw_items)
        prepared_comments, translation_items = preprocess_comments(comments)
        translations = translate_all_batches(translation_items, config, prompt_template, context)
        merged = merge_translations(prepared_comments, translations)
        print(json.dumps(merged, ensure_ascii=False, indent=2))
