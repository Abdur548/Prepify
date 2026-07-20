from __future__ import annotations

import base64
import json
import re
from pathlib import Path

import fitz
from openai import OpenAI

from prepify.config import Settings, settings
from prepify.ingestion.filenames import DocumentIdentity
from prepify.schemas import OCRBlock
from prepify.topics import TOPICS


QUESTION_START = re.compile(
    r"(?m)^\s*(?P<number>"
    r"\d+(?:\([a-z]\))?(?:\((?:i|ii|iii|iv|v|vi|vii|viii|ix|x)\))?"
    r"|\([a-z]\)(?:\((?:i|ii|iii|iv|v|vi|vii|viii|ix|x)\))?"
    r")\s+"
)


def _block_type(identity: DocumentIdentity) -> str:
    return {
        "question_paper": "question",
        "mark_scheme": "mark_scheme",
    }.get(identity.document_type, "other")


def _parent_number(number: str) -> str | None:
    parts = re.findall(r"\([^)]*\)", number)
    if not parts:
        return None
    return number[: number.rfind(parts[-1])] or None


def _expand_question_number(raw: str, previous: str | None) -> str:
    if raw[0].isdigit() or not previous:
        return raw
    root_match = re.match(r"\d+", previous)
    if not root_match:
        return raw
    root = root_match.group(0)
    first_part = re.match(r"\(([^)]+)\)", raw)
    is_roman = bool(first_part and first_part.group(1) in {"i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x"})
    if is_roman and re.search(r"\([a-hj-uw-z]\)$", previous):
        return previous + raw
    return root + raw


def _topic_from_text(text: str) -> str | None:
    folded = text.casefold()
    matches = [topic for topic in TOPICS if topic.name.casefold() in folded]
    return matches[0].name if len(matches) == 1 else None


def segment_embedded_text(
    text: str,
    *,
    page_number: int,
    identity: DocumentIdentity,
    previous_question: str | None = None,
) -> list[OCRBlock]:
    cleaned = "\n".join(line.rstrip() for line in text.splitlines()).strip()
    if not cleaned:
        return []
    matches = list(QUESTION_START.finditer(cleaned))
    if not matches:
        return [
            OCRBlock(
                text=cleaned,
                page_number=page_number,
                block_type=_block_type(identity),
                question_number=previous_question,
                topic_tag=_topic_from_text(cleaned),
                extraction_method="embedded_text",
            )
        ]
    blocks: list[OCRBlock] = []
    if matches[0].start() > 0:
        prefix = cleaned[: matches[0].start()].strip()
        if prefix:
            blocks.append(
                OCRBlock(
                    text=prefix,
                    page_number=page_number,
                    block_type=_block_type(identity),
                    question_number=previous_question,
                    extraction_method="embedded_text",
                )
            )
    current_question = previous_question
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(cleaned)
        question_number = _expand_question_number(match.group("number"), current_question)
        current_question = question_number
        block_text = cleaned[match.start() : end].strip()
        blocks.append(
            OCRBlock(
                text=block_text,
                page_number=page_number,
                block_type=_block_type(identity),
                question_number=question_number,
                parent_question_number=_parent_number(question_number),
                topic_tag=_topic_from_text(block_text),
                extraction_method="embedded_text",
            )
        )
    return blocks


class VisionOCR:
    """Qwen3-VL OCR for pages where embedded PDF text is not trustworthy."""

    def __init__(self, config: Settings = settings):
        if not config.ocr_api_key or not config.ocr_base_url:
            raise RuntimeError(
                "Scanned PDF page found, but OCR_API_KEY/OCR_BASE_URL are not configured "
                "for Qwen3-VL-8B-Instruct."
            )
        self.config = config
        self.client = OpenAI(api_key=config.ocr_api_key, base_url=config.ocr_base_url)

    def extract_page(
        self,
        page: fitz.Page,
        *,
        page_number: int,
        identity: DocumentIdentity,
    ) -> list[OCRBlock]:
        zoom = self.config.ocr_render_dpi / 72
        pixmap = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        encoded = base64.b64encode(pixmap.tobytes("png")).decode("ascii")
        expected_type = _block_type(identity)
        topic_names = ", ".join(topic.name for topic in TOPICS)
        prompt = f"""Transcribe this Cambridge 9618 document page faithfully into structured JSON.
Preserve pseudocode indentation and symbols exactly, especially ←, ≠, MOD, DIV, array brackets,
and procedure/function boundaries. Do not answer, correct, summarize, or paraphrase the source.

Return one JSON object with a `blocks` array. Each block must contain:
text, block_type, question_number, parent_question_number, marks_available,
topic_tag, and point_label. Use null for unknown fields. The expected block_type is
`{expected_type}`. topic_tag, when known, must be one of: {topic_names}.
Split question sub-parts and separately labelled mark-scheme points when the page makes that possible."""
        response = self.client.chat.completions.create(
            model=self.config.ocr_model_name,
            response_format={"type": "json_object"},
            temperature=0,
            messages=[
                {"role": "system", "content": "You are a high-precision document OCR engine."},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{encoded}"},
                        },
                    ],
                },
            ],
        )
        content = response.choices[0].message.content or "{}"
        parsed = json.loads(content)
        blocks: list[OCRBlock] = []
        for item in parsed.get("blocks", []):
            if not str(item.get("text", "")).strip():
                continue
            item["page_number"] = page_number
            item["block_type"] = expected_type
            item["extraction_method"] = "qwen3_vl_ocr"
            blocks.append(OCRBlock.model_validate(item))
        return blocks


class PDFExtractor:
    def __init__(self, config: Settings = settings):
        self.config = config
        self._vision: VisionOCR | None = None

    def extract(self, path: Path, identity: DocumentIdentity) -> list[OCRBlock]:
        blocks: list[OCRBlock] = []
        current_question: str | None = None
        with fitz.open(path) as document:
            for page_index, page in enumerate(document):
                embedded = page.get_text("text", sort=True).strip()
                if len(re.sub(r"\s+", "", embedded)) >= self.config.scanned_page_min_chars:
                    page_blocks = segment_embedded_text(
                        embedded,
                        page_number=page_index + 1,
                        identity=identity,
                        previous_question=current_question,
                    )
                    blocks.extend(page_blocks)
                    current_question = next(
                        (block.question_number for block in reversed(page_blocks) if block.question_number),
                        current_question,
                    )
                    continue
                if self._vision is None:
                    self._vision = VisionOCR(self.config)
                page_blocks = self._vision.extract_page(
                    page,
                    page_number=page_index + 1,
                    identity=identity,
                )
                blocks.extend(page_blocks)
                current_question = next(
                    (block.question_number for block in reversed(page_blocks) if block.question_number),
                    current_question,
                )
        return blocks
