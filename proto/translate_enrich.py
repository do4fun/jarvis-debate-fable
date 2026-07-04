"""FR<->EN translation with verbatim token protection (v3 correction F8):
proper nouns, version numbers, digits, and common license identifiers are
extracted before translation and reinjected after, so a translation model
never touches them. Translation happens once per chunk, never per claim or
per turn (v3 correction F4).

`translate_fn` is injected (an LLM call in production, identity in offline
tests) so this module never hard-depends on a live model.
"""
from __future__ import annotations

import re
from typing import Callable

# Heuristic, not a full NER: capitalized words, dotted version numbers, bare
# numbers, and a short list of common license identifiers. Over-masking a
# capitalized sentence-starter is an accepted trade-off for a prototype --
# the fidelity gate is the FR->EN->FR round-trip test (0.2 DECISION.md), not
# precision of this regex.
_TOKEN_PATTERN = re.compile(
    r"\b(?:[A-Z][a-zA-Z]*(?:\.[A-Z][a-zA-Z]*)*|v?\d+(?:\.\d+)+|\d+|"
    r"MIT|GPL|Apache-2\.0|BSD-3-Clause|LGPL)\b"
)


def extract_verbatim_tokens(text: str) -> tuple[str, dict[str, str]]:
    """Replace protected tokens with opaque placeholders __TOK1__, __TOK2__,
    ... Returns (masked_text, {placeholder: original_token})."""
    mapping: dict[str, str] = {}

    def _replace(match: re.Match) -> str:
        placeholder = f"__TOK{len(mapping) + 1}__"
        mapping[placeholder] = match.group(0)
        return placeholder

    masked = _TOKEN_PATTERN.sub(_replace, text)
    return masked, mapping


def reinject_verbatim_tokens(text: str, mapping: dict[str, str]) -> str:
    for placeholder, original in mapping.items():
        text = text.replace(placeholder, original)
    return text


def translate_enrich(text: str, translate_fn: Callable[[str], str]) -> str:
    """Translate `text`, protecting verbatim tokens across the call."""
    masked, mapping = extract_verbatim_tokens(text)
    translated = translate_fn(masked)
    return reinject_verbatim_tokens(translated, mapping)
