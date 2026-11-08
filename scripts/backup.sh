#!/usr/bin/env bash
# Writes a snapshot of the document store to the backup HDD (design D8):
#   ${BACKUP_MOUNT}/media-vault/documents/<YYYY-MM-DDTHHMMSS>/
#     db.dump      PostgreSQL custom-format dump
#     data/ config/ custom_apps/   copies of DOCS_ROOT
#
#   sudo scripts/backup.sh
set -euo pipefail

export MSYS_NO_PATHCONV=1
cd "$(dirname "$0")/.."

# Value from the environment, else from .env, else the given default.
env_value() {
  local name=$1 default=${2-} value
  value=${!name-}
  if [[ -z $value && -f .env ]]; then
    value=$(grep -E "^${name}=" .env | tail -n 1 | cut -d= -f2- | tr -d '\r')
  fi
  printf '%s' "${value:-$default}"
}

backup_mount=$(env_value BACKUP_MOUNT /mnt/synapse-backup)

# Without the HDD, the folder is just a directory on the SSD: write nothing there.
if ! mountpoint -q "$backup_mount"; then
  echo "ERROR: backup drive not mounted at $backup_mount" >&2
  exit 1
fi

docs_root=$(env_value DOCS_ROOT)
target_dir="$backup_mount/media-vault/documents"
snapshot="$target_dir/$(date +%Y-%m-%dT%H%M%S)"

occ() {
  docker compose exec -T -u www-data nextcloud php occ "$@"
}

# No file or database changes while copying; always leave maintenance mode again.
maintenance_off() {
  occ maintenance:mode --off >/dev/null || echo "backup.sh: WARNING: could not turn maintenance mode off" >&2
}
occ maintenance:mode --on >/dev/null
trap maintenance_off EXIT
trap 'exit 130' INT TERM HUP   # Ctrl-C or kill: still run the EXIT trap

# Work in <ts>.partial; only a complete snapshot gets its final name.
partial="$snapshot.partial"
mkdir -p "$partial"
docker compose exec -T db pg_dump -U nextcloud -Fc nextcloud > "$partial/db.dump"

# Unchanged files become hard links to the previous complete snapshot (no extra space).
link_dest=()
previous=$(find "$target_dir" -mindepth 1 -maxdepth 1 -type d -name '????-??-??T??????' ! -path "$snapshot" | sort | tail -n 1)
if [[ -n $previous ]]; then
  link_dest=(--link-dest="$previous")
fi
rsync -aH "${link_dest[@]}" "$docs_root/data" "$docs_root/config" "$docs_root/custom_apps" "$partial/"

mv "$partial" "$snapshot"

echo "Backup written: $snapshot ($(du -sh "$snapshot" | cut -f1))"
