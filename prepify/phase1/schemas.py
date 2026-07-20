from __future__ import annotations

from enum import Enum
from pathlib import PurePath
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class Paper4Language(str, Enum):
    python = "python"
    java = "java"
    visual_basic = "visual_basic"


class ComparisonMode(str, Enum):
    exact = "exact"
    trim_trailing = "trim_trailing"
    whitespace = "whitespace"


class Paper4GradeRequest(BaseModel):
    language: Paper4Language
    source_code: str = Field(min_length=1, max_length=200_000)


class Paper4TestResult(BaseModel):
    test_case_id: str
    name: str
    verdict: Literal[
        "passed",
        "failed",
        "runtime_error",
        "timed_out",
        "output_limit",
        "sandbox_error",
    ]
    marks_awarded: int | None
    marks_available: int
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    feedback: str


class Paper4GradeResponse(BaseModel):
    attempt_id: str
    question_id: str
    status: Literal["completed", "infrastructure_error"]
    marks_awarded: int | None
    marks_available: int
    certified: bool
    validation_status: Literal["blocked", "validated"]
    launch_gate: str
    test_results: list[Paper4TestResult]


class Paper4ManifestResource(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    source_path: str = Field(min_length=1)

    @model_validator(mode="after")
    def safe_flat_filename(self) -> "Paper4ManifestResource":
        pure = PurePath(self.filename)
        if pure.name != self.filename or self.filename in {".", ".."}:
            raise ValueError("resource filename must be a flat basename")
        if any(character in self.filename for character in ("/", "\\", ":", "\x00")):
            raise ValueError("resource filename contains a forbidden character")
        return self


class Paper4ManifestTestCase(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    stdin: str = Field(default="", max_length=100_000)
    arguments: list[str] = Field(default_factory=list, max_length=32)
    expected_stdout: str = Field(max_length=100_000)
    marks_available: int = Field(ge=1)
    comparison_mode: ComparisonMode = ComparisonMode.trim_trailing
    expected_source_chunk_id: str = Field(min_length=1)

    @model_validator(mode="after")
    def bounded_arguments(self) -> "Paper4ManifestTestCase":
        if any(len(argument) > 1_000 or "\x00" in argument for argument in self.arguments):
            raise ValueError("test arguments must be at most 1000 characters and contain no NUL")
        return self


class Paper4Manifest(BaseModel):
    question_id: str = Field(min_length=1)
    verified_by: str = Field(min_length=3, max_length=256)
    resources: list[Paper4ManifestResource] = Field(default_factory=list)
    test_cases: list[Paper4ManifestTestCase] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_names(self) -> "Paper4Manifest":
        names = [case.name.casefold() for case in self.test_cases]
        if len(names) != len(set(names)):
            raise ValueError("test case names must be unique")
        resource_names = [resource.filename.casefold() for resource in self.resources]
        if len(resource_names) != len(set(resource_names)):
            raise ValueError("resource filenames must be unique")
        return self


class Phase1ValidationSubmission(BaseModel):
    question_id: str
    language: Paper4Language
    source_path: str
    official_mark: int = Field(ge=0)
    provenance: str = Field(min_length=3)
    held_out: Literal[True]


class Phase1ValidationDataset(BaseModel):
    dataset_name: str = Field(min_length=3)
    submissions: list[Phase1ValidationSubmission] = Field(min_length=1)


class Phase1ValidationReport(BaseModel):
    run_id: str
    status: Literal["blocked", "validated"]
    sample_count: int
    completed_count: int
    exact_mark_matches: int
    exact_mark_match_rate: float
    reasons: list[str]
