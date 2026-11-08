#!/usr/bin/env bash
# Restores the document store from a snapshot written by backup.sh (design D8).
# REPLACES the current database and all files with the snapshot's.
#
#   sudo scripts/restore.sh /mnt/synapse-backup/media-vault/documents/<YYYY-MM-DDTHHMMSS>
set -euo pipefail

export MSYS_NO_PATHCONV=1
cd "$(dirname "$0")/.."

snapshot=${1:?usage: scripts/restore.sh <snapshot folder>}
snapshot=${snapshot%/}

fail() {
  echo "restore.sh: ERROR: $*" >&2
  exit 1
}

# Only complete snapshots: interrupted runs are named <ts>.partial.
[[ $(basename "$snapshot") =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{6}$ ]] \
  || fail "not a complete snapshot (expected a folder named YYYY-MM-DDTHHMMSS): $snapshot"
for part in db.dump data config custom_apps; do
  [[ -e $snapshot/$part ]] || fail "snapshot is missing $part: $snapshot"
done

echo "This REPLACES the current database and all files with the snapshot:"
echo "  $snapshot"
read -r -p "Type 'yes' to continue: " answer
answer=${answer%$'\r'}   # tolerate CRLF from Windows terminals
if [[ $answer != yes ]]; then
  echo "Restore cancelled. Nothing was changed."
  exit 1
fi

# Value from the environment, else from .env, else the given default.
env_value() {
  local name=$1 default=${2-} value
  value=${!name-}
  if [[ -z $value && -f .env ]]; then
    value=$(grep -E "^${name}=" .env | tail -n 1 | cut -d= -f2- | tr -d '\r')
  fi
  printf '%s' "${value:-$default}"
}

occ() {
  docker compose exec -T -u www-data nextcloud php occ "$@"
}

docs_root=$(env_value DOCS_ROOT)
[[ -n $docs_root && -d $docs_root ]] || fail "DOCS_ROOT folder not found: '$docs_root'"

trap 'echo "restore.sh: FAILED. The store may be incomplete and stays in maintenance mode; fix the cause and run the restore again." >&2' ERR

echo "Stopping Nextcloud ..."
# Best effort: with a broken database (the reason for many restores) occ itself fails.
occ maintenance:mode --on >/dev/null 2>&1 || echo "restore.sh: note: could not enable maintenance mode (continuing)" >&2
docker compose stop nextcloud cron >/dev/null

echo "Restoring the database ..."
# Nextcloud uses its own database user (e.g. oc_admin), created during its install and
# recorded in config.php. Its tables must belong to it, and it must own the database.
config_value() {
  sed -n "s/^[[:space:]]*'$1' => '\(.*\)',[[:space:]]*\$/\1/p" "$snapshot/config/config.php" | head -n 1
}
db_owner=$(config_value dbuser)
[[ -n $db_owner ]] || fail "no dbuser in $snapshot/config/config.php"
psql() {
  docker compose exec -T db psql -U nextcloud -d postgres -v ON_ERROR_STOP=1 -tA "$@"
}
if [[ -z $(psql -c "SELECT 1 FROM pg_roles WHERE rolname = '$db_owner'") ]]; then
  # Restoring onto a fresh database server: recreate Nextcloud's user with its password.
  db_password=$(config_value dbpassword)
  psql -c "CREATE ROLE \"$db_owner\" LOGIN CREATEDB PASSWORD '${db_password//\'/\'\'}'" >/dev/null
fi
docker compose exec -T db dropdb -U nextcloud --if-exists nextcloud
docker compose exec -T db createdb -U nextcloud -O "$db_owner" nextcloud
docker compose exec -T db pg_restore -U nextcloud -d nextcloud --exit-on-error < "$snapshot/db.dump"

echo "Restoring files ..."
for part in data config custom_apps; do
  rsync -aH --delete "$snapshot/$part/" "$docs_root/$part/"
done

echo "Starting Nextcloud ..."
# Start nextcloud alone: `start` would wait for cron's dependency (a healthy nextcloud) forever.
docker compose start nextcloud >/dev/null
container=$(docker compose ps -q nextcloud)
for _ in $(seq 120); do
  [[ $(docker inspect -f '{{.State.Health.Status}}' "$container") == healthy ]] && break
  sleep 5
done
[[ $(docker inspect -f '{{.State.Health.Status}}' "$container") == healthy ]] || fail "nextcloud did not become healthy"
docker compose start cron >/dev/null

# Tell sync clients the server went back in time, so they don't upload old copies as conflicts.
occ maintenance:data-fingerprint >/dev/null
occ maintenance:mode --off >/dev/null
occ files:scan --all >/dev/null

echo "Restore complete: $snapshot"
