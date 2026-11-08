"""Test helpers for the document stack's Compose configuration.

The seam under test is the resolved Compose model printed by
`docker compose config --format json`. Tests never start containers.
"""

import json
import os
import subprocess
from pathlib import Path

import pytest

STACK_DIR = Path(__file__).resolve().parent.parent

# A complete, valid set of values. Tests remove or change entries as needed.
VALID_ENV = {
    "DOCS_ROOT": "/srv/media-vault/documents",
    "DOCS_HOST": "docs.example-tailnet.ts.net",
    "POSTGRES_PASSWORD": "test-db-password",
    "NEXTCLOUD_ADMIN_USER": "owner",
    "NEXTCLOUD_ADMIN_PASSWORD": "test-admin-password",
}


class ComposeResult:
    def __init__(self, proc: subprocess.CompletedProcess):
        self.returncode = proc.returncode
        self.stdout = proc.stdout
        self.stderr = proc.stderr

    @property
    def model(self) -> dict:
        assert self.returncode == 0, f"docker compose config failed:\n{self.stderr}"
        return json.loads(self.stdout)


def _run_config(tmp_path: Path, env_values: dict, files: list[str]) -> ComposeResult:
    env_file = tmp_path / "test.env"
    env_file.write_text("".join(f"{k}={v}\n" for k, v in env_values.items()), encoding="utf-8")

    # Start from the real environment but drop every variable the stack reads,
    # so neither the developer's shell nor a local .env can influence the result.
    proc_env = {k: v for k, v in os.environ.items() if k not in VALID_ENV and not k.startswith("DOCS_")}

    cmd = ["docker", "compose", "--project-directory", str(STACK_DIR), "--env-file", str(env_file)]
    for f in files:
        cmd += ["-f", str(STACK_DIR / f)]
    cmd += ["config", "--format", "json"]
    proc = subprocess.run(cmd, capture_output=True, text=True, env=proc_env, cwd=STACK_DIR)
    return ComposeResult(proc)


@pytest.fixture
def compose_config(tmp_path):
    """Return a function that resolves the Compose model for the given env values and files."""

    def run(env_values: dict | None = None, files: list[str] | None = None) -> ComposeResult:
        values = dict(VALID_ENV) if env_values is None else env_values
        return _run_config(tmp_path, values, files or ["docker-compose.yml"])

    return run
