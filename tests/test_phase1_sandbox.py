from dataclasses import replace

from prepify.config import settings
from prepify.phase1.sandbox import DockerSandbox, SandboxStatus
from prepify.phase1.schemas import Paper4Language


def test_docker_command_applies_required_isolation(tmp_path) -> None:
    sandbox = DockerSandbox(replace(settings, docker_executable="docker"))
    hostile_argument = "$(touch /tmp/escaped)"
    command = sandbox.build_command(
        workspace=tmp_path,
        language=Paper4Language.java,
        container_name="test-container",
        arguments=[hostile_argument],
    )

    assert "--network=none" in command
    assert "--read-only" in command
    assert "--cap-drop=ALL" in command
    assert "--security-opt=no-new-privileges=true" in command
    assert "--pids-limit" in command
    assert "--memory" in command
    assert "--cpus" in command
    assert "--privileged" not in command
    assert any(item.endswith(",readonly") for item in command)
    assert command[-1] == hostile_argument
    assert hostile_argument not in command[command.index("sh") + 2]


def test_missing_docker_is_an_infrastructure_error_not_a_zero_mark(tmp_path) -> None:
    sandbox = DockerSandbox(
        replace(settings, docker_executable="definitely-not-a-real-docker-command")
    )
    (tmp_path / "Submission.py").write_text("print('ok')", encoding="utf-8")

    result = sandbox.run(
        workspace=tmp_path,
        language=Paper4Language.python,
        stdin="",
        arguments=[],
    )

    assert result.status == SandboxStatus.infrastructure_error
    assert result.exit_code is None

