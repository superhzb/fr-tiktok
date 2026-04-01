"""Core SRT merging logic: align punctuated text to timestamps and emit subtitles."""

import logging
import re

logger = logging.getLogger(__name__)

MAX_CHARS = 100
MIN_CHARS = 30
MIN_DURATION = 1.0

# Conjunctions/transitions to prefer splitting after
SPLIT_WORDS = {"et", "mais", "donc", "parce", "bref", "enfin", "puis", "car", "or"}

# Short function words that shouldn't dangle at the end of a subtitle line
DANGLING_WORDS = {
    "de", "du", "le", "la", "les", "un", "une", "et", "à", "en", "des",
    "se", "ce", "sa", "son", "ses", "au", "aux", "je", "tu", "il", "elle",
    "on", "nous", "vous", "ils", "elles", "me", "te", "ne", "qui", "que", "où",
}

# Type alias: (word_text, start_seconds, end_seconds)
Word = tuple[str, float, float]


def format_srt_time(seconds: float) -> str:
    """Convert seconds to SRT timestamp HH:MM:SS,mmm."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def strip_punctuation(word: str) -> str:
    return re.sub(r"[^\w\s]", "", word, flags=re.UNICODE).strip()


def is_sentence_end(word: str) -> bool:
    return bool(re.search(r"[.!?]+\s*$", word))


def sub_text(words: list[Word]) -> str:
    return " ".join(w for w, _, _ in words)


def sub_len(words: list[Word]) -> int:
    return len(sub_text(words))


def sub_duration(words: list[Word]) -> float:
    if not words:
        return 0.0
    return words[-1][2] - words[0][1]


def find_best_split(words: list[Word]) -> int | None:
    """Return index of best split point using gaps, punctuation, and conjunctions."""
    text = sub_text(words)
    mid = len(text) // 2

    max_gap = max(
        (words[i][1] - words[i - 1][2] for i in range(1, len(words))),
        default=0,
    )

    best: int | None = None
    best_score = float("-inf")
    char_pos = 0

    for i in range(1, len(words)):
        char_pos += len(words[i - 1][0]) + 1  # +1 for space

        dist_penalty = -abs(char_pos - mid)
        gap = words[i][1] - words[i - 1][2]
        has_gap = gap > 0.1
        gap_bonus = (gap / max_gap * 30) if max_gap > 0 else 0
        has_punct = bool(re.search(r"[,;:.!?]$", words[i - 1][0]))
        punct_bonus = 20 if has_punct else 0

        # Priority tiers: gap+punct > gap > punct
        if has_gap and has_punct:
            tier_bonus = 60
        elif has_gap:
            tier_bonus = 40
        elif has_punct:
            tier_bonus = 20
        else:
            tier_bonus = 0

        curr_clean = strip_punctuation(words[i][0]).lower()
        conj_bonus = 15 if curr_clean in SPLIT_WORDS else 0
        prev_clean = strip_punctuation(words[i - 1][0]).lower()
        dangling_penalty = -25 if prev_clean in DANGLING_WORDS else 0

        # Never split a number from the word right after it (e.g. "30 minutes")
        number_penalty = -50 if words[i - 1][0].rstrip(".,;:!?").isdigit() else 0

        score = dist_penalty + gap_bonus + punct_bonus + tier_bonus + conj_bonus + dangling_penalty + number_penalty
        logger.debug("split candidate i=%d score=%.2f", i, score)

        if score > best_score:
            best_score = score
            best = i

    return best


def split_long(subs: list[list[Word]]) -> list[list[Word]]:
    """Recursively split subtitle groups that exceed MAX_CHARS."""
    result: list[list[Word]] = []
    for words in subs:
        if sub_len(words) <= MAX_CHARS:
            result.append(words)
            continue
        split_idx = find_best_split(words)
        if not split_idx:
            logger.debug("no split found for %d-char subtitle, keeping as-is", sub_len(words))
            result.append(words)
            continue
        logger.debug("splitting %d-char subtitle at word index %d", sub_len(words), split_idx)
        result.extend(split_long([words[:split_idx]]))
        result.extend(split_long([words[split_idx:]]))
    return result


def merge_short(subs: list[list[Word]]) -> list[list[Word]]:
    """Merge subtitle groups that are too short with a neighbour."""
    result: list[list[Word]] = []
    i = 0
    while i < len(subs):
        words = subs[i]
        if sub_len(words) < MIN_CHARS and sub_duration(words) < MIN_DURATION:
            # Try merge with next
            if i + 1 < len(subs) and sub_len(words) + sub_len(subs[i + 1]) + 1 <= MAX_CHARS:
                logger.debug("merging short subtitle with next (len=%d)", sub_len(words))
                result.append(words + subs[i + 1])
                i += 2
                continue
            # Try merge with previous
            if result and sub_len(result[-1]) + sub_len(words) + 1 <= MAX_CHARS:
                logger.debug("merging short subtitle with previous (len=%d)", sub_len(words))
                result[-1] = result[-1] + words
                i += 1
                continue
        result.append(words)
        i += 1
    return result


def align_words(
    timestamps: list[dict],
    punct_text: str,
) -> list[Word]:
    """
    Align punctuated words to timestamp entries.

    Parameters
    ----------
    timestamps:
        List of ``{"text": str, "start": float, "end": float}`` dicts.
    punct_text:
        The full punctuated transcript string.

    Returns
    -------
    List of (word, start, end) tuples with punctuation preserved.
    """
    punct_words = punct_text.split()
    aligned: list[Word] = []
    ts_idx = 0

    for pw in punct_words:
        pw_clean = strip_punctuation(pw).lower()

        if ts_idx < len(timestamps) and strip_punctuation(timestamps[ts_idx]["text"]).lower() == pw_clean:
            aligned.append((pw, timestamps[ts_idx]["start"], timestamps[ts_idx]["end"]))
            logger.debug("aligned '%s' -> ts[%d] (%.2fs)", pw, ts_idx, timestamps[ts_idx]["start"])
            ts_idx += 1
        else:
            found = False
            for look in range(ts_idx, min(ts_idx + 3, len(timestamps))):
                if strip_punctuation(timestamps[look]["text"]).lower() == pw_clean:
                    ts_idx = look
                    aligned.append((pw, timestamps[ts_idx]["start"], timestamps[ts_idx]["end"]))
                    logger.debug("lookahead aligned '%s' -> ts[%d]", pw, ts_idx)
                    ts_idx += 1
                    found = True
                    break
            if not found:
                fallback_start = aligned[-1][1] if aligned else 0.0
                logger.warning("no timestamp match for '%s', using fallback start=%.2f", pw, fallback_start)
                aligned.append((pw, fallback_start, fallback_start))

    unmatched = len(timestamps) - ts_idx
    if unmatched > 0:
        logger.warning("%d timestamp word(s) were not matched", unmatched)

    return aligned


def build_subtitles(aligned: list[Word]) -> list[list[Word]]:
    """Group aligned words into subtitle segments."""
    # Step 1: sentence groups
    sentences: list[list[Word]] = []
    current: list[Word] = []
    for word, start, end in aligned:
        current.append((word, start, end))
        if is_sentence_end(word):
            sentences.append(current)
            current = []
    if current:
        sentences.append(current)
    logger.debug("%d sentence group(s) before splitting", len(sentences))

    # Step 2: split long
    subs = split_long(sentences)
    logger.debug("%d subtitle(s) after split_long", len(subs))

    # Step 3: merge short
    subs = merge_short(subs)
    logger.debug("%d subtitle(s) after merge_short", len(subs))

    return subs


def render_srt(subs: list[list[Word]]) -> str:
    """Render subtitle groups to SRT-format string."""
    lines: list[str] = []
    for i, words in enumerate(subs, 1):
        start_time = format_srt_time(words[0][1])
        end_time = format_srt_time(words[-1][2])
        text = sub_text(words)
        lines.append(f"{i}\n{start_time} --> {end_time}\n{text}\n")
    return "\n".join(lines)


def merge_srt(
    timestamps: list[dict],
    punct_text: str,
) -> str:
    """
    Full pipeline: align → segment → render SRT.

    Parameters
    ----------
    timestamps:
        Word-level timestamps, each ``{"text": str, "start": float, "end": float}``.
    punct_text:
        The punctuated transcript text.

    Returns
    -------
    SRT content as a string.
    """
    logger.info("aligning %d timestamp words to punctuated text (%d chars)", len(timestamps), len(punct_text))
    aligned = align_words(timestamps, punct_text)
    subs = build_subtitles(aligned)
    logger.info("produced %d subtitle(s)", len(subs))
    return render_srt(subs)
