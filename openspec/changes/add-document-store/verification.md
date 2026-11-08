# Verification log: add-document-store

> **Note:** the repository was flattened after slice 8 (owner's decision). Paths written as `documents/X` below now live at `X` in the repo root.

Results of the manual and command-line checks from tasks.md. Automated config tests live in `documents/tests/` (`pytest`).

## Slice 2: Organize, upload, and preview documents (task 2.2)

Environment: dev stack (`docker-compose.yml` + `docker-compose.dev.yml`) on Windows 11 with Docker Desktop, Nextcloud 35.0.2, 2026-11-08. Requests via WebDAV (`curl`) as the owner.

- [x] **Create nested folders** (spec: Folder tree). `MKCOL Taxes`, `Taxes/2026`, `Contracts`: 201 each. `Taxes/2026` exists on disk.
- [x] **Move a file** (spec: Folder tree). `PUT Taxes/2026/rent.pdf` 201, then `MOVE` to `Contracts/rent.pdf` 201. The old path returns 404, and the moved file is byte-identical (SHA-256).
- [x] **Upload through WebDAV** (spec: Upload from the browser). Uploading a file into a folder stores it there. This uses the same WebDAV path that the web UI and the clients use.
- [x] **Preview a JPEG and a TXT** (spec: Download and preview). `/core/preview` returns `200 image/jpeg` for `receipt.jpg` and `200 image/png` for `note.txt`. The TXT preview image shows the note's text.
- [x] **Preview a PDF** (spec: Preview a PDF). `files_pdfviewer` is enabled, and its viewer page for `Contracts/rent.pdf` loads the pdf.js viewer. The PDF is served as `application/pdf`. A server-side PDF *thumbnail* is not generated, because the image ships without ImageMagick/Ghostscript. The spec doesn't require one.
  - Confirmed visually by the owner over the tailnet: `Contracts/rent.pdf` opens in the browser.
- [x] **Large upload succeeds** (spec: Large file uploads). A 4 GiB random file was uploaded with Nextcloud chunked upload v2 (41 × 100 MiB chunks, then `MOVE .file` 201). The file on disk is 4,294,967,296 bytes with a matching SHA-256. It took about 38 minutes over the Docker Desktop bind mount on Windows, which is much slower than a native Linux disk.
- [x] **Disk full** (spec: Large file uploads, scenario Disk full). A 50 MB tmpfs was mounted as folder `Full` through a temporary override (not committed). Results:
  - A simple PUT of 100 MB returns `507 Insufficient space in /Full/too-big.bin`.
  - A chunked upload is refused at each chunk with 507, and the final `MOVE` fails with 400.
  - The folder stays empty, with no partial file.
- [x] **Readable without the app** (spec: Plain files on disk). With the stack stopped, `Contracts/rent.pdf` is read from `DOCS_ROOT/data/owner/files/Contracts/` by `pdfinfo` and `pdftotext` in a separate container: 1 page, PDF 1.4, text "Mietvertrag Kuendigungsfrist".
- [x] **Effective PHP limits** (task 2.1). `upload_max_filesize` 16G, `post_max_size` 16G, `memory_limit` 512M. The `files`, `viewer`, `files_pdfviewer`, and `text` apps are enabled.

Cleanup: the 4 GiB file, the trash bin, and the `Full` mount point were removed afterwards.

## Slice 3: Background jobs and no public sharing (task 3.2)

Environment: same dev stack, with the `cron` service added, 2026-11-08.

- [x] **configure.sh is idempotent**. Automated in `documents/tests/test_configure.py` (`test_running_twice_succeeds_and_changes_nothing`): a second run exits 0 and leaves all observed settings unchanged. All 7 configure tests pass, and ShellCheck 0.10.0 reports no issues.
- [x] **No public link** (spec: No public sharing). Creating a link share (`shareType=3`) through the OCS sharing API is refused with `HTTP 403` ("Öffentliches Teilen via Link ist nicht erlaubt"). The server capabilities report `files_sharing.public.enabled = false`, so the clients hide the link option.
  - Confirmed visually by the owner: a file's sharing panel offers no share link.
- [x] **Background jobs** (spec: Background jobs). `backgroundjobs_mode = cron`. With the cron container up for 17 minutes, the last run was 208 s ago, and the cron log shows `cron.php` every 5 minutes.
- [x] **Brute-force protection** (spec: Brute-force protection, scenario updated by the owner's decision to match Nextcloud 35). Failed attempts are counted per address (`security:bruteforce:attempts`), but **Nextcloud 35 no longer delays** a request: the throttler computes the delay without sleeping. Measured: 6 wrong logins through the login form each took about 0.5 s while Nextcloud reported a 6.4 s delay. Instead, after more than 10 failed logins within 30 minutes, every login from that address is refused with `HTTP 429`, even with the correct password. Lifted with `occ security:bruteforce:reset <ip>`. The spec scenario said "delayed". It now describes the block: more than 10 failures within 30 minutes refuse further logins until the block expires or is reset. The requirement text ("slowed down or blocked") is unchanged.

## Slice 4: Reachable from the tailnet over HTTPS only (task 4.2)

Environment: the **production** compose file (no dev override, no published port) on the Windows PC, with a real auth key (`tag:docs`), tailnet `tail7b5326.ts.net`, 2026-11-08. The existing dev install got `docs.tail7b5326.ts.net` added to `trusted_domains` by hand, because it was installed with the dev override. A fresh install on the Pi gets it from `DOCS_HOST`.

- [x] **Tagged node**. `docs` (100.83.153.57) appears in `tailscale status` as `tagged-devices`. The sidecar log shows `cert("docs.tail7b5326.ts.net"): got cert`.
- [x] **Reachable from the tailnet** (spec: Reachable from the tailnet). From the PC (`domiscitslenovo`, in the tailnet), `https://docs.tail7b5326.ts.net/status.php` returns 200, with certificate verification passing (`ssl_verify_result=0`).
- [x] **Generated links use the tailnet URL** (spec: Generated links use the tailnet URL). `/` redirects to `https://docs.tail7b5326.ts.net/login`, the internal link `/f/82` redirects to `https://docs.tail7b5326.ts.net/apps/files/files/82?dir=/Contracts…`, and `overwrite.cli.url` is the same URL.
- [x] **Unknown host name rejected** (spec: Unknown host name rejected). This was rejected on two layers once `OVERWRITEHOST` was removed (owner's decision, design D4 updated):
  - Tailscale: TLS for `evil.example` (SNI), for the bare IP, or plain HTTP on port 80 gets no connection.
  - Nextcloud: `Host: evil.example` sent directly from the container network gets `400 Bad Request` (untrusted domain); the real host gets 200.
  - With `OVERWRITEHOST` set (as originally designed), Nextcloud answered 200 for any host name.
- [x] **Not on the LAN** (spec: Not reachable from the LAN). No container publishes a port. The PC's LAN address `192.168.1.100` answers on none of 80, 443, and 8081.
- [x] **Not reachable from a non-tailnet device** (spec: Not reachable from the internet). The public DNS (1.1.1.1) resolves the name to `100.83.153.57`, a Tailscale CGNAT address (`100.64.0.0/10`) that isn't routed on the internet. Confirmed by the owner: a phone with the Tailscale VPN off, on mobile data, cannot reach `https://docs.tail7b5326.ts.net`.

## Slice 5: Phone and PC clients (tasks 5.1, 5.2)

Environment: the same production setup on the PC (`https://docs.tail7b5326.ts.net`). The owner followed the README section "Phone and PC", 2026-11-08. Confirmed by the owner:

- [x] **Upload from a phone** (spec: Upload from a phone). The Nextcloud Android app, connected through the tailnet, uploaded a PDF into `Contracts/`, and it appears in the web UI.
- [x] **Desktop sync client** (spec: Upload from any client). It syncs both ways: a file put into the local folder appears in the web UI, and a file created in the web UI appears locally.
- [x] **No photo auto-upload** (spec: Setup guide leaves auto-upload off). After following the README on the phone, **Settings → Auto upload** has no folder switched on.

## Slice 6: Backup snapshot (task 6.2)

Environment: `backup.sh` run in the Linux test runner (`documents/tests/runner/`: bash, rsync, util-linux `mountpoint`, docker compose) against the running stack. The backup drive is a tmpfs mounted in the runner, 2026-11-08. The automated tests are in `documents/tests/test_backup.py` (5 tests, all passing).

- [x] **ShellCheck** 0.10.0 reports no issues for `backup.sh` (and `configure.sh`).
- [x] **Successful backup** (spec: Successful backup). The snapshot `YYYY-MM-DDTHHMMSS/` contains `db.dump` (starting with `PGDMP`), `data/` (with `rent.pdf` identical to the source), `config/config.php`, and `custom_apps/`. The script prints the path and size, e.g. `Backup written: …/2026-11-08T170000 (87M)`.
- [x] **Store usable again after backup** (spec: Store usable again after backup). A stub `rsync` recorded `maintenance = true` at copy time. Afterwards maintenance is `false`, after success and after an interrupted run.
- [x] **Space-efficient snapshots** (spec: Second backup without changes). Two runs back to back: each snapshot is 87M alone, and both together are **87M**. The second run adds only its 656K dump. Unchanged files share inodes (hard links).
- [x] **HDD not mounted** (spec: HDD not mounted). With `BACKUP_MOUNT` pointing at a plain folder, the script exits non-zero with `ERROR: backup drive not mounted at /mnt/not-mounted`. The folder stays empty, and maintenance mode is never switched on.
- [x] **Interrupted backup** (spec: Interrupted backup). With a hanging stub `rsync`, an interrupt (SIGINT to the script and the copy process, like Ctrl-C) leaves only `<ts>.partial`, never a final-named folder, and maintenance is off.
- [x] **Pruning command from the README** keeps the newest 10 of 12 test snapshots and removes `.partial` folders.

## Slice 7: Restore (task 7.2)

Environment: `restore.sh` run in the Linux test runner against the running stack (production config on the PC), with snapshots from `backup.sh` on the runner's tmpfs, 2026-11-08. The automated tests are in `documents/tests/test_restore.py` (8 tests, all passing; the whole suite has 43). ShellCheck reports no issues for all three scripts.

- [x] **Restore cancelled** (spec: Restore cancelled). Answering `no` exits non-zero with "Restore cancelled". A file and a database value created after the snapshot are unchanged, and maintenance stays off.
- [x] **Only complete snapshots** (refinement of Full restore). A missing path and a `….partial` copy are refused with an error naming the path, before the `yes` prompt and without changing anything.
- [x] **Restore a snapshot** (spec: Restore a snapshot). `keep.txt`, deleted after the snapshot, is back with its content. A database value (`restoretest/marker`) is back at the snapshot state. A file created after the snapshot is gone. Maintenance is off, `nextcloud` is healthy, `cron` is running, and new uploads work. The data fingerprint changed. A restore takes about 40 s on the dev data.
- [x] **Sync client after restore** (task 7.2). Confirmed by the owner: the connected desktop client and the phone show `keep.txt` again, `after-snapshot.txt` is gone, there are no conflict copies, and there are no client errors.

Bugs found and fixed while making the tests pass:
- `pg_restore --no-owner` gave all tables to the `nextcloud` superuser, but Nextcloud connects as its own user `oc_admin`. The result was `permission denied for table oc_appconfig` and HTTP 500. The restore now recreates the database with owner `oc_admin` (read from the snapshot's `config.php`) and keeps the original owners. It creates that user if it doesn't exist, for a restore onto a fresh database server.
- `docker compose start nextcloud cron` waited forever, because `cron` depends on a healthy `nextcloud`. The script now starts `nextcloud`, waits for health, then starts `cron`.
- `occ maintenance:mode --on` fails while the database is broken, which aborted the restore. That step is now best effort, since Nextcloud is stopped right after it anyway.

## Slice 8: Limits and restart (task 8.1)

Environment: the production config on the PC, 2026-11-08. Automated in `test_compose.py`; the whole suite has 46 tests passing.

- [x] **Memory limits** per design D9: nextcloud 768m, **cron 640m** (D9 said 256m; raised above cron's 512 MB PHP limit, design updated), db 256m, redis 96m, tailscale 128m. `docker stats` shows the limits in effect. Idle use is about 0.23 GB in total (nextcloud 87–147 MB, tailscale 21–30 MB, db 23–43 MB, redis 4–5 MB, cron about 1 MB).
- [x] **`restart: unless-stopped`** on all 5 containers (`docker inspect` shows RestartPolicy).
- [x] **Redis** runs as a bounded cache: `maxmemory 64mb`, `allkeys-lru`, no RDB/AOF persistence.
- [x] **Upgrade procedure** documented in the README: backup first, one Nextcloud major version at a time, the PostgreSQL major-version path, and what to do if an upgrade fails.

## Slice 8: On the Raspberry Pi (task 8.2)

Environment: Raspberry Pi 5 (`KMSPi`, 8 GB, Debian 13 trixie, aarch64, NVMe), Docker 29.9.2, Compose v5.7.0, next to the running Synapse stack. Stack files copied to `~/media-vault/documents`, `DOCS_ROOT=/srv/media-vault/documents` (owner 33:33), `.env` with secrets generated on the Pi (mode 600), a new auth key with `tag:docs`, 2026-11-08.

- [x] **arm64 without emulation** (spec: Build on the Pi). All images run as `linux/arm64` (`nextcloud`, `postgres`, `redis`: `arm64/v8`; `tailscale`: `arm64`).
- [x] **First start**. All five containers were healthy after 68 s (including the Nextcloud install). `configure.sh` ran before the first login. The node `docs` (100.93.99.9) serves `https://docs.tail7b5326.ts.net` with a valid certificate and redirects to `/login`. `trusted_domains` contains the tailnet name from `DOCS_HOST`.
- [x] **Independent stack** (spec: Stop documents only). During `docker compose stop` of the document stack, Synapse kept answering 200 over the tailnet and its four containers stayed up. After `start`, both answer 200.
- [x] **Reboot** (spec: Reboot). After `sudo reboot` (run by the owner), all nine containers (document store and Synapse) were up and healthy within about 30 s of boot without any action, and both URLs answered 200 from the PC.
- [x] **Upgrade with data kept** (spec: Minor upgrade). Installed 35.0.1 through a temporary override, uploaded `note.txt` and a 5 MiB random file, then upgraded the normal way to the pinned 35.0.2 (`up -d --wait`, healthy after 64 s). Result: `versionstring 35.0.2`, maintenance off, `needsDbUpgrade false`, and both files byte-identical (SHA-256). Test data and the 35.0.1 image were removed, so the Pi runs a fresh 35.0.2 install configured before the first login. No backup was taken first, because there is no HDD yet and the store held no real data.
- [x] **Bounded resource use** (spec: Idle memory). After 10 idle minutes, `docker stats` showed nextcloud 219 MiB, db 51, cron 23, tailscale 19, redis 7: **about 319 MiB in total** (≤ 1 GB). cgroup `memory.current` (1410 MiB) also counts reclaimable page cache.
- [ ] **Backup to the real HDD**. Open: the Pi has no backup HDD attached (only NVMe; `/mnt/synapse-backup` doesn't exist). Deferred by the owner until the HDD is set up.

**Finding on the Pi (fixed): memory limits were not enforced.** The Raspberry Pi firmware boots the kernel with `cgroup_disable=memory`. `docker info` warned `No memory limit support`, `docker stats` showed `0B / 0B`, and Docker silently dropped every `mem_limit`. The fix, run by the owner, was `cgroup_enable=memory cgroup_memory=1` appended to `/boot/firmware/cmdline.txt` (backup `cmdline.txt.bak`) and a reboot. After that the `memory` controller is active, there is no Docker warning, and once the containers are recreated with `--force-recreate` the limits apply (768/640/256/96/128 MiB). Now documented in the README ("Pi prerequisite: memory accounting").

Test-environment note: a full test run hit `423 Locked` on `keep.txt`, because the file was open in the web Text editor (files_lock, owner "text"). It was lifted with `occ files:lock --unlock 182 owner`. The README's test section now mentions this.

Finding: Nextcloud persists values from environment-based config files into `config.php` whenever `occ config:system:set` runs. The dev install stored the dev override's `overwritehost`, `overwriteprotocol`, and `overwrite.cli.url` this way. Environment values still win while they are set. A value that is later *removed* from the environment stays active from `config.php` until deleted with `occ config:system:delete <key>`. This happened here with `overwritehost`.

Observation from slice 2, resolved in slice 3: on the first login, Nextcloud copied its sample "skeleton" files into the owner's account (including a `Photos/` folder with sample pictures and `Nextcloud intro.mp4`). `configure.sh` now sets an empty `skeletondirectory` (owner's decision), so new accounts start empty when the script runs before the first login.
