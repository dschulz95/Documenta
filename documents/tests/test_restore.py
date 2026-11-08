"""Behavior of scripts/restore.sh (spec: document-backup, Full restore).

Seam: run the real script in the Linux runner against the running stack, with
snapshots made by backup.sh on the runner's tmpfs. Observe through WebDAV
(from inside the nextcloud container), occ, and the stack's health.
"""

import pytest

from conftest import STACK_DIR
from scripts_runner import BACKUP_MOUNT, SNAPSHOTS, health, in_runner, occ, run_script, runner, sh, snapshots

pytestmark = pytest.mark.stack


def owner_password() -> str:
    for line in (STACK_DIR / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("NEXTCLOUD_ADMIN_PASSWORD="):
            return line.split("=", 1)[1].strip()
    raise AssertionError("NEXTCLOUD_ADMIN_PASSWORD missing in .env")


def dav(method: str, path: str, body: str | None = None) -> tuple[int, str]:
    """WebDAV request as the owner, sent from inside the nextcloud container."""
    url = f"http://localhost/remote.php/dav/files/owner/{path}"
    cmd = ["docker", "compose", "exec", "-T", "nextcloud", "curl", "-s", "-u", f"owner:{owner_password()}",
           "-X", method, "-w", "\n%{http_code}", url]
    if body is not None:
        cmd[-3:-3] = ["--data-binary", "@-"]
    out = sh(cmd, cwd=STACK_DIR, input=body).stdout
    content, _, code = out.rpartition("\n")
    return int(code or 0), content


def db_marker() -> str:
    return occ("config:app:get", "restoretest", "marker")


def run_restore(snapshot: str, answer: str = "yes"):
    return run_script("restore.sh", snapshot, stdin=f"{answer}\n")


@pytest.fixture(scope="module")
def snapshot(runner):
    """A snapshot that contains keep.txt and db marker 'before'."""
    occ("maintenance:mode", "--off")
    in_runner(f"rm -rf {BACKUP_MOUNT}/*")
    for leftover in ("after-snapshot.txt", "written-after-restore.txt"):  # from earlier runs
        dav("DELETE", leftover)
    assert dav("PUT", "keep.txt", "kept by the snapshot")[0] in (201, 204)
    occ("config:app:set", "restoretest", "marker", "--value=before")
    assert run_script("backup.sh").returncode == 0
    [name] = snapshots()
    return f"{SNAPSHOTS}/{name}"


@pytest.mark.parametrize("bad", ["missing", "partial"])
def test_something_that_is_not_a_complete_snapshot_is_refused_before_asking(snapshot, bad):
    path = f"{SNAPSHOTS}/2000-01-01T000000"
    if bad == "partial":
        path = f"{snapshot}.partial"
        in_runner(f"cp -a {snapshot} {path}")
    occ("config:app:set", "restoretest", "marker", "--value=untouched")

    result = run_restore(path, answer="yes")

    assert result.returncode != 0
    assert path in result.stderr
    assert "Type 'yes'" not in result.stdout
    assert db_marker() == "untouched"
    in_runner(f"rm -rf {snapshot}.partial")


def test_answering_anything_but_yes_changes_nothing(snapshot):
    dav("PUT", "after-snapshot.txt", "created after the snapshot")
    occ("config:app:set", "restoretest", "marker", "--value=after")

    result = run_restore(snapshot, answer="no")

    assert result.returncode != 0
    assert "cancel" in (result.stdout + result.stderr).lower()
    assert dav("GET", "after-snapshot.txt") == (200, "created after the snapshot")
    assert db_marker() == "after"
    assert occ("config:system:get", "maintenance") == "false"


@pytest.fixture(scope="module")
def restored(snapshot):
    """State changed after the snapshot, then the snapshot restored with 'yes'."""
    dav("DELETE", "keep.txt")
    dav("PUT", "after-snapshot.txt", "created after the snapshot")
    occ("config:app:set", "restoretest", "marker", "--value=after")
    fingerprint_before = occ("config:system:get", "data-fingerprint")

    result = run_restore(snapshot, answer="yes")

    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    return {"fingerprint_before": fingerprint_before, "output": result.stdout}


def test_a_file_deleted_after_the_snapshot_is_back(restored):
    assert dav("GET", "keep.txt") == (200, "kept by the snapshot")


def test_the_database_is_back_at_the_snapshot_state(restored):
    assert db_marker() == "before"


def test_a_file_created_after_the_snapshot_is_gone(restored):
    assert dav("GET", "after-snapshot.txt")[0] == 404


def test_the_store_is_usable_afterwards(restored):
    assert occ("config:system:get", "maintenance") == "false"
    assert health("nextcloud") == "healthy"
    assert sh(["docker", "compose", "ps", "cron", "--format", "{{.State}}"], cwd=STACK_DIR).stdout.strip() == "running"
    assert dav("PUT", "written-after-restore.txt", "ok")[0] in (201, 204)


def test_sync_clients_are_told_the_server_went_back_in_time(restored):
    # A new data-fingerprint makes desktop/mobile clients resync instead of re-uploading
    # deleted files or creating conflict copies.
    after = occ("config:system:get", "data-fingerprint")
    assert after and after != restored["fingerprint_before"]
