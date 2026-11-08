# Design

## Context

- **Target hardware.** A Raspberry Pi 5 with 8 GB RAM, booting 64-bit Raspberry Pi OS from an SSD, with Docker Compose v2. Synapse already runs on it as a separate Compose project with its own Tailscale sidecar. A media server stack will follow in this repo.
- **Backup drive.** An external USB HDD is mounted at `/mnt/synapse-backup` (ext4, `nofail`). This change shares that drive, but writes into its own subfolder.
- **Tailnet.** MagicDNS and HTTPS certificates are already enabled. Synapse's pattern works: a Tailscale container in userspace mode serves HTTPS and proxies to an internal container, and no host ports are published.
- **Repository.** The `media-vault` repo is empty apart from OpenSpec. This is its first change, so it also sets the repo layout.
- **Requirements** are in `specs/document-*/spec.md`. Motivation is in proposal.md.

## Goals / Non-Goals

**Goals:**
- Stock Nextcloud with as little custom code as possible. Only shell scripts and configuration.
- A layout and backup style that the media stack can copy: one folder per stack, one Tailscale node per stack, and host-path data on the SSD.
- Files and config stored in host folders, so a backup is "dump the database and copy the folders".

**Non-Goals:**
- Performance tuning beyond fitting into the RAM budget. There is one user, and a few clients at most.
- High availability. Durability comes only from the manual backup.
- Automating the one-time Tailscale admin-console setup. It is documented, not scripted.

## Decisions

### D1: Community `nextcloud:<version>-apache` image
- One container serves both PHP and HTTP. For a single user, Apache with mod_php is fast enough and saves the separate nginx container that the `fpm` variant needs.
- *Alternative: Nextcloud All-in-One (AIO).* Rejected. AIO manages its own containers through the Docker socket and expects to own ports 80/443/8080 and a public domain. It conflicts with the tailnet-only sidecar design and with "no published ports".
- *Alternative: `fpm` + nginx.* Rejected for now. It is slightly faster but adds a container and nginx config. Switching later is possible without touching data.

### D2: PostgreSQL 17 (alpine) as the database, Redis for locking
- Postgres is officially supported by Nextcloud and is already used by Synapse, so backup and restore use the same tools (`pg_dump -Fc` / `pg_restore`). It is tuned small, like Synapse's: `shared_buffers=64MB` and `max_connections=30`.
- Redis provides *transactional file locking*. Without it, Nextcloud falls back to locking in the database, which is slow and causes lock errors with sync clients. APCu serves as the local memory cache, which the image includes.
- *Alternative: MariaDB.* It is the most common Nextcloud database, but it would be a second database engine to operate next to Synapse. Rejected.
- *Alternative: SQLite.* Nextcloud discourages it for sync clients because of locking problems. Rejected.

### D3: Background jobs in a cron sidecar
- A second container runs the same Nextcloud image with `entrypoint: /cron.sh` and shares the code and data mounts. Nextcloud is set to `backgroundjobs_mode=cron`.
- *Alternative: AJAX or webcron.* Jobs would only run while a browser page is open. That breaks the "every 5 minutes" requirement. Rejected.

### D4: Networks and access path

```
 tailnet --443/HTTPS--> [docs-tailscale] --http:80--> [nextcloud] --> [db]
                         serve.json proxy              [cron] ------> [redis]
                         (TLS terminated here)
 networks:  web  = tailscale, nextcloud, cron   (fixed subnet, egress allowed)
            data = nextcloud, cron, db, redis    (internal: no route out)
```

- Like Synapse, the Tailscale sidecar runs with `TS_USERSPACE=true` and `TS_SERVE_CONFIG`, `AllowFunnel: false`, and the tag `tag:docs`. No service has a `ports:` entry.
- The `web` network gets a fixed subnet (for example `172.30.10.0/24`), so Nextcloud's `trusted_proxies` can name it exactly. Nextcloud then accepts `X-Forwarded-For` / `X-Forwarded-Proto` only from the sidecar.
- Nextcloud is configured through the image's environment variables:
  - `NEXTCLOUD_TRUSTED_DOMAINS="${DOCS_HOST} localhost"`. `localhost` is needed only for the container's own health check and is not reachable from outside.
  - `OVERWRITEPROTOCOL=https` and `OVERWRITECLIURL=https://${DOCS_HOST}`.
  - **No `OVERWRITEHOST`.** Tailscale Serve forwards the original host name, so Nextcloud already sees `${DOCS_HOST}`. Setting `OVERWRITEHOST` would replace the host name of every request and switch off Nextcloud's own trusted-domain check. Measured during task 4.2: with it, a request with `Host: evil.example` got 200; without it, Nextcloud answers 400. Foreign host names are then rejected twice: by Tailscale (no TLS for other names) and by Nextcloud.
  - `TRUSTED_PROXIES=<web subnet>`.
- `web` keeps internet egress, so Nextcloud can check for updates and download apps.

### D5: Data on host folders on the SSD

```
${DOCS_ROOT}/                 e.g. /srv/media-vault/documents   (SSD, owned by uid 33 = www-data)
  data/                       -> /var/www/html/data      files: data/<owner>/files/<your tree>
  config/                     -> /var/www/html/config    config.php (instance secret, settings)
  custom_apps/                -> /var/www/html/custom_apps
named volumes:
  docs-html                   -> /var/www/html           Nextcloud code; refreshed by the image on upgrade
  docs-db                     -> Postgres data
  docs-redis                  -> (none needed; Redis runs without persistence)
```

- Files appear on disk as `data/<owner>/files/Contracts/rent.pdf`. That meets the "plain files on disk" requirement.
- `config/` must be backed up together with the database dump. It holds the `instanceid`, `passwordsalt`, and `secret`, and without them a restored database is useless. Keeping it in a host folder rather than inside the code volume makes that a simple folder copy.
- Files placed directly on disk are not seen by Nextcloud until it scans for them (`occ files:scan`). The README documents this. Normal use is always through the clients.

### D6: Configuration and first start
- `.env` holds:
  - `DOCS_ROOT` and `DOCS_HOST` (e.g. `docs.<tailnet>.ts.net`).
  - `TS_AUTHKEY` and `TS_HOSTNAME` (default `docs`).
  - `POSTGRES_PASSWORD`.
  - `NEXTCLOUD_ADMIN_USER` and `NEXTCLOUD_ADMIN_PASSWORD`.
  - `BACKUP_MOUNT` (default `/mnt/synapse-backup`).
- Required values use Compose's `${VAR:?message}` syntax, so a missing value stops `docker compose up` with a message that names it.
- The image installs Nextcloud on its own when the database and admin variables are set and the instance is not installed yet. Those admin variables only matter for that first install. The README warns that changing them later does nothing.
- After install, a one-time, idempotent `scripts/configure.sh` applies settings through `occ`. It can be re-run and makes the setup reproducible:
  - Background jobs: `backgroundjobs_mode cron`.
  - Sharing: disable public link shares (`shareapi_allow_links no`) and federation.
  - Defaults: phone region and maintenance window.
  - An empty `skeletondirectory`, so the owner's account starts without Nextcloud's sample files (sample photos, intro video, templates). Nextcloud copies them on the first login, so `configure.sh` has to run before the owner logs in for the first time.
  - Disable apps that are unnecessary or confusing here, such as `photos` (media belongs to the media server), `firstrunwizard`, `recommendations`, `weather_status`, and `federation`. Keep `files`, `viewer`, `files_pdfviewer`, `text`, and `bruteforcesettings`.
- *Alternative: mounting a custom `config/*.config.php`.* It covers settings stored in config.php but not app settings stored in the database, such as sharing rules. Rejected in favour of a single `occ` script.

### D7: Large uploads
- Clients upload in chunks (the web UI uses chunking v2, and the apps and desktop client use their own chunking). Each HTTP request stays small, so a 10 GB file never goes through as one request.
- Settings: `PHP_UPLOAD_LIMIT=16G` for any non-chunked fallback and `PHP_MEMORY_LIMIT=512M`. `APACHE_BODY_LIMIT` stays at the image default, because chunk size is far below it.
- Nextcloud checks free space before it accepts an upload and deletes the chunks of an upload that failed. This covers the "disk full" scenario.

### D8: Backup as rsync snapshots with hard links
Backups go to `${BACKUP_MOUNT}/media-vault/documents/`, with one folder per snapshot (for example `2026-11-08T142000`). `scripts/backup.sh` works like this:
1. Run `mountpoint -q "$BACKUP_MOUNT"`. If it fails, exit with an error and write nothing.
2. Turn on `occ maintenance:mode --on`. A `trap` on EXIT turns it off again on success, failure, or Ctrl-C.
3. Write `pg_dump -Fc` into `<ts>.partial/db.dump`.
4. Run `rsync -aH --delete --link-dest=<previous snapshot> ${DOCS_ROOT}/{data,config,custom_apps} <ts>.partial/`. Unchanged files become hard links, so each snapshot is complete but only changed files take space.
5. Rename `<ts>.partial` to `<ts>`, print the path and size, and leave maintenance mode.

`scripts/restore.sh <snapshot>`:
1. Ask the owner to type `yes`.
2. Turn on maintenance mode and stop `nextcloud` and `cron`.
3. Drop and recreate the database inside `db`, then run `pg_restore`.
4. Copy the snapshot back with `rsync -aH --delete <snapshot>/{data,config,custom_apps} ${DOCS_ROOT}/`.
5. Start `nextcloud` and `cron`.
6. Run `occ maintenance:data-fingerprint`, so sync clients know the server went back in time and don't re-upload deleted files as conflicts.
7. Run `occ files:scan --all` and turn maintenance mode off.

- *Alternative: `tar` archives per backup.* Every run would be a full copy, which costs a lot of space and time for large document trees. Rejected.
- *Alternative: snapshot tools such as restic or borg.* They deduplicate better and support encryption, but they add a tool and the files on the HDD are no longer readable as plain files. Possible later, so it stays out of this change.

### D9: Resource limits

| Container | `mem_limit` | Typical idle |
|---|---|---|
| nextcloud | 768m | ~250–350 MB |
| cron | 640m (above its 512 MB PHP limit, so a heavy job fails in PHP instead of being killed) | under 5 MB between runs |
| db | 256m | ~60–100 MB |
| redis | 96m (`maxmemory 64mb`, `allkeys-lru`, no persistence) | ~10 MB |
| tailscale | 128m | ~40 MB |

Idle total is about 0.4–0.6 GB, below the 1 GB target (measured on the dev stack in task 8.1: about 0.23 GB). The limits keep the worst case at about 1.9 GB.

### D10: Repository layout and version pinning

The GitHub repository **Documenta** contains only the document store, flat at the repo root. The media server gets its own repository. (Planned and first built as `documents/` inside a multi-stack `media-vault` repo; flattened by the owner's decision after slice 8. The paths `documents/X` in tasks.md and verification.md now mean `X`.)

```
Documenta/
  docker-compose.yml        name: media-vault-docs
  docker-compose.dev.yml    local development on 127.0.0.1:8081
  .env.example
  tailscale/serve.json
  scripts/configure.sh  backup.sh  restore.sh
  tests/                    pytest (compose config, scripts via a Linux runner)
  README.md                 setup, phone/PC clients, backup/restore, upgrade
  openspec/                 planning
```

- The image tags are fixed when the change is implemented: the current stable `nextcloud:<major>.<minor>.<patch>-apache`, `postgres:17-alpine`, `redis:<7.x>-alpine`, and the current `tailscale/tailscale:v1.x.y`. Before pinning, check that each has an arm64 build and that the chosen Nextcloud release supports PostgreSQL 17 and the PHP version in the image.

## Risks / Trade-offs

- **[Nextcloud major upgrades must go one major at a time, and a failed upgrade can leave the instance in maintenance mode]** → Pin exact tags. The README requires a backup before each upgrade and documents the step-by-step major upgrade path. A restore returns to the previous state.
- **[Backup HDD sits next to the Pi, the same risk as Synapse]** → Documented. Rotating an offsite disk is recommended.
- **[Userspace Tailscale networking limits throughput (roughly tens to a few hundred Mbit/s on the Pi 5)]** → Fine for documents. If large uploads feel slow, kernel-mode Tailscale (`TS_USERSPACE=false` with `/dev/net/tun`) is a later option that changes no data.
- **[Files copied directly into `DOCS_ROOT/data` are invisible to Nextcloud]** → The README documents `occ files:scan`. Normal use goes through the clients.
- **[`config/` lost or out of sync with the database dump makes the restore fail]** → Both are always captured in the same snapshot while maintenance mode is on, and restored together.
- **[Clock or permission problems on the host folders (uid 33)]** → The setup creates `DOCS_ROOT/*` with `chown 33:33`, and `configure.sh` checks write access before it changes anything.
- **[RAM pressure once the media server's face detection runs alongside]** → Per-container limits stop Nextcloud from growing without bound. The media change budgets its own memory.
- **[The Nextcloud phone app's auto-upload could be switched on by mistake, duplicating photos]** → The README's phone setup says to leave it off. The `photos` app is disabled on the server.

## Migration Plan

This is a greenfield deployment with no existing data:
1. **Tailscale admin console:** create `tag:docs`, a grant allowing the owner to reach it on 443, and an auth key with that tag.
2. **On the Pi:** create `DOCS_ROOT` on the SSD with `data/ config/ custom_apps/` owned by 33:33, copy `.env.example` to `.env`, and fill it in.
3. Run `docker compose up -d` in the repo folder, wait until everything is healthy, then run `scripts/configure.sh`.
4. Log in from a tailnet device, then connect the phone app and the desktop client.
5. Run the first `scripts/backup.sh`.

Rollback: `docker compose down` in the repo folder stops the stack, and Synapse is not affected. Deleting `DOCS_ROOT` and the volumes removes everything.

## Open Questions

- How many snapshots to keep. Pruning stays manual, like Synapse's dumps, and the README shows a one-line command for it. Automatic retention can be added later without changing the specs.
