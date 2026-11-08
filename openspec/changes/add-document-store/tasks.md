# Tasks

> **Note:** the repository was flattened after slice 8 (owner's decision). Paths written as `documents/X` below now live at `X` in the repo root.

Each section is a vertical slice: it delivers one behavior the owner can observe and is tested end to end on its own. Each slice builds on the ones before it.

## 1. Slice: The owner can log in to a local document store

- [x] 1.1 Create the repo layout (design D10): a root `README.md` that describes the layout with one folder per stack, a root `.gitignore` that ignores `.env` and local test data, and `documents/` with `tailscale/` and `scripts/`. Pin the image tags for `nextcloud:<x.y.z>-apache`, `postgres:17-alpine`, and `redis:<7.x>-alpine`. Check each tag's arm64 manifest with `docker buildx imagetools inspect` and record the tags in `documents/README.md`.
- [x] 1.2 Write `documents/docker-compose.yml` (project name `media-vault-docs`) with the services `nextcloud`, `db`, and `redis`. Use the networks `web` (fixed subnet) and `data` (internal). Use the named volumes `docs-html` and `docs-db`, and bind mounts for `${DOCS_ROOT}/{data,config,custom_apps}`. Add health checks and `depends_on: service_healthy`, and no `ports:`. Write `.env.example` and use `${VAR:?}` for the required values. Write `docker-compose.dev.yml`, which publishes Nextcloud on `127.0.0.1:${DOCS_DEV_PORT:-8081}` with `OVERWRITEPROTOCOL=http`.
- [x] 1.3 Verify the slice:
  - `docker compose config` fails and names `POSTGRES_PASSWORD` when it is unset (spec: Configuration from .env).
  - The production compose file has no published ports.
  - The dev stack reaches `healthy`.
  - The owner from `.env` can log in at `http://127.0.0.1:8081`, and there is no sign-up option (spec: Owner account).
  - After `docker compose down && up -d`, the login still works with the same data (spec: Data on the SSD).
  - Document the first-start steps in `documents/README.md`.

## 2. Slice: The owner can organize, upload, and preview documents in the browser

- [x] 2.1 Configure uploads and previews (design D7): `PHP_UPLOAD_LIMIT=16G` and `PHP_MEMORY_LIMIT=512M`, with the default `files`, `viewer`, `files_pdfviewer`, and `text` apps enabled.
- [x] 2.2 Verify on the dev stack (spec: document-storage):
  - Create `Taxes/2026`, upload a PDF, and move it to `Contracts/`.
  - Preview a PDF, a JPEG, and a TXT file in the browser.
  - Upload a file of at least 4 GB and compare its SHA-256 with the file in `DOCS_ROOT/data/<owner>/files/...`.
  - With the stack stopped, open the PDF directly from the data folder (spec: Plain files on disk).
  - Fill the test disk and confirm that an upload fails with an error and leaves no partial file.
  - Record the results in a checklist in the change folder.
  - Document `occ files:scan` for files copied directly onto the disk.

## 3. Slice: Background jobs run, and public sharing is impossible

- [x] 3.1 Add the `cron` service: the same image with `entrypoint: /cron.sh`, the shared mounts, and a health check. Write `documents/scripts/configure.sh` (design D6). It is idempotent and uses `occ`. It:
  - sets `backgroundjobs_mode cron` and `shareapi_allow_links no`
  - disables federation
  - sets the phone region and the maintenance window
  - disables `photos`, `firstrunwizard`, `recommendations`, and `weather_status`
  - checks that `bruteforcesettings` is enabled
  - sets an empty `skeletondirectory`, so new accounts start without Nextcloud's sample files
  - checks that uid 33 can write to `DOCS_ROOT`
- [x] 3.2 Verify:
  - Running `configure.sh` twice produces no errors and the same settings.
  - The sharing panel of a file offers no public link (spec: No public sharing).
  - After 15 minutes, the admin overview shows a cron run within the last 5 minutes (spec: Background jobs).
  - More than 10 wrong passwords within 30 minutes block further logins from that address until the block is lifted (spec: Brute-force protection).
  - Document `configure.sh` in the README.

## 4. Slice: The store is reachable from the tailnet over HTTPS only

- [x] 4.1 Add the `tailscale` sidecar (design D4): pinned `tailscale/tailscale:v1.x.y`, `TS_USERSPACE=true`, `TS_SERVE_CONFIG`, `tag:docs`, the `docs-ts` volume, and a `/healthz` health check. Write `tailscale/serve.json` (proxy to `http://nextcloud:80`, `AllowFunnel: false`). Set `NEXTCLOUD_TRUSTED_DOMAINS`, `OVERWRITEPROTOCOL`, `OVERWRITECLIURL`, and `TRUSTED_PROXIES` (the `web` subnet). Don't set `OVERWRITEHOST`: it would switch off Nextcloud's trusted-domain check (found in 4.2).
- [x] 4.2 Verify with a real tailnet auth key (on the Pi, or on the dev machine with Docker):
  - `https://docs.<tailnet>.ts.net` loads with a valid certificate from a tailnet device.
  - A file's internal link starts with that URL.
  - A request with a different `Host` header is rejected as an untrusted domain.
  - A non-tailnet device gets no answer.
  - (spec: document-access)
  - Document the Tailscale admin-console steps (tag, grant, auth key) in the README.

## 5. Slice: The owner uploads from the phone and the PC sync client

- [x] 5.1 Verify:
  - With the Nextcloud Android or iOS app connected to `https://docs.<tailnet>.ts.net`, a PDF uploaded from the phone into `Contracts/` appears in the web UI.
  - The desktop sync client syncs a folder both ways.
  - (spec: Upload from any client)
- [x] 5.2 Document the phone and desktop setup in the README, including the instruction to **leave auto-upload off**. Verify that following the README on a fresh phone leaves auto-upload disabled (spec: No photo auto-upload).

## 6. Slice: The owner can take a backup snapshot

- [x] 6.1 Write `documents/scripts/backup.sh` (design D8). It:
  - checks `mountpoint -q "$BACKUP_MOUNT"`
  - turns maintenance mode on, with a `trap` on EXIT that turns it off
  - runs `pg_dump -Fc` into `<ts>.partial/db.dump`
  - runs `rsync -aH --link-dest` on `data`, `config`, and `custom_apps`
  - renames `<ts>.partial` to `<ts>` and prints the path and size
- [x] 6.2 Verify:
  - `shellcheck` passes.
  - With a test mount, a snapshot is created and maintenance mode is off afterwards.
  - A second run without changes adds only about the size of the dump (`du -sh`).
  - An unmounted `BACKUP_MOUNT` exits non-zero, names the mount point, and writes nothing.
  - A run killed during rsync leaves only `.partial`, and maintenance mode is off.
  - (spec: Manual backup, Backup refuses a missing drive, Incomplete snapshots are recognizable, Space-efficient snapshots)
  - Document the backup and manual pruning in the README.

## 7. Slice: The owner can restore a snapshot

- [x] 7.1 Write `documents/scripts/restore.sh <snapshot>` (design D8). It:
  - asks for a typed `yes`
  - turns maintenance mode on and stops `nextcloud` and `cron`
  - drops and recreates the database, then runs `pg_restore`
  - runs `rsync -aH --delete` back into `DOCS_ROOT`
  - starts the services, runs `maintenance:data-fingerprint` and `files:scan --all`, and turns maintenance mode off
- [x] 7.2 Verify:
  - `shellcheck` passes.
  - Answering "no" changes nothing.
  - A file deleted after a snapshot reappears in the web UI and in a connected sync client after restoring that snapshot, without conflict copies.
  - (spec: Full restore)
  - Document the restore in the README.

## 8. Slice: The store runs reliably on the Pi next to Synapse

- [x] 8.1 Add `mem_limit` to every container (design D9) and `restart: unless-stopped`. Document the upgrade procedure in the README: backup first, one Nextcloud major version at a time.
- [ ] 8.2 Deploy on the Pi following the README. Verify:
  - All images run as arm64 without emulation.
  - Stopping and starting `media-vault-docs` leaves Synapse reachable (spec: Independent stack).
  - After a Pi reboot, the store is reachable again within a few minutes (spec: Health and automatic restart).
  - After 10 idle minutes, `docker stats` shows at most about 1 GB in total (spec: Bounded resource use).
  - A minor-version image upgrade keeps all files (spec: Upgrade with data kept).
  - `scripts/backup.sh` writes a snapshot to `/mnt/synapse-backup/media-vault/documents/`.

## Workflow follow-up

- Archive the change with `/opsx:archive` after the Pi checks pass.
