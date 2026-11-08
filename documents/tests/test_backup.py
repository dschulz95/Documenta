"""Behavior of scripts/backup.sh (spec: document-backup).

Seam: run the real script in a Linux runner container (same tools as the Pi:
bash, rsync, mountpoint, docker compose) against the running stack, then
observe the snapshot folders and Nextcloud's maintenance mode.
"""

import pytest

from scripts_runner import (
    BACKUP_MOUNT, SNAPSHOT_NAME, SNAPSHOTS, STUB_PATH, RUNNER_NAME,
    in_runner, install_stub, occ, run_script, runner, sh, snapshots,
)

pytestmark = pytest.mark.stack


def run_backup(backup_mount: str = BACKUP_MOUNT, stubs: bool = False):
    return run_script("backup.sh", env={"BACKUP_MOUNT": backup_mount}, stubs=stubs)


@pytest.fixture
def empty_backup(runner):
    in_runner(f"rm -rf {BACKUP_MOUNT}/*")
    occ("maintenance:mode", "--off")
    yield


def test_backup_writes_a_complete_dated_snapshot(empty_backup):
    result = run_backup()

    assert result.returncode == 0, result.stderr
    [name] = snapshots()
    assert SNAPSHOT_NAME.match(name)
    snap = f"{SNAPSHOTS}/{name}"
    assert snap in result.stdout
    # A PostgreSQL custom-format dump starts with "PGDMP".
    assert in_runner(f"head -c 5 {snap}/db.dump").stdout == "PGDMP"
    assert in_runner(f"cmp {snap}/data/owner/files/Contracts/rent.pdf ../dev-data/documents/data/owner/files/Contracts/rent.pdf").returncode == 0
    assert in_runner(f"test -f {snap}/config/config.php && test -d {snap}/custom_apps").returncode == 0


def test_unchanged_files_take_no_extra_space_in_the_next_snapshot(empty_backup):
    assert run_backup().returncode == 0
    in_runner("sleep 1")  # snapshot names have one-second resolution
    second = run_backup()

    assert second.returncode == 0, second.stderr
    first_snap, second_snap = (f"{SNAPSHOTS}/{n}" for n in snapshots())
    pdf = "data/owner/files/Contracts/rent.pdf"
    inodes = in_runner(f"stat -c %i {first_snap}/{pdf} {second_snap}/{pdf}").stdout.split()
    assert inodes[0] == inodes[1], "unchanged file was copied instead of hard-linked"
    dumps = in_runner(f"stat -c %i {first_snap}/db.dump {second_snap}/db.dump").stdout.split()
    assert dumps[0] != dumps[1]


def test_an_interrupted_backup_never_looks_complete_and_leaves_maintenance_mode(empty_backup):
    install_stub("rsync", "touch /tmp/copy-started\nexec sleep 300")
    in_runner("rm -f /tmp/copy-started")
    env = ["-e", f"BACKUP_MOUNT={BACKUP_MOUNT}", "-e", f"PATH={STUB_PATH}"]
    sh(["docker", "exec", "-d", *env, RUNNER_NAME, "bash", "scripts/backup.sh"])
    assert in_runner("for i in $(seq 60); do [ -f /tmp/copy-started ] && exit 0; sleep 1; done; exit 1").returncode == 0

    # Like Ctrl-C: the script and its copy process both get the signal.
    in_runner("pkill -INT -f scripts/backup.sh; pkill -INT -f 'sleep 300'; sleep 3")

    names = snapshots()
    assert [n for n in names if SNAPSHOT_NAME.match(n)] == [], names
    assert len([n for n in names if n.endswith(".partial")]) == 1, names
    assert occ("config:system:get", "maintenance") == "false"


def test_backup_refuses_a_drive_that_is_not_mounted(empty_backup):
    not_mounted = "/mnt/not-mounted"  # a plain folder on the runner's own disk
    in_runner(f"rm -rf {not_mounted} && mkdir -p {not_mounted}")

    result = run_backup(backup_mount=not_mounted)

    assert result.returncode != 0
    assert not_mounted in result.stderr
    assert in_runner(f"ls -A {not_mounted}").stdout == ""
    assert occ("config:system:get", "maintenance") == "false"


def test_files_are_copied_in_maintenance_mode_and_the_store_is_usable_afterwards(empty_backup):
    # The stub records Nextcloud's maintenance flag at the moment the files are copied.
    install_stub("rsync", (
        "docker compose exec -T -u www-data nextcloud php occ config:system:get maintenance > /tmp/maintenance-during-copy\n"
        'exec /usr/bin/rsync "$@"'
    ))

    result = run_backup(stubs=True)

    assert result.returncode == 0, result.stderr
    assert in_runner("cat /tmp/maintenance-during-copy").stdout.strip() == "true"
    assert occ("config:system:get", "maintenance") == "false"
