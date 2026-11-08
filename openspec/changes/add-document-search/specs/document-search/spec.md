# Spec Delta

## Purpose

Lets the owner find documents in the document store by the words inside them, from Nextcloud's normal search bar. The index stays up to date as files are added, changed, moved, or deleted.

## ADDED Requirements

### Requirement: Searchable file types
The text content of these files SHALL be searchable:
- PDF
- plain text (`.txt`), Markdown (`.md`), CSV, HTML, RTF
- Word, Excel, PowerPoint (`.docx`, `.xlsx`, `.pptx`)
- OpenDocument text, spreadsheet, and presentation (`.odt`, `.ods`, `.odp`)
- JPEG, PNG, and TIFF images (through OCR)

Every other file SHALL still be findable by its file name.

#### Scenario: Word document
- **GIVEN** `Contracts/rent.docx` contains the sentence "Die Kündigungsfrist beträgt drei Monate"
- **WHEN** the owner searches for "Kündigungsfrist"
- **THEN** `rent.docx` is in the results

#### Scenario: Unsupported type found by name
- **GIVEN** a file `Backup/router-config.bin`
- **WHEN** the owner searches for "router-config"
- **THEN** the file is in the results

### Requirement: Only the owner's document files
The index SHALL contain only files from the users' Nextcloud file trees. Files in the Nextcloud trash, old file versions, and internal app data SHALL NOT appear in results. A user SHALL only get results from their own files.

#### Scenario: Deleted file disappears
- **GIVEN** `Taxes/2024/notice.pdf` is in the index
- **WHEN** the owner deletes it in Nextcloud, so it goes to the Nextcloud trash
- **THEN** within a few minutes it no longer appears in full-text results

### Requirement: Index follows changes
New and changed files SHALL be searchable within 5 minutes of upload when no OCR is needed. Files that need OCR SHALL become searchable once OCR finishes. A moved or renamed file SHALL keep its search content and show its new location within 5 minutes, without its text being extracted again. Changes made while the search service was stopped SHALL be picked up after it starts.

#### Scenario: Upload becomes searchable
- **WHEN** the owner uploads a text PDF containing "Kundennummer 4711"
- **THEN** a search for "4711" finds it within 5 minutes

#### Scenario: Moved file
- **GIVEN** an indexed scan `Inbox/scan.pdf`
- **WHEN** the owner moves it to `Insurance/scan.pdf`
- **THEN** within 5 minutes the result shows the folder `Insurance`
- **AND** OCR does not run again for that file

#### Scenario: Changes while stopped
- **GIVEN** the search service is stopped
- **WHEN** the owner uploads three PDFs and the service is started again
- **THEN** all three become searchable without manual action

### Requirement: Query matching
A search SHALL ignore case and match text anywhere inside words. A query of several words SHALL return only files that contain all of them, in any order. A phrase in double quotes SHALL match only that exact sequence. Queries shorter than 3 characters SHALL return no full-text results.

#### Scenario: Part of a compound word
- **GIVEN** a document containing "Einkommensteuerbescheid"
- **WHEN** the owner searches for "steuerbescheid"
- **THEN** that document is found

#### Scenario: Several words
- **WHEN** the owner searches for "Allianz 2025"
- **THEN** only files containing both "Allianz" and "2025" are returned

#### Scenario: Exact phrase
- **WHEN** the owner searches for `"drei Monate"`
- **THEN** files with "drei Monate" are found
- **AND** files with "drei" and "Monate" in different places are not

### Requirement: Results in Nextcloud search
Full-text results SHALL appear in Nextcloud's search bar as their own section. They SHALL be sorted by relevance and loaded in pages of 20. Each result SHALL show:
- the file name
- the folder path
- the modification date
- a short text snippet around a matching word

Selecting a result SHALL open the file in Nextcloud.

#### Scenario: Result content
- **WHEN** the owner searches for "Kündigungsfrist"
- **THEN** a "Full-text" section lists `rent.docx` with its folder `Contracts`, its modification date, and a snippet that contains "Kündigungsfrist"

#### Scenario: Open result
- **WHEN** the owner selects a full-text result
- **THEN** Nextcloud opens or previews that file

#### Scenario: More results
- **GIVEN** 45 documents contain "Rechnung"
- **WHEN** the owner searches for "Rechnung" and asks for more results twice
- **THEN** all 45 documents are listed

### Requirement: Search fast enough on the Pi
A full-text search SHALL return its first page of results within 2 seconds for an index of up to 50,000 documents.

#### Scenario: Large index
- **GIVEN** 50,000 indexed documents
- **WHEN** the owner searches for a word that occurs in 500 of them
- **THEN** the first 20 results appear within 2 seconds

### Requirement: Search service not exposed
The search service SHALL be reachable only by Nextcloud over the stack's internal network, and only with a shared secret. It SHALL NOT be reachable from the tailnet, the LAN, or the internet. Search results SHALL only be available through Nextcloud's login.

#### Scenario: Direct access refused
- **WHEN** a device in the tailnet tries to reach the search service directly
- **THEN** there is no route to it

#### Scenario: Missing secret
- **WHEN** a request inside the stack reaches the search service without the correct secret
- **THEN** it is rejected and returns no content

### Requirement: Index status and rebuild
The Nextcloud admin settings SHALL show:
- the number of indexed files
- the number of files waiting, with the count waiting for OCR shown separately
- the files that failed, each with its reason

A rebuild command SHALL clear the index and index every file again, reusing cached OCR text for unchanged files.

#### Scenario: Status after upload
- **WHEN** the owner uploads 30 scans and opens the status panel
- **THEN** it shows them as waiting for OCR, and the count drops as OCR progresses

#### Scenario: Failed file listed
- **WHEN** a password-protected PDF is uploaded
- **THEN** the status panel lists it as failed with the reason "encrypted PDF"
- **AND** it remains findable by its file name

#### Scenario: Rebuild
- **WHEN** the owner runs the rebuild command
- **THEN** all files become searchable again without new OCR for files that did not change

### Requirement: Search data survives restore
The document store backup SHALL include the search index and the cached OCR text. After a restore, search SHALL work for the restored files without OCR having to run again for them.

#### Scenario: Restore keeps OCR
- **GIVEN** a snapshot taken after 500 scans were OCR'd
- **WHEN** the owner restores that snapshot
- **THEN** those scans are searchable again without OCR running for them
