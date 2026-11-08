# Document store

Nextcloud with PostgreSQL and Redis, reachable only from your tailnet. Files are stored as plain files on the SSD.

## Tailscale (one-time, in the [admin console](https://login.tailscale.com/admin))

The store gets its own tailnet node (`docs`) and is reachable only at `https://docs.<your-tailnet>.ts.net`. No container publishes a port on the Pi, and Funnel (public internet access) stays off.

1. **DNS:** enable **MagicDNS** and **HTTPS Certificates** (already done if Synapse runs).
2. **Access controls:** add the tag and allow only your own user to reach it on port 443, next to the existing Synapse entries:
   ```json
   "tagOwners": { "tag:docs": ["autogroup:admin"] },
   "grants": [
     { "src": ["you@example.com"], "dst": ["tag:docs"], "ip": ["tcp:443"] }
   ]
   ```
3. **Settings → Keys:** generate an auth key with the tag `tag:docs` and put it into `.env` as `TS_AUTHKEY`. Tagged nodes don't expire. After the first successful start, you can revoke the key: the node identity is kept in the `docs-ts` volume.

`DOCS_HOST` in `.env` must be `<TS_HOSTNAME>.<your-tailnet>.ts.net`, for example `docs.tail1234.ts.net`. Nextcloud stores it as a trusted host name during its first install, and generates all links with it.

## First start

1. Copy `.env.example` to `.env` and fill in every value. `POSTGRES_PASSWORD` and `NEXTCLOUD_ADMIN_PASSWORD` must be long random values.
2. Create the data folders under `DOCS_ROOT`. On the Pi they must belong to uid 33 (`www-data`). Make sure [memory accounting](#pi-prerequisite-memory-accounting) is on, too.
   ```bash
   sudo mkdir -p /srv/media-vault/documents/data /srv/media-vault/documents/config /srv/media-vault/documents/custom_apps
   sudo chown -R 33:33 /srv/media-vault/documents
   ls -l /srv/media-vault/documents      # exactly: config, custom_apps, data, owned by 33
   ```
3. Start the stack and wait until every service is `healthy`. The first start installs Nextcloud, which takes about 1 minute on a PC and several minutes on the Pi:
   ```bash
   docker compose up -d --wait
   docker compose ps
   ```
4. Apply the settings **before the first login** (see [Settings script](#settings-script-configuresh)):
   ```bash
   scripts/configure.sh
   ```
5. Log in with `NEXTCLOUD_ADMIN_USER` / `NEXTCLOUD_ADMIN_PASSWORD`. There is no sign-up; this is the only account.

The admin values in `.env` are only used for that first install. Changing them later does nothing. Change the password in Nextcloud instead (**Settings → Security**).

`docker compose down` followed by `up -d` keeps all files and settings. Your files live under `DOCS_ROOT/data/<user>/files/` as normal files.

## Phone and PC

Every device needs **Tailscale switched on** and logged in to your account. Without it, the store can't be reached.

### Phone (Android / iOS)

1. Install **Nextcloud** from the Play Store or App Store (the app by *Nextcloud GmbH*, not "Nextcloud Talk").
2. Open the app → **Log in** → server address `https://docs.<your-tailnet>.ts.net` → log in with the owner account in the browser window that opens → **Grant access**.
3. If the app offers **Auto upload** (photos/videos), choose **No / Not now**. Photos and videos belong to the media server, not to the document store. Check this later under **Settings → Auto upload**: no folder may be switched on.
4. Uploading: open a folder → **+** → **Upload files** (or from another app: *Share* → *Nextcloud*).

### PC (desktop sync client)

1. Install the **Nextcloud desktop client** from [nextcloud.com/install](https://nextcloud.com/install/#install-clients).
2. **Log in to your Nextcloud** → `https://docs.<your-tailnet>.ts.net` → log in in the browser → **Grant access**.
3. Choose a local folder (e.g. `Documents\Nextcloud`) and what to sync. **Virtual files** saves disk space: files are downloaded only when you open them.
4. Files you put into the local folder appear in Nextcloud, and the other way round.

## Settings script (`configure.sh`)

`scripts/configure.sh` applies the store's Nextcloud settings with `occ`. Run it after the first start and any time later, for example after an upgrade. It is safe to run repeatedly; a second run changes nothing. It needs `bash` (on Windows: Git Bash) and the running stack.

| Setting | Value |
|---|---|
| Background jobs | `cron`: the `cron` container runs them every 5 minutes |
| Public link shares | off: files are only reachable for logged-in users |
| Disabled apps | `federation`, `photos` (photos belong to the media server), `firstrunwizard`, `recommendations`, `weather_status` |
| Brute-force protection | `bruteforcesettings` enabled |
| Phone region | `DOCS_PHONE_REGION` from `.env` (default `DE`) |
| Maintenance window | starts at 01:00 UTC |
| Sample files for new accounts | none (`skeletondirectory` empty). Nextcloud copies samples on the first login, so run the script before that. |

Before changing anything, the script checks that `DOCS_ROOT/{data,config,custom_apps}` exist and are writable by uid 33. If not, it stops with an error and says how to fix it.

### Blocked after failed logins

After more than 10 failed logins from one address within 30 minutes, Nextcloud blocks that address. Even the correct password then gets `HTTP 429` until the 30 minutes are over. To lift the block early:

```bash
docker compose exec -u www-data nextcloud php occ security:bruteforce:attempts <ip> login   # show attempts
docker compose exec -u www-data nextcloud php occ security:bruteforce:reset <ip>            # lift the block
```

### Files copied directly onto the disk

Nextcloud only knows about files that arrived through Nextcloud (web UI, apps, sync client). If you copy files directly into `DOCS_ROOT/data/<user>/files/`, for example from a USB stick on the Pi, they stay invisible until Nextcloud scans for them:

```bash
sudo chown -R 33:33 /srv/media-vault/documents/data/<user>/files     # files must belong to www-data
docker compose exec -u www-data nextcloud php occ files:scan <user>       # or --all for every user
```

For everyday use, always upload through the clients.

### Local development

Run the stack on your PC at `http://127.0.0.1:8081`, without Tailscale:

```bash
# in .env: DOCS_ROOT=../dev-data/documents (the repo's dev-data/ folder is git-ignored)
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --wait
```

Nextcloud only stores its trusted host names when it installs. A dev install therefore trusts only `127.0.0.1`/`localhost`. Don't copy dev data to the Pi.

## Backup

Backups are **manual** snapshots on the external HDD (`BACKUP_MOUNT`, default `/mnt/synapse-backup`). Run one regularly and **always before an upgrade**:

```bash
sudo scripts/backup.sh
# Backup written: /mnt/synapse-backup/media-vault/documents/2026-11-08T170000 (87M)
```

`sudo` is needed because the data folder belongs to `www-data` and is not readable for other users.

What the script does:
1. It checks that the HDD is mounted. If not, it stops with `ERROR: backup drive not mounted at …` and writes nothing, so nothing lands on the SSD by mistake.
2. It switches Nextcloud into **maintenance mode**, so no file changes while copying. Clients wait and retry. Maintenance mode is always switched off again at the end, even after an error or Ctrl-C.
3. It writes a database dump (`db.dump`) and copies `data/`, `config/`, and `custom_apps/` into a new snapshot folder.
4. Files that didn't change since the previous snapshot are stored as **hard links**: every snapshot is complete, but only changed files take new space.
5. The snapshot gets its final name `YYYY-MM-DDTHHMMSS` only when it is complete. A `….partial` folder is an interrupted run. It can be deleted, and it is never used as a base for the next snapshot.

### Restore

A restore **replaces the current database and all files** with a snapshot. Everything changed after that snapshot is lost.

```bash
ls /mnt/synapse-backup/media-vault/documents/                      # pick a snapshot
sudo scripts/restore.sh /mnt/synapse-backup/media-vault/documents/2026-11-08T170000
# Type 'yes' to continue: yes
```

1. The script only accepts a complete snapshot (`YYYY-MM-DDTHHMMSS` with `db.dump`, `data/`, `config/`, `custom_apps/`). It refuses `….partial` folders before asking anything.
2. Anything other than `yes` cancels without changing anything.
3. It stops Nextcloud and the cron container, then recreates the database from `db.dump`. Table and database owners stay Nextcloud's own database user (e.g. `oc_admin`, from the snapshot's `config.php`). On a fresh database server that user is created again.
4. It copies `data/`, `config/`, and `custom_apps/` back. Files that aren't in the snapshot are removed.
5. It starts Nextcloud, waits until it is healthy, and starts cron again.
6. It sets a new **data fingerprint**, so the phone apps and the desktop client notice that the server went back in time. They download the restored state instead of uploading deleted files again or creating conflict copies. Then it switches maintenance mode off and rescans the files.

A restore also works when Nextcloud itself is broken, for example when the database can't be read. It takes about a minute plus the time to copy the files.

If it fails halfway, Nextcloud stays in maintenance mode. Fix the cause (the error message names it) and run the restore again.

### Deleting old snapshots

Thanks to the hard links, any snapshot can be deleted without affecting the others. For example, keep the newest 10:

```bash
cd /mnt/synapse-backup/media-vault/documents
ls -1d ????-??-??T?????? | head -n -10 | xargs -r sudo rm -rf
sudo rm -rf ./*.partial          # interrupted runs
```

The HDD sits next to the Pi, so fire, theft, or a power surge could hit both. For more safety, rotate a second HDD that you keep elsewhere.

## Image versions

Every image is pinned to an exact tag. Each tag was checked for a `linux/arm64` build (Raspberry Pi 5).

| Image | Tag | arm64 | Notes |
|---|---|---|---|
| `nextcloud` | `35.0.2-apache` | yes (`linux/arm64/v8`) | Nextcloud 35 supports PostgreSQL 14–17 |
| `postgres` | `17.11-alpine` | yes (`linux/arm64/v8`) | |
| `redis` | `7.4.12-alpine` | yes (`linux/arm64/v8`) | |
| `tailscale/tailscale` | `v1.104.4` | yes (`linux/arm64`) | Same version as Synapse's sidecar |

Checked on 2026-11-08 with `docker buildx imagetools inspect`. To check a tag again:

```bash
docker buildx imagetools inspect nextcloud:35.0.2-apache | grep -A1 arm64
```

## Tests

- `test_compose.py` checks the resolved Compose configuration (`docker compose config`). It needs Docker but starts no containers.
- `test_configure.py`, `test_backup.py`, and `test_restore.py` (marker `stack`) need the running stack; they are skipped otherwise. **`test_restore.py` replaces the stack's data** with test snapshots, so only run it against a dev stack. Close files from the test (`keep.txt`) in the web editor first: the Text app locks open files, and the test then gets `423 Locked`. A leftover lock is lifted with `occ files:lock --unlock <fileid> <user>`. The backup and restore tests run the scripts in a small Linux container (`tests/runner/`) with the same tools as the Pi (bash, rsync, mountpoint), using a tmpfs as the backup drive. `test_configure.py` needs `bash` (on Windows: Git Bash).

```bash
python -m venv .venv && .venv/bin/pip install "pytest>=8,<9"   # Windows: .venv\Scripts\pip
.venv/bin/python -m pytest tests
```

## Upgrades

All images are pinned, so nothing changes until you change a tag in `docker-compose.yml`.

```bash
sudo scripts/backup.sh                              # always first
nano docker-compose.yml                             # raise the tag (nextcloud: in both services, nextcloud and cron)
docker compose pull
docker compose up -d --wait                         # Nextcloud runs its upgrade steps on start
docker compose exec -u www-data nextcloud php occ status   # check: new version, maintenance: false
scripts/configure.sh                                # re-apply settings (safe to repeat)
```

- **Nextcloud: one major version at a time.** Nextcloud refuses to skip majors. To go from 35 to 37, upgrade to the latest 36.x first, check that it runs, then to 37.x, with a backup before each step. Minor and patch updates within a major (e.g. 35.0.2 → 35.0.5) are a single step.
- **PostgreSQL major versions** (e.g. 17 → 18) can't reuse the data volume. Take a backup, run `docker compose down`, remove the volume (`docker volume rm media-vault-docs_docs-db`), change the tag, run `docker compose up -d db`, and then `scripts/restore.sh <snapshot>`. Check first that the Nextcloud version supports the new PostgreSQL version.
- **If an upgrade fails**, Nextcloud stays in maintenance mode. Set the old tag back and restore the backup you took before.

## Resource use

### Pi prerequisite: memory accounting

Raspberry Pi OS boots with `cgroup_disable=memory` (set by the firmware). Docker then **ignores every memory limit**: `docker info` warns `No memory limit support`, and `docker stats` shows `0B / 0B`. Turn memory accounting on once:

```bash
sudo cp /boot/firmware/cmdline.txt /boot/firmware/cmdline.txt.bak
sudo sed -i '1 s/$/ cgroup_enable=memory cgroup_memory=1/' /boot/firmware/cmdline.txt
cat /boot/firmware/cmdline.txt     # still ONE line, ending in "cgroup_enable=memory cgroup_memory=1"
sudo reboot
```

Containers created *before* this change keep running without limits. Recreate them once afterwards:

```bash
docker compose up -d --force-recreate --wait
docker inspect -f '{{.Name}} {{.HostConfig.Memory}}' $(docker compose ps -q)   # non-zero byte values
```

### Limits

Every container has a memory limit (design D9): nextcloud 768 MB, cron 640 MB, db 256 MB, redis 96 MB (a pure cache: 64 MB, nothing written to disk), tailscale 128 MB. At idle the whole stack needs well under 1 GB (about 0.25 GB measured), so it fits next to Synapse and the media server on an 8 GB Pi. All containers restart on their own after a crash or a reboot (`restart: unless-stopped`).
