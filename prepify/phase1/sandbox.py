from __future__ import annotations

import os
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from prepify.config import Settings, settings
from prepify.phase1.schemas import Paper4Language


class SandboxStatus(str, Enum):
    completed = "completed"
    timed_out = "timed_out"
    output_limit = "output_limit"
    infrastructure_error = "infrastructure_error"


@dataclass(frozen=True)
class SandboxExecution:
    status: SandboxStatus
    exit_code: int | None
    stdout: str
    stderr: str
    duration_seconds: float


def _creation_flags() -> int:
    return subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


class DockerSandbox:
    """Runs one untrusted submission/test pair in a fresh, constrained container."""

    def __init__(self, config: Settings = settings):
        self.config = config
        self.images = {
            Paper4Language.python: config.paper4_python_image,
            Paper4Language.java: config.paper4_java_image,
            Paper4Language.visual_basic: config.paper4_vb_image,
        }

    @property
    def profile(self) -> dict:
        return {
            "engine": "docker",
            "images": {key.value: value for key, value in self.images.items()},
            "network": "none",
            "read_only_root": True,
            "read_only_workspace": True,
            "cap_drop": "ALL",
            "no_new_privileges": True,
            "user": "65534:65534",
            "timeout_seconds": self.config.sandbox_timeout_seconds,
            "memory_mb": self.config.sandbox_memory_mb,
            "cpus": self.config.sandbox_cpus,
            "pids_limit": self.config.sandbox_pids_limit,
            "max_output_bytes": self.config.sandbox_max_output_bytes,
        }

    @property
    def images_are_digest_pinned(self) -> bool:
        return all("@sha256:" in image for image in self.images.values())

    def build_command(
        self,
        *,
        workspace: Path,
        language: Paper4Language,
        container_name: str,
        arguments: list[str],
    ) -> list[str]:
        resolved = workspace.resolve()
        if not resolved.is_dir():
            raise ValueError("sandbox workspace must be an existing directory")
        if "," in str(resolved):
            raise ValueError("sandbox workspace path cannot contain a comma")
        mount = f"type=bind,source={resolved},target=/workspace,readonly"
        command = [
            self.config.docker_executable,
            "run",
            "--rm",
            "--pull=never",
            "--name",
            container_name,
            "--network=none",
            "--read-only",
            "--mount",
            mount,
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=64m,mode=1777",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges=true",
            "--user",
            "65534:65534",
            "--memory",
            f"{self.config.sandbox_memory_mb}m",
            "--cpus",
            str(self.config.sandbox_cpus),
            "--pids-limit",
            str(self.config.sandbox_pids_limit),
            "--ulimit",
            "nofile=64:64",
            "--ulimit",
            "nproc=64:64",
            "--stop-timeout",
            "1",
            "--init",
            "--env",
            "HOME=/tmp",
            "--env",
            "DOTNET_CLI_HOME=/tmp",
            "--workdir",
            "/",
            self.images[language],
        ]
        if language == Paper4Language.python:
            return command + [
                "sh",
                "-c",
                'cp -R /workspace/. /tmp/run && cd /tmp/run && exec python -I -B Submission.py "$@"',
                "prepify-python",
                *arguments,
            ]
        if language == Paper4Language.java:
            return command + [
                "sh",
                "-c",
                "cp -R /workspace/. /tmp/run && cd /tmp/run && "
                'mkdir -p /tmp/classes && javac -d /tmp/classes Main.java && '
                'exec java -cp /tmp/classes Main "$@"',
                "prepify-java",
                *arguments,
            ]
        return command + [
            "sh",
            "-c",
            "cp -R /workspace/. /tmp/run && cd /tmp/run && "
            "dotnet build Submission.vbproj -o /tmp/out --nologo "
            "-p:UseAppHost=false -p:BaseIntermediateOutputPath=/tmp/obj/ "
            ">/tmp/build.log 2>&1 || { cat /tmp/build.log >&2; exit 1; }; "
            'exec dotnet /tmp/out/Submission.dll "$@"',
            "prepify-vb",
            *arguments,
        ]

    def run(
        self,
        *,
        workspace: Path,
        language: Paper4Language,
        stdin: str,
        arguments: list[str],
    ) -> SandboxExecution:
        container_name = f"prepify-p4-{uuid.uuid4().hex}"
        try:
            command = self.build_command(
                workspace=workspace,
                language=language,
                container_name=container_name,
                arguments=arguments,
            )
        except (KeyError, ValueError) as exc:
            return SandboxExecution(
                SandboxStatus.infrastructure_error, None, "", str(exc), 0.0
            )

        started = time.monotonic()
        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=_creation_flags(),
            )
        except OSError as exc:
            return SandboxExecution(
                SandboxStatus.infrastructure_error,
                None,
                "",
                f"Docker could not start: {exc}",
                time.monotonic() - started,
            )

        stdout_buffer = bytearray()
        stderr_buffer = bytearray()
        output_limit = threading.Event()

        def drain(stream, buffer: bytearray) -> None:
            while True:
                chunk = stream.read(4096)
                if not chunk:
                    break
                remaining = self.config.sandbox_max_output_bytes - len(buffer)
                if remaining > 0:
                    buffer.extend(chunk[:remaining])
                if len(chunk) > remaining:
                    output_limit.set()

        threads = [
            threading.Thread(target=drain, args=(process.stdout, stdout_buffer), daemon=True),
            threading.Thread(target=drain, args=(process.stderr, stderr_buffer), daemon=True),
        ]
        for thread in threads:
            thread.start()

        def feed_stdin() -> None:
            try:
                if process.stdin:
                    process.stdin.write(stdin.encode("utf-8"))
                    process.stdin.close()
            except (BrokenPipeError, OSError):
                pass

        stdin_thread = threading.Thread(target=feed_stdin, daemon=True)
        stdin_thread.start()

        deadline = started + self.config.sandbox_timeout_seconds
        terminal_status: SandboxStatus | None = None
        while process.poll() is None:
            if output_limit.is_set():
                terminal_status = SandboxStatus.output_limit
                break
            if time.monotonic() >= deadline:
                terminal_status = SandboxStatus.timed_out
                break
            time.sleep(0.02)

        if terminal_status is not None:
            self._remove_container(container_name)
            try:
                process.kill()
            except OSError:
                pass
        try:
            exit_code = process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            exit_code = None
        for thread in threads:
            thread.join(timeout=1)
        stdin_thread.join(timeout=1)

        stdout = stdout_buffer.decode("utf-8", errors="replace")
        stderr = stderr_buffer.decode("utf-8", errors="replace")
        duration = time.monotonic() - started
        if terminal_status is not None:
            return SandboxExecution(terminal_status, exit_code, stdout, stderr, duration)
        if exit_code == 125:
            return SandboxExecution(
                SandboxStatus.infrastructure_error, exit_code, stdout, stderr, duration
            )
        return SandboxExecution(SandboxStatus.completed, exit_code, stdout, stderr, duration)

    def _remove_container(self, container_name: str) -> None:
        try:
            subprocess.run(
                [self.config.docker_executable, "rm", "-f", container_name],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False,
                creationflags=_creation_flags(),
            )
        except (OSError, subprocess.TimeoutExpired):
            pass
