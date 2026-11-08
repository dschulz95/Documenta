# Design

## Context

- **Depends on `add-document-store`** (see its design). Relevant pieces:
  - Nextcloud runs as `nextcloud:<x.y.z>-apache` with Postgres, Redis, a cron container, and a Tailscale sidecar.
  - Networks: `web` (with egress) and `data` (internal).
  - Files are plain on disk at `${DOCS_ROOT}/data/<user>/files/<tree>` (uid 33).
  - Config and apps are bind-mounted from `${DOCS_ROOT}/config` and `${DOCS_ROOT}/custom_apps`.
  - Backup is an rsync snapshot taken during maintenance mode.
- **The Pi** (8 GB) also runs Synapse and the media server. The media worker already uses up to 2 CPUs in the background.
- **Documents are mostly German.** German uses long compound words ("Einkommensteuerbescheid"), so plain word-based search often fails ("steuerbescheid" finds nothing).
- **Requirements** are in `specs/document-search` and `specs/document-ocr`, and the motivation is in proposal.md.

## Goals / Non-Goals

**Goals:**
- Search matches substrings inside words, for German compound words.
- No JVM and no extra search-engine container. The stack gains one small container.
- OCR runs once per file content. The index can be rebuilt from the files plus the OCR cache.
- Results show up inside Nextcloud and use its login. The search service itself is never exposed.

**Non-Goals:**
- Language-aware stemming or typo tolerance.
- Search across several users' files. There is one owner, but the index is scoped per user anyway.
- Searching Nextcloud external storages or group folders. None are configured.

## Decisions

### D1: Custom indexer + SQLite FTS5 (trigram) + a Nextcloud search provider app

```
 Nextcloud search bar --> [nextcloud] docsearch app (PHP, search provider)
                               | HTTP + token, network "data" (internal)
                               v
                         [docsearch] Python service
                          - watcher (inotify) + periodic reconcile
                          - text queue (fast)   OCR queue (1 file at a time, nice)
                          - SQLite: files, content cache (OCR text), FTS5 trigram index
                               |  read-only                  | read-write
                       ${DOCS_ROOT}/data            ${DOCS_ROOT}/search/index.sqlite
```

- **FTS5 with `tokenize='trigram'`** matches any substring of 3 or more characters, case-insensitively. It ranks with `bm25()` and builds snippets with `snippet()`. It runs inside the service process, so it adds no extra container and almost no RAM. A quoted phrase is a substring match that includes the spaces, which gives exact-sequence matching.
- *Alternative: the Nextcloud "Full text search" apps with Elasticsearch.* Rejected:
  - Elasticsearch needs 1 GB of RAM or more on the JVM.
  - Their Tesseract OCR plugin is no longer maintained. OCR would need the `workflow_ocr` app, whose OCR backend runs as an AppAPI ExApp that needs a Docker deploy daemon.
  - These apps have historically trailed new Nextcloud major versions.
- *Alternative: Meilisearch.* Rejected. It is light and typo-tolerant, but it has no matching inside words, which German compound words need, and it is one more container.
- *Alternative: Postgres full-text search in Nextcloud's database.* Rejected. It couples to Nextcloud's schema, needs a stemming configuration per language, and can't match inside words.
- *Alternative: Paperless-ngx.* Rejected. It is an entire second document system with its own import folder and storage, which conflicts with the plain folder tree.
- *Alternative: Apache Tika server for text extraction.* Rejected. It is another JVM using about 400 MB. Python libraries plus Poppler cover the required formats.

### D2: The docsearch service
- **Image.** `python:3.12-slim-bookworm` (SQLite 3.40, which has the trigram tokenizer) with the Debian packages `poppler-utils`, `tesseract-ocr`, `tesseract-ocr-deu`, `tesseract-ocr-eng`, and `tesseract-ocr-osd`. Python packages: `fastapi`, `uvicorn`, `watchdog`, `python-docx`, `openpyxl`, `python-pptx`, `odfpy`, `striprtf`, and `pillow`.
- **Process.** It runs as uid 33 (www-data), so it can read the data folder and own `${DOCS_ROOT}/search`.
  - One process runs uvicorn (the internal API) plus background threads: the watcher, the reconciler, a text worker, and an OCR worker.
  - OCR runs in `tesseract` subprocesses with `nice -n 15` and `OMP_THREAD_LIMIT=1`.
  - The container is capped with `cpus: 1.0` and `mem_limit: 768m` (spec: Background processing at limited CPU).
- **Networks.** Only `data` (internal), so there is no egress and no route from the tailnet or the LAN (spec: Local only, Search service not exposed). Nextcloud reaches it as `http://docsearch:8080`. Every request needs the header `X-Docsearch-Token`, which equals `DOCSEARCH_TOKEN` from `.env`.

### D3: Index schema

```
files    (id INTEGER PK, user, relpath UNIQUE(user,relpath), name, folder, size, mtime, sha256,
          status: indexed | pending | pending_ocr | partial | failed | name_only,
          reason, indexed_at)
content  (sha256 PK, text, pages, ocr_pages, partial_reason, extractor_version, ocr_version)
fts      VIRTUAL TABLE USING fts5(name, folder, body, tokenize='trigram')   -- rowid = files.id
```

- `content` is the OCR and extraction cache, keyed by content hash. Moving, renaming, copying, or rebuilding the index only needs to hash the file and look it up (spec: OCR runs once per content).
- `extractor_version` and `ocr_version` constants force re-extraction when the extraction code changes. Rebuilding never invalidates OCR text unless `ocr_version` changes.
- SQLite runs in WAL mode. The API reads on its own connection, so a search never waits for the indexer.

### D4: Change detection
- **Scope.** Only `/data/<user>/files/**`. The service ignores `files_trashbin`, `files_versions`, `appdata_*`, `uploads`, `cache`, `.part` files, and Nextcloud transfer temporaries (spec: Only the owner's document files). Nextcloud writes uploads into `uploads/` and moves the finished file into place, so watched files are complete when they appear.
- **Events.** A recursive `watchdog` inotify observer collects created, modified, moved, and deleted events. Each path waits 10 seconds after its last event (debounce). A move event updates `relpath` directly. A delete removes the row from `files` and its `fts` entry.
- **Reconcile.** The service walks the tree and compares `(size, mtime)`. It runs at startup and every 30 minutes, and it covers missed events, inotify overflow, and downtime (spec: Changes while stopped). A new or changed file is hashed. If `content[sha256]` exists, the file is indexed right away without extraction.
- **inotify limits.** The README documents raising `fs.inotify.max_user_watches` (for example to 524288) through `/etc/sysctl.d`. If watches run out, the reconciler still catches everything within 30 minutes.

### D5: Text extraction and OCR flow

```
new/changed file -> sha256 -> cached? --yes--> index (name, folder, body)
                                 | no
                     text extractor by type (text queue)
                       PDF: pdftotext per page; pages with < 20 non-space chars -> need OCR
                       office/odf/rtf/html/txt/csv/md: python libs, decode utf-8 -> cp1252 fallback
                       image: -> needs OCR
                       other: name_only
                     index now with what we have
                     if pages/image need OCR -> status pending_ocr -> OCR queue
OCR queue (1 file at a time): pdftoppm -r 300 -gray page -> tesseract -l deu+eng --psm 1 -> stdout
                     merge page texts -> content cache -> re-index -> status indexed/partial
```

- **Two queues.** Text extraction and OCR use separate queues, so a Word file never waits behind 300 scans (spec: Text files not blocked). The text layer of a mixed PDF is searchable right away, and the scanned pages follow once OCR finishes.
- **Images.** Pillow corrects the orientation, converts to grayscale, and limits the long side to 4000 px before Tesseract. `--psm 1` with OSD handles rotated scans.
- **Limits.** `OCR_MAX_PAGES` (default 200) and `OCR_MAX_FILE_MB` (default 200). Over a limit, the status becomes `partial` with the reason "page limit", or `name_only` with the reason "file too large" (spec: Limits per file). Extracted text is capped at 5 MB per file.
- **Failures.** Detected with `pdfinfo` and parser exceptions. Encrypted PDFs, corrupt files, and parser errors get `status=failed` with a readable reason, and the file stays findable by name.

### D6: Query handling
- **Parsing.** The query splits into quoted phrases and bare terms. Terms shorter than 3 characters are dropped, and if nothing remains, the result is empty (spec: Query matching). Each term or phrase becomes an FTS5 string literal (`"…"`, with inner quotes doubled), and they are joined with `AND`. With trigram tokenization, each literal matches as a case-insensitive substring.
- **Ranking.** `bm25(fts, 10.0, 2.0, 1.0)`, so name matches rank above folder matches, which rank above body matches. Paging uses `LIMIT 20 OFFSET n`.
- **Snippet.** `snippet(fts, 2, '', '', '…', 48)` gives plain text around the first match. If the match is only in the name or folder, the start of the body is used.
- **API.** `GET /search?user=&q=&offset=&limit=` returns `{entries:[{relpath,name,folder,mtime,snippet}], next_offset}`. `GET /status?user=` returns the counts and the failed and partial files (first 200). `GET /health` takes no token. Rebuilding is a CLI command, not an HTTP endpoint (D9).
- **Performance.** Trigram FTS on 50,000 documents of typical size (an index of a few GB) answers selective queries in tens of milliseconds on an SSD. Task 2.4 measures this on the Pi against the 2-second requirement.

### D7: The Nextcloud app (`nextcloud-app/docsearch`)
- **`appinfo/info.xml`.** It declares `<nextcloud min-version max-version>` equal to the pinned Nextcloud major version.
- **Registration.** `Application::register()` calls `registerSearchProvider(FullTextProvider::class)` and registers an admin settings section.
- **`FullTextProvider` (implements `OCP\Search\IProvider`).**
  - id `docsearch`, name "Full-text", order 15 (right after Files).
  - `search(IUser, ISearchQuery)` calls `/search` with the user's id, the term, the cursor as offset, and a limit of 20.
  - It resolves each `relpath` through `IRootFolder::getUserFolder($uid)->get($relpath)` to get the file id, and skips entries that no longer exist.
  - Each entry is a `SearchResultEntry` with:
    - title: the file name
    - subline: `folder · date · snippet`
    - resource URL: `/index.php/f/<fileId>`, which opens the file in Nextcloud
    - icon: the file's preview or mimetype icon
  - It returns `SearchResult::paginated(...)` (spec: Results in Nextcloud search).
  - If docsearch can't be reached, it logs a warning and returns an empty section. Nextcloud's own file name search keeps working.
- **Admin settings section "Full-text search".** A server-rendered template calls `/status` and shows the indexed, waiting, and waiting-for-OCR counts and the list of failed or partial files with their reasons (spec: Index status and rebuild).
- **Configuration.**
  - The token and URL go into Nextcloud's system config (`occ config:system:set docsearch_url|docsearch_token`), set by `configure.sh`. The app reads them through `IConfig`, which avoids Apache environment-variable passing.
  - HTTP calls go through `IClientService` with a 3-second timeout. `allow_local_remote_servers` is set to true, because the target is an internal Docker host name.
- **Deployment.** The repo folder is bind-mounted read-only at `/var/www/html/custom_apps/docsearch` (and into `cron`). `configure.sh` runs `occ app:enable docsearch`.
- *Alternative: a separate search web page behind the same Tailscale host.* Rejected. It would need its own login or a way to validate Nextcloud sessions. The provider app reuses Nextcloud's login and UI.

### D8: Compose and config changes to the stack

```yaml
docsearch:
  build: ./docsearch
  user: "33:33"
  restart: unless-stopped
  environment: [DOCSEARCH_TOKEN, OCR_MAX_PAGES, OCR_MAX_FILE_MB, OCR_LANGS=deu+eng]
  volumes: ["${DOCS_ROOT}/data:/data:ro", "${DOCS_ROOT}/search:/search"]
  networks: [data]
  cpus: 1.0
  mem_limit: 768m
  healthcheck: GET http://localhost:8080/health
nextcloud / cron:
  + volume ./nextcloud-app/docsearch:/var/www/html/custom_apps/docsearch:ro
```

- `DOCSEARCH_TOKEN` is required (`${VAR:?}`).
- `nextcloud` does **not** depend on `docsearch` being healthy. Search degrades on its own, and the document store must not fail because of search.

### D9: Backup, restore, and rebuild
- **`backup.sh`.** Additionally runs `docker compose stop docsearch` (restarted in the same EXIT trap that ends maintenance mode) and adds `search/` to the rsync list. Stopping the service guarantees a consistent SQLite file without needing the `sqlite3` tool in the backup path (spec: Search data survives restore).
- **`restore.sh`.** Stops `docsearch`, restores `search/` along with the rest, and starts it again. The startup reconcile fixes any drift between the restored index and the files.
- **Rebuild.** `docker compose exec docsearch docsearch rebuild` clears `files` and `fts` but keeps `content`, then reconciles. Unchanged files get their cached text back without OCR (spec: Rebuild).

### D10: Resource budget
- Idle: about 80–120 MB.
- OCR: one Tesseract process at 300 dpi needs about 150–300 MB, and the 768 MB limit leaves headroom. Expect about 5–15 seconds per page on one Pi 5 core.
- An initial archive of 1,000 scanned pages takes about 2–4 hours. Text documents index in seconds.

## Risks / Trade-offs

- **[The trigram index takes about 3× the space of the plain text]** → Even 50,000 documents with 20 KB of text each come to only a few GB on the SSD. The status panel could show the index size later if needed.
- **[No accent folding: "Muller" doesn't find "Müller"]** → Accepted. Owners type umlauts on German keyboards. A possible later improvement is an additional normalized column (with a newer SQLite and `remove_diacritics`).
- **[OCR quality on phone photos of paper (skew, shadows) is mediocre]** → OSD and grayscale help. The text stays as cached, unchanged OCR output, and better pre-processing can be added later by bumping `ocr_version`.
- **[The custom app breaks on a Nextcloud major upgrade (the `max-version` check)]** → The upgrade procedure in the README gets a step: bump `max-version`, run the app's smoke test, then upgrade. If the app is incompatible, Nextcloud disables it and keeps running without full-text search.
- **[Nextcloud's search UI may change how it shows sublines or pagination]** → The provider uses only the public `OCP\Search` API. The task list includes a manual check after each upgrade.
- **[inotify watches run out on large trees]** → The sysctl is documented, and the 30-minute reconcile is a safety net.
- **[CPU contention with the media worker, which uses up to 2 CPUs]** → docsearch is capped at 1 CPU and runs at nice 15. In the worst case, the Pi 5's 4 cores are shared 2 + 1 with one left for the web UIs.
- **[A stale index entry points to a deleted file before the debounce or reconcile catches it]** → The provider skips entries whose path no longer resolves.

## Migration Plan

1. Deploy `add-document-store` first, since this change requires it.
2. Pull this change, create `${DOCS_ROOT}/search` (owned by 33:33), and add `DOCSEARCH_TOKEN` to `.env`.
3. Run `docker compose up -d --build`, then `scripts/configure.sh` (enables the app and sets the URL and token).
4. The first reconcile indexes the existing files. Watch progress in Nextcloud → Administration → Full-text search.

Rollback: run `occ app:disable docsearch` and remove the service from the compose file. Nextcloud and the files are untouched, and `${DOCS_ROOT}/search` can be deleted.

## Open Questions

- The defaults for the OCR page and size limits (200 pages / 200 MB) and the reconcile interval (30 minutes) are environment variables. They can be tuned after the first real import without changing the specs.
