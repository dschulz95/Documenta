# Tasks

Each section is a vertical slice: it delivers one behavior the owner can observe in Nextcloud and is tested end to end on its own. Each slice builds on the ones before it. Slice 1 needs `add-document-store` implemented.

## 1. Slice: A text file in Nextcloud is found from the Nextcloud search bar

- [ ] 1.1 Confirm that `add-document-store` is implemented: the compose file, `configure.sh`, `backup.sh`, and `restore.sh` exist, and the dev stack starts healthy. Record the pinned Nextcloud major version. Stop and report if it is missing.
- [ ] 1.2 Create `docsearch/`, the minimal service (design D2, D3):
  - a Dockerfile on `python:3.12-slim-bookworm`, uid 33
  - a SQLite schema in WAL mode with an FTS5 `trigram` table
  - a startup scan of `/data/<user>/files/**` that indexes `.txt` files and every file name
  - `GET /search` and `GET /health`, with the `X-Docsearch-Token` check
  - Add the service to `docker-compose.yml` (network `data` only, `${DOCS_ROOT}/data:ro`, `${DOCS_ROOT}/search`). Make `DOCSEARCH_TOKEN` required in `.env.example`.
- [ ] 1.3 Create `nextcloud-app/docsearch` (design D7): `info.xml` with the pinned major version, `Application`, `DocsearchClient` (`IClientService`, 3-second timeout, URL and token from `IConfig`), and a `FullTextProvider` that returns title, folder, date, and snippet with a `/index.php/f/<id>` link. Add the read-only app mount to `nextcloud` and `cron`. Extend `configure.sh` to create `search/` (owner 33:33), set `docsearch_url`, `docsearch_token`, and `allow_local_remote_servers`, and enable the app, keeping the script idempotent.
- [ ] 1.4 Verify:
  - With pytest: a `.txt` fixture is found by a word in it; a `.bin` file is found by its name; a wrong or missing token returns 401 with no data; `/search?user=a` never returns user `b`'s files.
  - With PHPUnit (mocked client): the entries and the link are correct.
  - On the dev stack: uploading `notes.txt` containing "Kündigungsfrist" and restarting `docsearch` makes it show up in a "Full-text" section of the search bar, and selecting it opens the file.
  - With `docsearch` stopped, the search bar still shows file name results, and `nextcloud` stays healthy.
  - `docker compose config` fails and names `DOCSEARCH_TOKEN` when it is unset.
  - (spec: Results in Nextcloud search, Search service not exposed)
  - Document the setup in `README.md`.

## 2. Slice: Searches match the way the owner expects

- [ ] 2.1 Implement query parsing and ranking (design D6): quoted phrases and bare terms, dropping terms shorter than 3 characters, FTS5 literal escaping, the AND join, `bm25(10,2,1)`, `snippet`, and paging with `next_offset`. Pass the provider's cursor through to the service.
- [ ] 2.2 Verify:
  - With pytest: "steuerbescheid" finds "Einkommensteuerbescheid"; matching ignores case; "Allianz 2025" requires both words; `"drei Monate"` matches only the exact sequence; "ab" returns nothing; a name match ranks above a body match; queries containing `"`, `*`, or `NEAR` neither fail nor inject syntax.
  - On the dev stack: 45 matching files are reachable through "load more" in pages of 20.
  - (spec: Query matching, More results)
  - Document the query rules (at least 3 characters, no accent folding) in the README.

## 3. Slice: New, changed, moved, and deleted files are reflected in search

- [ ] 3.1 Implement change detection (design D4): the scope filter (exclude `files_trashbin`, `files_versions`, `appdata_*`, `uploads`, `cache`, `.part`), a watchdog observer with a 10-second debounce, moves that update `relpath`, deletes, the content cache keyed by SHA-256 so that moves and copies reuse text, and the reconciler at startup and every `RECONCILE_MINUTES`.
- [ ] 3.2 Verify:
  - With pytest on a temporary Nextcloud-like tree: trash-bin and version files are never indexed; a move updates the folder without calling the extractor; a delete removes the entry; files added while the service is stopped are indexed after it starts; a missed delete is fixed by the next reconcile.
  - On the dev stack: an uploaded TXT file is searchable within 5 minutes; a moved file shows its new folder within 5 minutes; a file deleted in Nextcloud disappears from results.
  - (spec: Index follows changes, Only the owner's document files)
  - Document `fs.inotify.max_user_watches` in the README.

## 4. Slice: Office documents and text PDFs are searchable

- [ ] 4.1 Add the extractors (design D5): the PDF text layer through `pdftotext` per page, `pdfinfo` detection of encrypted PDFs, DOCX, XLSX, PPTX, ODT/ODS/ODP, RTF, HTML, and MD/CSV with the UTF-8 then CP1252 fallback, plus the 5 MB text cap. The `failed` status (with reason) and `name_only` status are stored per file. Add `poppler-utils` to the image.
- [ ] 4.2 Verify:
  - With pytest: one fixture per format, each with known German text and umlauts, yields that text; an encrypted PDF is `failed` with the reason "encrypted PDF" and is still found by name.
  - On the dev stack: a DOCX containing "Kündigungsfrist" is found from the search bar.
  - (spec: Searchable file types)
  - List the supported formats in the README.

## 5. Slice: Scans and photos of paper are searchable through OCR

- [ ] 5.1 Add OCR (design D5): `tesseract-ocr` with `-deu`, `-eng`, and `-osd` in the image; a separate OCR queue that processes one file at a time; `pdftoppm -r 300 -gray` for PDF pages under 20 characters; image pre-processing (orientation, grayscale, at most 4000 px); `tesseract -l ${OCR_LANGS} --psm 1` under `nice -n 15` with `OMP_THREAD_LIMIT=1`; the `pending_ocr` status; merging the page texts into the content cache; `cpus: 1.0` and `mem_limit: 768m`.
- [ ] 5.2 Verify:
  - With pytest fixtures: a scanned German letter is found by "Müller"; a phone photo of an English receipt is found by "Total"; a PDF with 2 text pages and 1 scanned page runs OCR only on page 3, and all 3 pages are searchable.
  - A copy of an OCR'd file is searchable without OCR running again (OCR call mocked and counted), and changed content is OCR'd again.
  - After OCR, the SHA-256 and mtime of every fixture are unchanged and no new files exist.
  - (spec: OCR for scans and document images, OCR runs once per content, Files are never changed)
  - Document the OCR languages in the README.

## 6. Slice: OCR stays within limits and never holds up other documents

- [ ] 6.1 Add `OCR_MAX_PAGES` (default 200) and `OCR_MAX_FILE_MB` (default 200), with the statuses `partial` ("page limit") and `name_only` ("file too large"). Make sure the text queue and the OCR queue run independently.
- [ ] 6.2 Verify:
  - With pytest and lowered limits: a PDF over the page limit has its first N pages searchable and is marked `partial`; an oversized file is `name_only` and found by name.
  - With 50 scans waiting for OCR, a DOCX added afterwards becomes searchable before the OCR queue is empty.
  - (spec: Limits per file, Text files not blocked)
  - Document the limits in the README.

## 7. Slice: The owner sees the index status and can rebuild the index

- [ ] 7.1 Add `GET /status` (counts for indexed, waiting, and waiting for OCR, plus the first 200 failed or partial files with reasons), the Nextcloud admin settings section "Full-text search", and the CLI command `docsearch rebuild`, which clears `files` and `fts`, keeps `content`, and reconciles.
- [ ] 7.2 Verify:
  - With pytest: after a rebuild, everything is searchable and OCR is never called for unchanged files.
  - On the dev stack, after uploading 30 scans and an encrypted PDF: the panel shows the scans as waiting for OCR with a count that goes down, and lists the PDF with its reason.
  - (spec: Index status and rebuild)
  - Document the panel and the rebuild command in the README.

## 8. Slice: Search data survives backup and restore

- [ ] 8.1 Extend `backup.sh` to stop `docsearch` in the same EXIT trap scope as maintenance mode and to add `search/` to the rsync. Extend `restore.sh` to stop the service, restore `search/`, and start it again (design D9).
- [ ] 8.2 Verify:
  - `shellcheck` passes.
  - `docsearch` is running again after both a successful and a failed backup.
  - After restoring a snapshot taken after OCR, the scans are searchable with no `tesseract` process running and an OCR queue of 0.
  - (spec: Search data survives restore)
  - Update the backup section of the README.

## 9. Slice: Search performs well on the Pi without disturbing other services

- [ ] 9.1 Write a benchmark script that fills an index with 50,000 synthetic documents (about 20 KB each) and times the first page for a word found in 500 of them. Verify that it takes under 2 seconds on the Pi 5, and record the time and the index size in the README (spec: Search fast enough on the Pi).
- [ ] 9.2 Deploy on the Pi. Verify:
  - A tailnet device has no route to docsearch.
  - While 100 real scans are OCR'd and Synapse and the media gallery are in use, Nextcloud and Synapse pages load within a few seconds.
  - `tcpdump` shows no outbound connections from `docsearch`.
  - The seconds per page and the peak memory are recorded in the README.
  - (spec: Direct access refused, Pi stays responsive, Local only)
- [ ] 9.3 Add the Nextcloud upgrade step (bump `max-version` in `info.xml`, then rerun the slice 1 smoke test) to the README's upgrade procedure, and verify that it runs as written.

## Workflow follow-up

- Archive after `add-document-store` has been archived, so that the `document-*` capabilities exist in the main specs first.
