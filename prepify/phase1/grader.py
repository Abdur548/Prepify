from __future__ import annotations

import hashlib
import shutil
import tempfile
from pathlib import Path

from prepify.config import Settings, settings
from prepify.phase1.repository import Paper4Repository
from prepify.phase1.sandbox import DockerSandbox, SandboxExecution, SandboxStatus
from prepify.phase1.schemas import (
    ComparisonMode,
    Paper4GradeRequest,
    Paper4GradeResponse,
    Paper4Language,
    Paper4TestResult,
)


VB_PROJECT = """<Project Sdk=\"Microsoft.NET.Sdk\">
  <PropertyGroup>
    <OutputType>Exe</OutputType>
    <TargetFramework>net8.0</TargetFramework>
    <RootNamespace>Submission</RootNamespace>
  </PropertyGroup>
</Project>
"""


def outputs_match(actual: str, expected: str, mode: ComparisonMode) -> bool:
    if mode == ComparisonMode.exact:
        return actual == expected
    if mode == ComparisonMode.whitespace:
        return actual.split() == expected.split()

    def trim_trailing(value: str) -> str:
        normalized = value.replace("\r\n", "\n").replace("\r", "\n")
        return "\n".join(line.rstrip() for line in normalized.split("\n")).rstrip("\n")

    return trim_trailing(actual) == trim_trailing(expected)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class Paper4CodeExecutionGrader:
    """Phase 1 grader. Verdicts come only from sandbox execution and output comparison."""

    def __init__(
        self,
        repository: Paper4Repository,
        *,
        sandbox: DockerSandbox | None = None,
        config: Settings = settings,
    ):
        self.repository = repository
        self.config = config
        self.sandbox = sandbox or DockerSandbox(config)

    def grade(
        self,
        question_id: str,
        request: Paper4GradeRequest,
        *,
        validation_run_id: str | None = None,
    ) -> Paper4GradeResponse:
        context = self.repository.get_context(
            question_id, sandbox_profile=self.sandbox.profile
        )
        marks_available = sum(case.marks_available for case in context.test_cases)
        if context.question.marks_available != marks_available:
            raise ValueError(
                "Verified test-case marks do not equal the question's marks_available"
            )
        attempt = self.repository.start_attempt(
            question_id=question_id,
            language=request.language,
            source_code=request.source_code,
            marks_available=marks_available,
            validation_status=context.validation_status,
            sandbox_profile=self.sandbox.profile,
            validation_run_id=validation_run_id,
        )
        results: list[Paper4TestResult] = []
        infrastructure_error = False
        workspace_root = Path(self.config.sandbox_workspace_root)
        workspace_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="paper4-", dir=workspace_root) as temporary:
            workspace = Path(temporary)
            try:
                self._stage_submission(workspace, request.language, request.source_code)
                self._stage_resources(workspace, context.resources)
            except (OSError, ValueError) as exc:
                infrastructure_error = True
                results.append(
                    Paper4TestResult(
                        test_case_id="staging",
                        name="Sandbox staging",
                        verdict="sandbox_error",
                        marks_awarded=None,
                        marks_available=marks_available,
                        feedback=f"Execution infrastructure error: {exc}",
                    )
                )
            if not infrastructure_error:
                for test_case in context.test_cases:
                    execution = self.sandbox.run(
                        workspace=workspace,
                        language=request.language,
                        stdin=test_case.stdin,
                        arguments=list(test_case.arguments or []),
                    )
                    result = self._result_for(test_case, execution)
                    results.append(result)
                    if result.verdict == "sandbox_error":
                        infrastructure_error = True
                        break

        status = "infrastructure_error" if infrastructure_error else "completed"
        marks_awarded = None if infrastructure_error else sum(
            result.marks_awarded or 0 for result in results
        )
        certified = context.validation_status == "validated" and not infrastructure_error
        self.repository.finish_attempt(
            attempt,
            status=status,
            marks_awarded=marks_awarded,
            certified=certified,
            results=results,
        )
        return Paper4GradeResponse(
            attempt_id=attempt.id,
            question_id=question_id,
            status=status,
            marks_awarded=marks_awarded,
            marks_available=marks_available,
            certified=certified,
            validation_status=context.validation_status,
            launch_gate=(
                "Phase 1 validated against the configured held-out real-submission set."
                if certified
                else "Provisional only: public/certified scoring is blocked until held-out real submissions match official marks."
            ),
            test_results=results,
        )

    def _stage_submission(
        self, workspace: Path, language: Paper4Language, source_code: str
    ) -> None:
        filename = {
            Paper4Language.python: "Submission.py",
            Paper4Language.java: "Main.java",
            Paper4Language.visual_basic: "Program.vb",
        }[language]
        (workspace / filename).write_text(source_code, encoding="utf-8", newline="\n")
        if language == Paper4Language.visual_basic:
            (workspace / "Submission.vbproj").write_text(
                VB_PROJECT, encoding="utf-8", newline="\n"
            )

    def _stage_resources(self, workspace: Path, resources: list) -> None:
        total = 0
        reserved = {"submission.py", "main.java", "program.vb", "submission.vbproj"}
        for resource in resources:
            if resource.filename.casefold() in reserved:
                raise ValueError(f"resource filename is reserved: {resource.filename}")
            source = Path(resource.storage_path).resolve()
            if not source.is_file():
                raise ValueError(f"verified resource is missing: {resource.filename}")
            size = source.stat().st_size
            total += size
            if size != resource.size_bytes or _sha256(source) != resource.sha256:
                raise ValueError(f"verified resource checksum mismatch: {resource.filename}")
            if total > self.config.sandbox_max_resource_bytes:
                raise ValueError("verified resources exceed sandbox size limit")
            shutil.copy2(source, workspace / resource.filename)

    @staticmethod
    def _result_for(test_case, execution: SandboxExecution) -> Paper4TestResult:
        common = {
            "test_case_id": test_case.id,
            "name": test_case.name,
            "marks_available": test_case.marks_available,
            "exit_code": execution.exit_code,
            "stdout": execution.stdout,
            "stderr": execution.stderr,
        }
        if execution.status == SandboxStatus.infrastructure_error:
            return Paper4TestResult(
                **common,
                verdict="sandbox_error",
                marks_awarded=None,
                feedback="The sandbox could not run this test; no score was produced.",
            )
        if execution.status == SandboxStatus.timed_out:
            return Paper4TestResult(
                **common,
                verdict="timed_out",
                marks_awarded=0,
                feedback="Execution exceeded the per-test time limit.",
            )
        if execution.status == SandboxStatus.output_limit:
            return Paper4TestResult(
                **common,
                verdict="output_limit",
                marks_awarded=0,
                feedback="Execution exceeded the output limit.",
            )
        if execution.exit_code != 0:
            return Paper4TestResult(
                **common,
                verdict="runtime_error",
                marks_awarded=0,
                feedback="The program exited with an error before producing a passing result.",
            )
        mode = ComparisonMode(test_case.comparison_mode)
        passed = outputs_match(execution.stdout, test_case.expected_stdout, mode)
        return Paper4TestResult(
            **common,
            verdict="passed" if passed else "failed",
            marks_awarded=test_case.marks_available if passed else 0,
            feedback=(
                "Actual output matched the verified expected output."
                if passed
                else "Actual output did not match the verified expected output."
            ),
        )
