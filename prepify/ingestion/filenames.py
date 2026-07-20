from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


EXAM_FILE_RE = re.compile(
    r"^(?P<syllabus>\d{4})_(?P<series>[a-z]\d{2})_"
    r"(?P<kind>qp|ms)_(?P<paper>\d{2})\.pdf$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class DocumentIdentity:
    syllabus_code: str
    series: str
    document_type: str
    paper_code: str | None
    paper_number: int | None
    variant: int | None

    @property
    def link_key(self) -> tuple[str, str, str | None]:
        return self.syllabus_code, self.series, self.paper_code


def parse_document_identity(path: str | Path) -> DocumentIdentity:
    filename = Path(path).name
    match = EXAM_FILE_RE.match(filename)
    if match:
        raw_kind = match.group("kind").lower()
        kind = {"qp": "question_paper", "ms": "mark_scheme"}[raw_kind]
        paper_code = match.group("paper")
        return DocumentIdentity(
            syllabus_code=match.group("syllabus"),
            series=match.group("series").lower(),
            document_type=kind,
            paper_code=paper_code,
            paper_number=int(paper_code[0]) if paper_code else None,
            variant=int(paper_code[1]) if paper_code else None,
        )
    raise ValueError(
        f"Unsupported filename '{filename}'. The current ingestion scope accepts only "
        "matching question papers and mark schemes, e.g. 9618_s23_qp_21.pdf and "
        "9618_s23_ms_21.pdf."
    )
