# Spec Delta

## Purpose

Makes scanned documents and photos of paper searchable by recognising their text (German and English) on the Raspberry Pi. It does so without changing the files and without slowing down the rest of the Pi.

## ADDED Requirements

### Requirement: OCR for scans and document images
The system SHALL recognise text in two cases:
- each PDF page that has no usable text layer
- every JPEG, PNG, and TIFF image in the document store

It SHALL use German and English together, so documents with mixed languages work, including German umlauts and ß. PDF pages that already have a text layer SHALL use that text without OCR.

#### Scenario: Scanned letter
- **GIVEN** a scanned PDF of a German letter containing "Sehr geehrter Herr Müller"
- **WHEN** OCR has finished
- **THEN** a search for "Müller" finds the PDF

#### Scenario: Phone photo of a receipt
- **WHEN** the owner uploads a JPEG photo of a printed English receipt containing "Total"
- **THEN** after OCR, a search for "Total" finds the image

#### Scenario: Mixed PDF
- **GIVEN** a PDF with 2 text pages and 1 scanned page
- **WHEN** it is indexed
- **THEN** OCR runs only for the scanned page
- **AND** text from all 3 pages is searchable

### Requirement: Files are never changed
OCR SHALL NOT modify, replace, or add files in the document store. The recognised text SHALL be stored only in the search data.

#### Scenario: Original unchanged
- **WHEN** a scanned PDF has been OCR'd
- **THEN** its checksum and modification date in Nextcloud are unchanged
- **AND** no new file appears next to it

### Requirement: OCR runs once per content
Recognised text SHALL be cached by file content. A file whose content did not change SHALL NOT be OCR'd again, even after moving, renaming, copying, or rebuilding the index. A file whose content changed SHALL be OCR'd again.

#### Scenario: Copy of a scan
- **GIVEN** `scan.pdf` was OCR'd
- **WHEN** the owner copies it to another folder
- **THEN** the copy becomes searchable without a new OCR run

#### Scenario: Replaced content
- **WHEN** the owner uploads a new version of `scan.pdf` with different pages
- **THEN** the new content is OCR'd
- **AND** the search reflects the new text

### Requirement: Limits per file
OCR SHALL process at most a configurable number of pages per file (default 200) and only files up to a configurable size (default 200 MB). For a file over a limit, the system SHALL index the text it could get, mark the file in the index status as partially processed or skipped with the reason, and keep it findable by name.

#### Scenario: Very long scan
- **GIVEN** a scanned PDF with 350 pages and the default limit
- **WHEN** it is indexed
- **THEN** the first 200 pages are searchable
- **AND** the status panel lists the file as "partially OCR'd: page limit"

### Requirement: Background processing at limited CPU
OCR SHALL run in the background, one file at a time, at reduced priority and with a CPU cap. Files without OCR need SHALL NOT wait behind a long OCR queue. While OCR runs, Nextcloud, Synapse, and the media server SHALL stay responsive.

#### Scenario: Text files not blocked
- **GIVEN** 300 scans are waiting for OCR
- **WHEN** the owner uploads a Word document
- **THEN** the Word document becomes searchable within 5 minutes

#### Scenario: Pi stays responsive
- **WHEN** OCR processes a batch of 100 scans
- **THEN** the Nextcloud web UI and Synapse still load pages within a few seconds

### Requirement: Local only
OCR SHALL run entirely on the Raspberry Pi. No document content SHALL be sent to an external service.

#### Scenario: No outbound connections
- **WHEN** a batch of scans is OCR'd
- **THEN** the search service opens no network connections to hosts outside the stack
