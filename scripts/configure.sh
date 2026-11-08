#!/usr/bin/env bash
# Applies the document store's Nextcloud settings (design D6).
# Idempotent: safe to run again at any time. Run it after the first start,
# before the owner logs in for the first time.
#
#   scripts/configure.sh
set -euo pipefail

# Git Bash on Windows would rewrite container paths like /var/www/html into Windows paths.
export MSYS_NO_PATHCONV=1

cd "$(dirname "$0")/.."

occ() {
  docker compose exec -T -u www-data nextcloud php occ "$@"
}

# Value from the environment, else from .env, else the given default.
env_value() {
  local name=$1 default=${2-} value
  value=${!name-}
  if [[ -z $value && -f .env ]]; then
    value=$(grep -E "^${name}=" .env | tail -n 1 | cut -d= -f2- | tr -d '\r')
  fi
  printf '%s' "${value:-$default}"
}

is_enabled() {
  occ app:list --enabled | grep -q "^  - $1:"
}

fail() {
  echo "configure.sh: ERROR: $*" >&2
  exit 1
}

# Check the data folders before changing anything.
docs_root=$(env_value DOCS_ROOT)
[[ -n $docs_root ]] || fail "DOCS_ROOT is not set (in .env or the environment)"
for sub in data config custom_apps; do
  [[ -d $docs_root/$sub ]] || fail "DOCS_ROOT folder missing: $docs_root/$sub"
done
for dir in data config custom_apps; do
  docker compose exec -T -u www-data nextcloud test -w "/var/www/html/$dir" \
    || fail "DOCS_ROOT/$dir is not writable by uid 33 (www-data): run 'sudo chown -R 33:33 $docs_root'"
done

occ background:cron >/dev/null

# Apps that are unnecessary or confusing here; photos belong to the media server.
for app in federation photos firstrunwizard recommendations weather_status; do
  if is_enabled "$app"; then
    occ app:disable "$app" >/dev/null
  fi
done

if ! is_enabled bruteforcesettings; then
  occ app:enable bruteforcesettings >/dev/null
fi

# Phone numbers without a country code are read as this region; heavy jobs run from 01:00 UTC.
occ config:system:set default_phone_region --value="$(env_value DOCS_PHONE_REGION DE)" >/dev/null
occ config:system:set maintenance_window_start --type=integer --value=1 >/dev/null

# New accounts start empty instead of getting Nextcloud's sample files (copied on first login).
occ config:system:set skeletondirectory --value= >/dev/null

# No public links: files are only reachable for logged-in users (spec: No public sharing).
occ config:app:set core shareapi_allow_links --value=no >/dev/null

echo "configure.sh: done"
