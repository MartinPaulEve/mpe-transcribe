import re
from difflib import SequenceMatcher

_DEFAULT_THRESHOLD = 0.8


def apply_corrections(
    text: str,
    replacements: dict[str, str] | None = None,
    custom_terms: list[str] | None = None,
    threshold: float = _DEFAULT_THRESHOLD,
) -> str:
    """Apply corrections to transcribed text.

    Two correction strategies:
    1. Exact replacements — case-insensitive substitution.
    2. Fuzzy term matching — sliding window over words, replacing
       spans that are similar enough to a known term.
    """
    if not text:
        return text
    for old, new in (replacements or {}).items():
        text = _exact_replace(text, old, new)
    for term in custom_terms or []:
        text = _fuzzy_replace(text, term, threshold)
    return text


def _exact_replace(text: str, old: str, new: str) -> str:
    pattern = re.compile(re.escape(old), re.IGNORECASE)
    return pattern.sub(new, text)


def _fuzzy_replace(
    text: str, term: str, threshold: float
) -> str:
    term_words = term.split()
    n = len(term_words)
    if n == 0:
        return text
    words = text.split()
    if len(words) < n:
        # Check the entire text as one span
        ratio = SequenceMatcher(
            None, text.lower(), term.lower()
        ).ratio()
        if ratio >= threshold:
            return term
        return text

    best_ratio = 0.0
    best_start = -1
    for i in range(len(words) - n + 1):
        span = " ".join(words[i : i + n])
        ratio = SequenceMatcher(
            None, span.lower(), term.lower()
        ).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_start = i

    if best_ratio >= threshold and best_start >= 0:
        words[best_start : best_start + n] = term_words
    return " ".join(words)


def build_whisper_prompt(
    replacements: dict[str, str] | None = None,
    custom_terms: list[str] | None = None,
) -> str | None:
    """Build an initial_prompt string for Whisper from custom terms.

    Whisper uses the prompt to bias its decoder toward these words
    and phrases, improving recognition accuracy.
    """
    parts: list[str] = []
    for new in (replacements or {}).values():
        if new not in parts:
            parts.append(new)
    for term in custom_terms or []:
        if term not in parts:
            parts.append(term)
    if not parts:
        return None
    return ", ".join(parts)
