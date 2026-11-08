"""Behavior of scripts/configure.sh against the running stack (spec: document-access, document-deployment).

Seam: run the script, then observe Nextcloud's state through `occ`.
Needs a running, healthy stack (e.g. the dev stack); otherwise the tests are skipped.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import STACK_DIR

pytestmark = pytest.mark.stack


def _bash() -> str:
    candidates = [os.environ.get("BASH_FOR_TESTS"), r"C:\Program Files\Git\bin\bash.exe", shutil.which("bash")]
    for c in candidates:
        if c and Path(c).exists() and "system32" not in c.lower():
            return c
    pytest.skip("no usable bash found (set BASH_FOR_TESTS)")


def occ(*args: str) -> str:
    proc = subprocess.run(
        ["docker", "compose", "exec", "-T", "-u", "www-data", "nextcloud", "php", "occ", *args],
        cwd=STACK_DIR, capture_output=True, text=True,
    )
    return proc.stdout.strip()


def run_configure(extra_env: dict | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ, **(extra_env or {}))
    return subprocess.run([_bash(), "scripts/configure.sh"], cwd=STACK_DIR, capture_output=True, text=True, env=env)


@pytest.fixture(scope="module", autouse=True)
def running_stack():
    proc = subprocess.run(
        ["docker", "compose", "ps", "nextcloud", "--format", "{{.Health}}"],
        cwd=STACK_DIR, capture_output=True, text=True,
    )
    if proc.stdout.strip() != "healthy":
        pytest.skip("document stack is not running and healthy")


APPS_TO_DISABLE = ["federation", "photos", "firstrunwizard", "recommendations", "weather_status"]


def enabled_apps() -> set[str]:
    out = occ("app:list", "--enabled")
    return {line.strip()[2:].split(":")[0] for line in out.splitlines() if line.strip().startswith("- ")}


def reset_to_unconfigured_state():
    """Put Nextcloud into the opposite of what configure.sh should produce,
    so a passing test proves the script changed it."""
    occ("background:ajax")
    occ("config:app:set", "core", "shareapi_allow_links", "--value=yes")
    occ("app:enable", *APPS_TO_DISABLE)
    occ("app:disable", "bruteforcesettings")
    occ("config:system:delete", "default_phone_region")
    occ("config:system:delete", "maintenance_window_start")
    occ("config:system:delete", "skeletondirectory")


@pytest.fixture(scope="module")
def configured():
    reset_to_unconfigured_state()
    result = run_configure()
    assert result.returncode == 0, f"configure.sh failed:\n{result.stdout}\n{result.stderr}"
    return result


def test_background_jobs_run_from_cron(configured):
    assert occ("config:app:get", "core", "backgroundjobs_mode") == "cron"


def test_public_link_shares_are_disabled(configured):
    assert occ("config:app:get", "core", "shareapi_allow_links") == "no"


def test_unneeded_apps_are_disabled_and_brute_force_protection_is_enabled(configured):
    enabled = enabled_apps()

    assert enabled & set(APPS_TO_DISABLE) == set()
    assert "bruteforcesettings" in enabled


def settings_snapshot() -> dict:
    return {
        "mode": occ("config:app:get", "core", "backgroundjobs_mode"),
        "links": occ("config:app:get", "core", "shareapi_allow_links"),
        "apps": sorted(enabled_apps()),
        "region": occ("config:system:get", "default_phone_region"),
        "maintenance": occ("config:system:get", "maintenance_window_start"),
        "skeleton": occ("config:system:get", "skeletondirectory"),
    }


def test_running_twice_succeeds_and_changes_nothing(configured):
    before = settings_snapshot()

    second = run_configure()

    assert second.returncode == 0, second.stderr
    assert settings_snapshot() == before


def test_missing_docs_root_stops_with_an_error_naming_it(configured, tmp_path):
    missing = tmp_path / "no-such-folder"
    occ("config:app:set", "core", "shareapi_allow_links", "--value=yes")

    result = run_configure({"DOCS_ROOT": str(missing)})

    assert result.returncode != 0
    assert "DOCS_ROOT" in result.stderr
    assert occ("config:app:get", "core", "shareapi_allow_links") == "yes", "changed settings before failing"
    assert run_configure().returncode == 0  # restore the configured state for later tests


def test_new_accounts_start_without_sample_files(configured):
    # A missing key prints nothing; an explicitly empty value prints "" as JSON.
    assert occ("config:system:get", "skeletondirectory", "--output=json") == '""'


def test_phone_region_defaults_to_germany_and_maintenance_runs_at_night(configured):
    assert occ("config:system:get", "default_phone_region") == "DE"
    assert occ("config:system:get", "maintenance_window_start") == "1"
