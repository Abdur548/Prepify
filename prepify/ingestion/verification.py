from __future__ import annotations

import re
from dataclasses import dataclass

from prepify.schemas import OCRBlock


TOKEN_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("assignment_arrow", re.compile(r"←|<-|⇐")),
    ("not_equal", re.compile(r"≠|<>|!=")),
    ("integer_operator", re.compile(r"\b(?:MOD|DIV)\b", re.IGNORECASE)),
    ("pseudocode_control", re.compile(r"\b(?:IF|THEN|ELSE|ENDIF|CASE|ENDCASE|FOR|NEXT|WHILE|ENDWHILE|REPEAT|UNTIL)\b", re.IGNORECASE)),
    ("pseudocode_routine", re.compile(r"\b(?:PROCEDURE|ENDPROCEDURE|FUNCTION|ENDFUNCTION|CALL|RETURN)\b", re.IGNORECASE)),
    ("array_index", re.compile(r"\[[^\]\n]+\]")),
)


@dataclass(frozen=True)
class ReviewDecision:
    status: str
    reasons: tuple[str, ...]


def review_decision(block: OCRBlock) -> ReviewDecision:
    if block.extraction_method != "qwen3_vl_ocr":
        return ReviewDecision("auto_trusted", ())
    reasons = tuple(name for name, pattern in TOKEN_PATTERNS if pattern.search(block.text))
    if reasons:
        return ReviewDecision("pending_review", reasons)
    return ReviewDecision("auto_trusted", ())
