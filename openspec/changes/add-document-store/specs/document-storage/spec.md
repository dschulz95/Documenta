# Spec Delta

## Purpose

Keeps the owner's documents in one folder tree on the Raspberry Pi. The owner can upload, organize, preview, and download files from a phone, a PC, or a browser.

## ADDED Requirements

### Requirement: Folder tree
The document store SHALL let the owner create, rename, move, and delete folders and files at any depth. The store SHALL NOT sort, rename, or move files on its own, and SHALL NOT require any metadata for a file.

#### Scenario: Create nested folders
- **WHEN** the owner creates the folder `Taxes` and inside it the folder `2026`
- **THEN** the folder `Taxes/2026` exists and is shown in every client

#### Scenario: Move a file
- **WHEN** the owner moves `Inbox/scan.pdf` to `Contracts/`
- **THEN** the file is at `Contracts/scan.pdf` with the same content
- **AND** it is no longer at `Inbox/scan.pdf`

### Requirement: Upload from any client
The document store SHALL accept uploads into any folder from the web UI in a desktop or mobile browser, from the official Nextcloud Android and iOS apps, and from the desktop sync client. A file of any type SHALL be accepted.

#### Scenario: Upload from a phone
- **GIVEN** a phone in the tailnet with the Nextcloud app connected to the store
- **WHEN** the owner uploads a PDF into `Contracts/` from the app
- **THEN** the PDF is in `Contracts/` and is visible from the web UI

#### Scenario: Upload from the browser
- **WHEN** the owner drags a file into a folder in the web UI
- **THEN** the file is stored in that folder

### Requirement: Large file uploads
The document store SHALL accept a single file of at least 10 GB, as long as the SSD has room for it. An interrupted upload from the apps or the sync client SHALL be able to resume without starting over.

#### Scenario: Large upload succeeds
- **WHEN** the owner uploads a 4 GB file from the web UI
- **THEN** the upload completes and the stored file has the same size and checksum as the original

#### Scenario: Disk full
- **WHEN** an upload needs more space than is free on the SSD
- **THEN** the upload fails with an error shown to the owner
- **AND** no partial file is left in the target folder

### Requirement: Download and preview
The document store SHALL let the owner download any file. It SHALL show an in-browser preview of PDFs, common image formats, and plain text files.

#### Scenario: Preview a PDF
- **WHEN** the owner opens a PDF in the web UI
- **THEN** the PDF is displayed in the browser without downloading it first

### Requirement: Plain files on disk
The document store SHALL keep each file as a normal file on the SSD, under a folder path that matches its path in the folder tree. A copy of the data folder SHALL be readable without the document server running.

#### Scenario: Readable without the app
- **GIVEN** the owner stored `Contracts/rent.pdf`
- **WHEN** the data folder on the SSD is opened with a normal file manager while the stack is stopped
- **THEN** `rent.pdf` is found under a `Contracts` folder and opens as a valid PDF

### Requirement: No photo auto-upload
The document store SHALL NOT be configured as the destination for automatic phone photo or video uploads. Photos and videos belong to the separate media server.

#### Scenario: Setup guide leaves auto-upload off
- **WHEN** the owner follows the phone setup steps in the documentation
- **THEN** the Nextcloud app's auto-upload stays disabled
