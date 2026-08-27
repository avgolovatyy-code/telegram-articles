#!/usr/bin/env bash
# Provision a fresh Ubuntu 24.04 droplet for the content engine.
#
# Run as root on the droplet:
#   curl -fsSL https://raw.githubusercontent.com/avgolovatyy-code/telegram-articles/main/deploy/setup-droplet.sh | bash
# or, after cloning:
#   sudo bash deploy/setup-droplet.sh
#
# Installs Docker, creates a deploy user, clones the repository and prepares .env.
# It never writes secrets: you fill in .env afterwards.

set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/avgolovatyy-code/telegram-articles.git}"
BRANCH="${BRANCH:-main}"
APP_USER="${APP_USER:-wegotrip}"
APP_DIR="/opt/wegotrip-content-engine"

log() { printf '\n\033[1;34m==> %s\033[0m\n' "$1"; }

if [[ $EUID -ne 0 ]]; then
	echo "Run this script as root." >&2
	exit 1
fi

log "Updating packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq ca-certificates curl git ufw fail2ban

log "Installing Docker"
if ! command -v docker >/dev/null 2>&1; then
	install -m 0755 -d /etc/apt/keyrings
	curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
	chmod a+r /etc/apt/keyrings/docker.asc
	echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
		>/etc/apt/sources.list.d/docker.list
	apt-get update -qq
	apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
systemctl enable --now docker

log "Configuring the firewall"
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

log "Creating the ${APP_USER} user"
if ! id -u "$APP_USER" >/dev/null 2>&1; then
	useradd --create-home --shell /bin/bash "$APP_USER"
fi
usermod -aG docker "$APP_USER"

log "Cloning the repository into ${APP_DIR}"
if [[ -d "$APP_DIR/.git" ]]; then
	git -C "$APP_DIR" fetch origin "$BRANCH"
	git -C "$APP_DIR" checkout "$BRANCH"
	git -C "$APP_DIR" pull origin "$BRANCH"
else
	git clone --branch "$BRANCH" "$REPO_URL" "$APP_DIR"
fi
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

if [[ ! -f "$APP_DIR/.env" ]]; then
	log "Creating .env from the example"
	cp "$APP_DIR/.env.example" "$APP_DIR/.env"
	{
		echo ""
		echo "# --- added by setup-droplet.sh ---"
		echo "POSTGRES_USER=wegotrip"
		echo "POSTGRES_PASSWORD=$(openssl rand -hex 24)"
		echo "POSTGRES_DB=wegotrip_engine"
		echo "ADMIN_PASSWORD=$(openssl rand -hex 16)"
		echo "DEPLOY_DOMAIN=CHANGE_ME.example.com"
		echo "ACME_EMAIL=CHANGE_ME@example.com"
		echo "LOG_FORMAT=json"
		echo "APP_ENV=production"
	} >>"$APP_DIR/.env"
	chown "$APP_USER:$APP_USER" "$APP_DIR/.env"
	chmod 600 "$APP_DIR/.env"
fi

cat <<EOF

Done. Next steps:

  1. Point an A record for your domain at this droplet.
  2. Edit ${APP_DIR}/.env and fill in:
       DEPLOY_DOMAIN, ACME_EMAIL,
       OPENAI_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_TEST_CHANNEL
     A random POSTGRES_PASSWORD and ADMIN_PASSWORD were generated for you.
  3. Start the stack:
       cd ${APP_DIR}
       docker compose -f deploy/docker-compose.prod.yml --env-file .env up -d --build
  4. Seed and check:
       docker compose -f deploy/docker-compose.prod.yml exec api wgt seed
       docker compose -f deploy/docker-compose.prod.yml exec api wgt doctor
       docker compose -f deploy/docker-compose.prod.yml exec api wgt check-telegram

Admin UI: https://\$DEPLOY_DOMAIN/admin  (user "admin", password from .env)
EOF
