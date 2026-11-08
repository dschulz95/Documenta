# Proposal

## Why

The document store from `add-document-store` finds files only by name. A folder of contracts, tax letters, and invoices is only useful if you can search for what is written inside them, such as "Kündigungsfrist", an IBAN, or a customer number. Many of these documents are scans or phone photos of paper with no text layer. To make them searchable, the Pi has to OCR them first.

## What Changes

- **A new `docsearch` service** in the document stack (the Documenta repository). It is a container on the internal network that the tailnet cannot reach. It:
  - watches the Nextcloud data folder (read-only) for new, changed, moved, and deleted files
  - extracts the text from each file and builds a full-text index
- **Text extraction for common document formats:**
  - PDF with a text layer
  - plain text, Markdown, CSV, HTML, and RTF
  - Word, Excel, and PowerPoint (`.docx`, `.xlsx`, `.pptx`)
  - OpenDocument (`.odt`, `.ods`, `.odp`)
- **OCR in German and English** for scanned PDFs (pages without a text layer) and for images of documents (JPEG, PNG, TIFF). OCR runs only on the Pi, in the background, at limited CPU. Its results are cached, so moving or renaming a file never triggers a new OCR run.
- **Search inside Nextcloud.** A small custom Nextcloud app adds a "Full-text" section to Nextcloud's search bar. Each result shows the file name, its folder, a snippet with the matched words highlighted, and the modification date, and opens the file. Search matches inside words ("steuer" finds "Einkommensteuerbescheid") and ignores case.
- **Index status for the owner.** A panel in Nextcloud's admin settings shows how many files are indexed, how many are waiting (including OCR), and which ones failed and why. A command can rebuild the whole index.
- **Backup includes the search data.** `add-document-store`'s backup copies the search index and OCR text, so restoring doesn't need hours of OCR again.
- **`add-document-store` proposal.** Its "Full-text search and OCR" out-of-scope item now points to this change. It has no other changes.

Out of scope:
- Writing OCR text back into the files (for example, making scanned PDFs searchable outside this system).
- Semantic or AI search.
- Search inside ZIP archives, emails (`.eml`/`.msg`), or encrypted PDFs.
- A dedicated search page with advanced filters (search uses Nextcloud's standard search bar).
- Languages other than German and English for OCR.
- Searching photos and videos from the media server.

## Capabilities

### New Capabilities
- `document-search`: Full-text search over the documents in the document store. It covers which files are searchable, how quickly changes appear, what queries match, how results look in Nextcloud, and how the owner sees the index status.
- `document-ocr`: Text recognition (German and English) for scanned PDFs and document images, including caching and limits on CPU and file size.

### Modified Capabilities
- None. The `document-*` capabilities from `add-document-store` are not archived yet, and their requirements still hold unchanged.

## Impact

- **Depends on `add-document-store`.** That change must be implemented first. This change adds to its stack in the same repository.
- **New code:**
  - `docsearch/`: a Python service with its Dockerfile and tests. The image includes Tesseract with German and English data, plus Poppler.
  - `nextcloud-app/docsearch/`: a small PHP Nextcloud app with the search provider and the admin status panel.
- **Changed files from `add-document-store`:**
  - `docker-compose.yml`: the new service, plus a read-only mount of the app into `custom_apps`.
  - `.env.example`: the search token and limits.
  - `scripts/backup.sh` and `restore.sh`: include `${DOCS_ROOT}/search/`.
  - `scripts/configure.sh`: enable the app.
  - `README.md`.
- **Raspberry Pi:** about 100 MB of extra RAM at idle, and up to about 0.75 GB with high CPU (capped) while OCR runs. Indexing a large existing archive of scans for the first time can take hours.
- **Nextcloud upgrades:** the custom app declares which Nextcloud major versions it supports, so it has to be updated and tested whenever Nextcloud moves to a new major version.
