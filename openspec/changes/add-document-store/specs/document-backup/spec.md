# Spec Delta

## Purpose

Lets the owner copy all documents and the server state to the external HDD by hand, and restore the store completely from such a copy.

## ADDED Requirements

### Requirement: Manual backup to the external HDD
A backup command SHALL write a consistent copy of the database and the data folder to the external HDD as one dated snapshot. While it runs, the store SHALL be in maintenance mode so no files change. Afterwards the store SHALL be in normal mode again, even when the backup failed.

#### Scenario: Successful backup
- **GIVEN** the HDD is mounted
- **WHEN** the owner runs the backup command
- **THEN** a new snapshot folder named with date and time exists in the HDD's document backup folder
- **AND** it contains a database dump and a copy of the data folder
- **AND** the command prints the snapshot path and size

#### Scenario: Store usable again after backup
- **WHEN** the backup finishes, successfully or not
- **THEN** maintenance mode is off and the owner can use the store again

### Requirement: Backup refuses a missing drive
The backup command SHALL check that the backup HDD is mounted. If it is not mounted, the command SHALL stop with an error that names the expected mount point and write nothing.

#### Scenario: HDD not mounted
- **GIVEN** the HDD is not mounted
- **WHEN** the owner runs the backup command
- **THEN** it exits with an error that names the mount point
- **AND** nothing is written to the SSD or the mount point folder

### Requirement: Incomplete snapshots are recognizable
A snapshot SHALL only get its final name after it is complete. A snapshot interrupted mid-run SHALL NOT look like a complete one.

#### Scenario: Interrupted backup
- **WHEN** the backup is aborted while copying files
- **THEN** no snapshot folder with a final date-time name exists for that run

### Requirement: Space-efficient snapshots
Each snapshot SHALL contain the complete data folder. Files unchanged since the previous snapshot SHALL NOT take up additional space on the HDD.

#### Scenario: Second backup without changes
- **GIVEN** a snapshot exists and no file changed since
- **WHEN** the owner runs the backup again
- **THEN** the new snapshot shows all files
- **AND** it uses only a little extra space on the HDD, mainly for the database dump

### Requirement: Full restore
A restore command SHALL replace the current database and data folder with the contents of a chosen snapshot. Afterwards the store SHALL show exactly the files and folders of that snapshot. The command SHALL ask for confirmation before it deletes current data.

#### Scenario: Restore a snapshot
- **GIVEN** a snapshot taken when `Contracts/rent.pdf` existed
- **AND** the file was deleted later
- **WHEN** the owner restores that snapshot and confirms
- **THEN** `Contracts/rent.pdf` is visible again in every client

#### Scenario: Restore cancelled
- **WHEN** the owner answers "no" at the confirmation prompt
- **THEN** no current data is changed
