#!/usr/bin/env bash
# Pull the latest code and restart the stack on the droplet.
#
#   cd /opt/wegotrip-content-engine && bash deploy/update.sh

set -euo pipefail

APP_DIR="${APP_DIR:-/opt/wegotrip-content-engine}"
BRANCH="${BRANCH:-main}"
COMPOSE="docker compose -f deploy/docker-compose.prod.yml --env-file .env"

cd "$APP_DIR"

echo "==> Pulling ${BRANCH}"
git fetch origin "$BRANCH"
git checkout "$BRANCH"
git pull origin "$BRANCH"

echo "==> Rebuilding"
$COMPOSE build

echo "==> Applying migrations"
$COMPOSE run --rm migrate

echo "==> Restarting services"
$COMPOSE up -d api worker caddy

echo "==> Health"
sleep 5
$COMPOSE exec -T api wgt doctor || true
$COMPOSE ps
