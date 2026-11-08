# Proposal

## Why

Documents such as contracts, tax papers, and manuals are scattered across phones, laptops, and mail inboxes. A self-hosted document store on the existing Raspberry Pi 5 keeps them private and in one folder tree. You can reach that tree from any device in the tailnet, including a smartphone. It lives in its own repository (Documenta). It is independent of Synapse and of the planned media server, and it sets the pattern for the media stack: its own containers, its own Tailscale node, data on the SSD, and backups to the external HDD.

## What Changes

- A new, self-contained **document stack** with its own `docker-compose.yml` (at the root of the Documenta repository), separate from Synapse and from the later media stack:
  - **Nextcloud** (official ARM64 image) as the document server and web UI.
  - **PostgreSQL** as Nextcloud's database, only reachable by Nextcloud.
  - **Redis** for file locking and caching.
  - **A cron container** that runs Nextcloud background jobs.
  - **A Tailscale sidecar** that gives the stack its own tailnet node and HTTPS name.
- **A plain folder tree.** You create, rename, move, and delete folders and files yourself. There is no metadata, no inbox, and no automatic sorting. Files sit on the SSD as normal, readable files.
- **Uploads from any tailnet device** through the Nextcloud web UI, the Nextcloud Android/iOS apps, and the desktop sync client. Large files (videos, scans) upload in chunks.
- **Access only from the tailnet.** No container publishes a port on the Pi, and there is no public endpoint.
- **One owner account** created on the first start from environment variables.
- **Manual backup and restore scripts.** They put Nextcloud into maintenance mode, dump the database, and copy the data folder to the external HDD as a dated snapshot.

Out of scope:
- Photo and video handling. That belongs to the separate media server change, and Nextcloud's own phone auto-upload stays off so photos don't end up in two places.
- Public links and access from outside the tailnet, including sharing with people outside it.
- Office document editing (Collabora / OnlyOffice).
- Full-text search and OCR. These are planned in the follow-up change `add-document-search`.
- Server-side encryption.
- Multiple user accounts (Nextcloud allows them, but nothing here depends on them).
- Automatic or scheduled backups.

## Capabilities

### New Capabilities
- `document-storage`: The folder tree. Upload, download, organize, and preview files from web, mobile, and desktop clients. Files are kept as plain files on the SSD.
- `document-access`: How the store is reached and protected: tailnet-only HTTPS, the owner account, and login.
- `document-backup`: Manual backup to the external HDD and full restore of database and files.
- `document-deployment`: The container stack on the Pi, including its configuration through `.env`, health checks, start order, and resource limits that let it run next to Synapse and the media server.

### Modified Capabilities
- None. This is the first change in the repository.

## Impact

- **New code and config:** the Documenta repository (compose file, `.env.example`, Tailscale serve config, backup and restore scripts, README, tests).
- **Raspberry Pi 5 (8 GB RAM, SSD):**
  - Adds about 0.6–1 GB RAM use next to Synapse.
  - Needs a data folder on the SSD, for example `/srv/media-vault/documents`.
  - Reuses the external backup HDD mount, writing into its own subfolder.
- **Tailscale:**
  - Needs a new node (for example `docs`).
  - Needs an auth key with a tag such as `tag:docs`.
  - Needs an ACL grant that allows the owner to reach it on 443.
- **Phone and PC:** install the Nextcloud app or desktop client and add `https://docs.<tailnet>.ts.net` as the server.
- **No changes to Synapse.**
