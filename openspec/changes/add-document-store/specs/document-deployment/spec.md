# Spec Delta

## Purpose

Defines how the document stack runs on the Raspberry Pi 5 next to Synapse and the media server. It covers the containers, configuration, startup, health, and resource use.

## ADDED Requirements

### Requirement: Independent stack
The document store SHALL run as its own Docker Compose project with its own containers, networks, and volumes. Starting, stopping, or upgrading it SHALL NOT affect Synapse or the media server.

#### Scenario: Stop documents only
- **GIVEN** Synapse and the document stack are running
- **WHEN** the owner stops the document stack
- **THEN** Synapse keeps running and stays reachable

### Requirement: ARM64 images
Every container image in the stack SHALL be available for linux/arm64 and SHALL be pinned to a specific version tag, not `latest`.

#### Scenario: Build on the Pi
- **WHEN** the owner starts the stack on a Raspberry Pi 5 running 64-bit Raspberry Pi OS
- **THEN** all images pull or build for arm64 without emulation

### Requirement: Configuration from .env
All secrets and deployment-specific values SHALL come from an `.env` file. An `.env.example` with every variable SHALL be provided. The stack SHALL refuse to start if a required secret or the data folder path is missing.

#### Scenario: Missing secret
- **WHEN** the owner starts the stack without the database password set
- **THEN** startup fails with a message that names the missing variable

### Requirement: Data on the SSD
The document data folder SHALL be stored at a host path on the SSD that the `.env` file sets. The database SHALL use a persistent volume. Removing and recreating the containers SHALL NOT lose files or database content.

#### Scenario: Recreate containers
- **GIVEN** the owner has uploaded files
- **WHEN** the owner runs `docker compose down` and then `docker compose up -d`
- **THEN** all files and folders are still there

### Requirement: Health and automatic restart
Every long-running container SHALL have a health check and SHALL restart automatically after a crash or a reboot of the Pi. A container SHALL only start after the containers it depends on are healthy.

#### Scenario: Reboot
- **WHEN** the Pi reboots
- **THEN** the stack comes back up on its own and the store is reachable again within a few minutes

### Requirement: Background jobs
Nextcloud's background jobs (cleanup, preview generation, file scans) SHALL run on a schedule every 5 minutes, independent of web requests.

#### Scenario: Background job status
- **WHEN** the owner opens the admin overview after the stack has run for 15 minutes
- **THEN** it shows a successful background job run within the last 5 minutes

### Requirement: Bounded resource use
The stack SHALL stay within about 1 GB of RAM while idle, so it can share an 8 GB Pi with Synapse and the media server. Memory limits SHALL be set per container.

#### Scenario: Idle memory
- **WHEN** the stack has been idle for 10 minutes
- **THEN** the combined memory use of its containers is at or below about 1 GB

### Requirement: Upgrade with data kept
Upgrading to a newer pinned version SHALL keep all files and settings. The documentation SHALL require a backup first, and SHALL state that Nextcloud can only be upgraded one major version at a time.

#### Scenario: Minor upgrade
- **GIVEN** a backup was taken
- **WHEN** the owner raises the Nextcloud image tag by a minor version and restarts the stack
- **THEN** Nextcloud runs its upgrade steps on its own and all files remain available
