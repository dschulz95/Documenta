"""Shared helpers for testing the host scripts (backup.sh, restore.sh).

The scripts run inside a Linux runner container (tests/runner/) that has the
same tools as the Pi and talks to the running stack through the Docker socket.
"""

import re
import subprocess

import pytest

from conftest import STACK_DIR

RUNNER_IMAGE = "media-vault-docs-test-runner"
RUNNER_NAME = "media-vault-docs-test-runner"
BACKUP_MOUNT = "/mnt/backup"  # a tmpfs inside the runner: `mountpoint` says yes
SNAPSHOTS = f"{BACKUP_MOUNT}/media-vault/documents"
SNAPSHOT_NAME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{6}$")
STUB_PATH = "/stubs:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"


def sh(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def occ(*args: str) -> str:
    return sh(["docker", "compose", "exec", "-T", "-u", "www-data", "nextcloud", "php", "occ", *args], cwd=STACK_DIR).stdout.strip()


def health(service: str) -> str:
    return sh(["docker", "compose", "ps", service, "--format", "{{.Health}}"], cwd=STACK_DIR).stdout.strip()


@pytest.fixture(scope="session")
def runner():
    if health("nextcloud") != "healthy":
        pytest.skip("document stack is not running and healthy")

    build = sh(["docker", "build", "-q", "-t", RUNNER_IMAGE, str(STACK_DIR / "tests" / "runner")])
    assert build.returncode == 0, build.stderr
    sh(["docker", "rm", "-f", RUNNER_NAME])
    start = sh([
        "docker", "run", "-d", "--name", RUNNER_NAME,
        "-v", "/var/run/docker.sock:/var/run/docker.sock",
        "-v", f"{STACK_DIR.parent}:/work",
        "--tmpfs", f"{BACKUP_MOUNT}:size=2g",
        RUNNER_IMAGE,
    ])
    assert start.returncode == 0, start.stderr
    yield
    sh(["docker", "rm", "-f", RUNNER_NAME])


def in_runner(script: str) -> subprocess.CompletedProcess:
    return sh(["docker", "exec", RUNNER_NAME, "bash", "-c", script])


def run_script(script: str, *args: str, env: dict | None = None, stdin: str | None = None,
               stubs: bool = False) -> subprocess.CompletedProcess:
    values = {"BACKUP_MOUNT": BACKUP_MOUNT, **(env or {})}
    if stubs:
        values["PATH"] = STUB_PATH
    flags = [f for k, v in values.items() for f in ("-e", f"{k}={v}")]
    interactive = ["-i"] if stdin is not None else []
    return sh(["docker", "exec", *interactive, *flags, RUNNER_NAME, "bash", f"scripts/{script}", *args], input=stdin)


def install_stub(name: str, body: str) -> None:
    in_runner(f"mkdir -p /stubs && cat > /stubs/{name} <<'EOF'\n#!/bin/bash\n{body}\nEOF\nchmod +x /stubs/{name}")


def snapshots() -> list[str]:
    return sorted(in_runner(f"ls -1 {SNAPSHOTS} 2>/dev/null").stdout.split())
