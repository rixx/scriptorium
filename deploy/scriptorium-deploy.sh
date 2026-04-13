#!/usr/bin/env bash
# Deploy script for scriptorium — triggered by systemd path unit.
# Runs as root (needs to restart the service), drops to BOOKS_USER for app commands.
set -euo pipefail

SCRIPTORIUM_DIR="${SCRIPTORIUM_DIR:-/opt/scriptorium}"
BOOKS_USER="${BOOKS_USER:-books}"
FLAG_FILE="${SCRIPTORIUM_DEPLOY_FLAG_FILE:-/var/lib/scriptorium/deploy.flag}"
LOG_TAG="scriptorium-deploy"

log() { logger -t "$LOG_TAG" "$@"; echo "[$(date -Is)] $*"; }

# Remove flag immediately so we don't re-trigger
rm -f "$FLAG_FILE"

log "Deploy started"

cd "$SCRIPTORIUM_DIR"

log "Running git pull"
sudo -u "$BOOKS_USER" git pull --ff-only

log "Running uv sync"
sudo -u "$BOOKS_USER" uv sync

log "Running migrations"
sudo -u "$BOOKS_USER" uv run python src/manage.py migrate --noinput

log "Collecting static files"
sudo -u "$BOOKS_USER" uv run python src/manage.py collectstatic --noinput

log "Restarting books service"
systemctl restart books

log "Deploy completed"
