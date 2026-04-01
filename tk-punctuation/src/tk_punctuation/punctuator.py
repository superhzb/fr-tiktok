"""Core punctuation logic using kredor/punctuate-all."""

import logging
import re

logger = logging.getLogger(__name__)

DEFAULT_MODEL_ID = "kredor/punctuate-all"
DEFAULT_CHUNK_WORDS = 180

TRAILING_PUNCT_RE = re.compile(r"[,.?:;\-…!]+$")
DOUBLE_SPACE_RE = re.compile(r"\s+")
WORD_CHARS = r"0-9A-Za-zÀ-ÖØ-öø-ÿŒœÆæ"
WORD_RE = re.compile(rf"[{WORD_CHARS}]+(?:[''\-][{WORD_CHARS}]+)*")

LABEL_TO_PUNCT = {
    "0": "",
    ".": ".",
    ",": ",",
    "?": "?",
    "-": "-",
    ":": ":",
}


def load_classifier(model_id: str = DEFAULT_MODEL_ID):
    from transformers import pipeline

    logger.debug("Loading model: %s", model_id)
    clf = pipeline(
        "token-classification",
        model=model_id,
        aggregation_strategy="first",
    )
    logger.debug("Model loaded.")
    return clf


def normalize_label(raw_label: str) -> str:
    if raw_label in LABEL_TO_PUNCT:
        return raw_label
    if raw_label.startswith("LABEL_"):
        label_id = raw_label.split("_", 1)[1]
        if label_id in LABEL_TO_PUNCT:
            return label_id
    return raw_label


def compute_word_spans(words: list[str]) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    cursor = 0
    for word in words:
        start = cursor
        end = start + len(word)
        spans.append((start, end))
        cursor = end + 1
    return spans


def find_word_index(spans: list[tuple[int, int]], start: int, end: int) -> int | None:
    for index, (word_start, word_end) in enumerate(spans):
        if start < word_end and end > word_start:
            return index
    return None


def sanitize_word(word: str) -> str:
    cleaned = TRAILING_PUNCT_RE.sub("", word)
    return cleaned or word


def normalize_output_text(text: str) -> str:
    normalized = text
    normalized = re.sub(r"([,.?:;!]){2,}", lambda m: m.group(0)[-1], normalized)
    normalized = re.sub(r"([,.?:;!])(?:\s+\1)+", r"\1", normalized)
    normalized = re.sub(r",\.", ".", normalized)
    normalized = re.sub(r"\.,", ".", normalized)
    normalized = re.sub(r"\?\.", "?", normalized)
    normalized = re.sub(r"\.\?", "?", normalized)
    normalized = re.sub(r":\.", ":", normalized)
    normalized = re.sub(
        r":\s+(pas|oui|non|ok|bah|bon)\.",
        r" \1.",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(
        r"\b(je dis|je lui dis|tu dis|il dit|elle dit|on dit|me dit|m'a dit|me répond|m'a répondu|elle répond|il répond|je réponds|demande|demandez|ajoute|ajouté):\s+([a-zà-ÿ])",
        lambda m: f"{m.group(1)} {m.group(2)}",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(r"\s+([,.?:;!])", r"\1", normalized)
    normalized = re.sub(r"([,.?:;!])([^\s])", r"\1 \2", normalized)
    normalized = re.sub(
        r"(^|(?<=[.!?]\s))([a-zà-öø-ÿ])",
        lambda m: m.group(1) + m.group(2).upper(),
        normalized,
    )
    normalized = DOUBLE_SPACE_RE.sub(" ", normalized)
    return normalized.strip()


def find_second_to_last_sentence_end(text: str) -> int | None:
    collapsed = re.sub(r"\.{3}|…", "\x00", text)
    positions = [m.end() for m in re.finditer(r"[.!?\x00]", collapsed)]
    if len(positions) < 2:
        return None
    return positions[-2]


def tail_word_count(text: str) -> int:
    return len(WORD_RE.findall(text))


def punctuate_chunk(classifier, words: list[str]) -> str:
    sanitized = [sanitize_word(w) for w in words]
    chunk_text = " ".join(sanitized)
    spans = compute_word_spans(sanitized)
    predictions = classifier(chunk_text)
    labels_by_word: list[str] = ["0"] * len(words)

    for item in predictions:
        label = normalize_label(item.get("entity_group") or item.get("entity") or "0")
        if label not in LABEL_TO_PUNCT:
            continue
        start = int(item.get("start", 0))
        end = int(item.get("end", start))
        word_index = find_word_index(spans, start, end)
        if word_index is None:
            continue
        labels_by_word[word_index] = label

    output_parts: list[str] = []
    for index, word in enumerate(words):
        punct = LABEL_TO_PUNCT[labels_by_word[index]]
        output_parts.append(f"{word}{punct}" if punct else word)

    return normalize_output_text(" ".join(output_parts))


def strip_punctuation(text: str) -> str:
    return " ".join(WORD_RE.findall(text))


def punctuate_text(
    text: str,
    classifier=None,
    *,
    model_id: str = DEFAULT_MODEL_ID,
    chunk_words: int = DEFAULT_CHUNK_WORDS,
) -> str:
    """Punctuate plain transcription text and return the result string."""
    if classifier is None:
        classifier = load_classifier(model_id)

    text = strip_punctuation(text)
    words = text.split()
    if not words:
        logger.debug("Input text is empty after stripping punctuation.")
        return ""

    total_words = len(words)
    logger.debug("Total words to process: %d", total_words)

    pos = 0
    output_parts: list[str] = []
    chunk_index = 0

    while pos < total_words:
        chunk_index += 1
        chunk = words[pos : pos + chunk_words]
        is_last = pos + chunk_words >= total_words
        punctuated_chunk = punctuate_chunk(classifier, chunk)

        accepted_output = punctuated_chunk
        rollback = 0
        advance = len(chunk)

        if not is_last:
            split_pos = find_second_to_last_sentence_end(punctuated_chunk)
            if split_pos is not None:
                accepted_output = punctuated_chunk[:split_pos].rstrip()
                tail = punctuated_chunk[split_pos:].strip()
                rollback = tail_word_count(tail)
                advance = max(1, len(chunk) - rollback)

        accepted_word_end = pos + advance - 1
        logger.debug(
            "Chunk %d: accepted words %d-%d, read %d-%d, rollback=%d",
            chunk_index,
            pos,
            accepted_word_end,
            pos,
            pos + len(chunk) - 1,
            rollback,
        )
        output_parts.append(accepted_output)
        pos += advance

    return normalize_output_text(" ".join(output_parts))
