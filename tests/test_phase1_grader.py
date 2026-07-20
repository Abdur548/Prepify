from types import SimpleNamespace

from prepify.phase1.grader import Paper4CodeExecutionGrader, outputs_match
from prepify.phase1.repository import Paper4Context
from prepify.phase1.sandbox import SandboxExecution, SandboxStatus
from prepify.phase1.schemas import ComparisonMode, Paper4GradeRequest


class FakeRepository:
    def __init__(self, validation_status="blocked") -> None:
        self.attempt = None
        self.finished = None
        self.context = Paper4Context(
            question=SimpleNamespace(id="q1", marks_available=3, paper_number=4),
            test_cases=[
                SimpleNamespace(
                    id="tc1",
                    name="normal data",
                    stdin="2\n",
                    arguments=[],
                    expected_stdout="4\n",
                    marks_available=2,
                    comparison_mode="trim_trailing",
                ),
                SimpleNamespace(
                    id="tc2",
                    name="boundary data",
                    stdin="0\n",
                    arguments=[],
                    expected_stdout="0\n",
                    marks_available=1,
                    comparison_mode="trim_trailing",
                ),
            ],
            resources=[],
            validation_status=validation_status,
        )

    def get_context(self, question_id, *, sandbox_profile=None):
        return self.context

    def start_attempt(self, **kwargs):
        self.attempt = SimpleNamespace(id="attempt-1")
        return self.attempt

    def finish_attempt(self, attempt, **kwargs):
        self.finished = kwargs


class FakeSandbox:
    profile = {"network": "none"}
    images_are_digest_pinned = True

    def __init__(self, executions):
        self.executions = iter(executions)

    def run(self, **kwargs):
        return next(self.executions)


def completed(stdout, exit_code=0):
    return SandboxExecution(SandboxStatus.completed, exit_code, stdout, "", 0.01)


def test_output_comparison_modes_are_deterministic() -> None:
    assert outputs_match("a  b\n", "a b", ComparisonMode.whitespace)
    assert outputs_match("a  \r\n", "a", ComparisonMode.trim_trailing)
    assert not outputs_match("a\n", "a", ComparisonMode.exact)


def test_grader_aggregates_pass_fail_marks_without_llm() -> None:
    repository = FakeRepository()
    sandbox = FakeSandbox([completed("4\n"), completed("1\n")])
    result = Paper4CodeExecutionGrader(repository, sandbox=sandbox).grade(
        "q1",
        Paper4GradeRequest(language="python", source_code="print(int(input()) * 2)"),
    )

    assert result.status == "completed"
    assert result.marks_awarded == 2
    assert result.marks_available == 3
    assert [item.verdict for item in result.test_results] == ["passed", "failed"]
    assert result.certified is False
    assert result.validation_status == "blocked"
    assert repository.finished["marks_awarded"] == 2


def test_sandbox_failure_produces_no_aggregate_score() -> None:
    repository = FakeRepository()
    sandbox = FakeSandbox(
        [SandboxExecution(SandboxStatus.infrastructure_error, None, "", "daemon absent", 0.01)]
    )
    result = Paper4CodeExecutionGrader(repository, sandbox=sandbox).grade(
        "q1",
        Paper4GradeRequest(language="python", source_code="print('x')"),
    )

    assert result.status == "infrastructure_error"
    assert result.marks_awarded is None
    assert result.test_results[0].verdict == "sandbox_error"
