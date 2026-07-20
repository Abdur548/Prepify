from __future__ import annotations

import re
from difflib import SequenceMatcher


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def enforce_paraphrase(
    generated_parts: list[str],
    source_texts: list[str],
    *,
    max_contiguous_chars: int = 120,
) -> None:
    """Reject suspiciously long copied spans; source text remains retrieval-only."""
    for generated in generated_parts:
        normalized_generated = _normalize(generated)
        if not normalized_generated:
            continue
        for source in source_texts:
            match = SequenceMatcher(None, normalized_generated, _normalize(source)).find_longest_match()
            if match.size > max_contiguous_chars:
                raise ValueError(
                    "Generation failed copyright paraphrase guard: output contains a long source span"
                )

