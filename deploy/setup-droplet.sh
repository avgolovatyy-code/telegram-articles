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

# A domain is optional: sslip.io resolves <dashed-ip>.sslip.io to that IP, which is
# enough for Let's Encrypt to issue a certificate. Set DEPLOY_DOMAIN yourself to use a
# real hostname instead.
PUBLIC_IP="$(curl -fsS --max-time 10 https://api.ipify.org || hostname -I | awk '{print $1}')"
DEFAULT_DOMAIN="${PUBLIC_IP//./-}.sslip.io"

if [[ ! -f "$APP_DIR/.env" ]]; then
	log "Creating .env from the example"
	cp "$APP_DIR/.env.example" "$APP_DIR/.env"
	ADMIN_PASSWORD="$(openssl rand -hex 16)"
	{
		echo ""
		echo "# --- added by setup-droplet.sh ---"
		echo "POSTGRES_USER=wegotrip"
		echo "POSTGRES_PASSWORD=$(openssl rand -hex 24)"
		echo "POSTGRES_DB=wegotrip_engine"
		echo "ADMIN_PASSWORD=${ADMIN_PASSWORD}"
		echo "DEPLOY_DOMAIN=${DEPLOY_DOMAIN:-$DEFAULT_DOMAIN}"
		echo "ACME_EMAIL=${ACME_EMAIL:-admin@${DEFAULT_DOMAIN}}"
		echo "LOG_FORMAT=json"
		echo "APP_ENV=production"
	} >>"$APP_DIR/.env"
	chown "$APP_USER:$APP_USER" "$APP_DIR/.env"
	chmod 600 "$APP_DIR/.env"
else
	ADMIN_PASSWORD="$(grep -E '^ADMIN_PASSWORD=' "$APP_DIR/.env" | cut -d= -f2- || true)"
fi

DOMAIN="$(grep -E '^DEPLOY_DOMAIN=' "$APP_DIR/.env" | cut -d= -f2-)"

cat <<EOF

Done.

  Server IP:  ${PUBLIC_IP}
  Address:    https://${DOMAIN}
  Admin user: admin
  Admin pass: ${ADMIN_PASSWORD}

No domain was required: ${DEFAULT_DOMAIN} resolves to this droplet automatically.
To use your own hostname, point an A record at ${PUBLIC_IP} and change DEPLOY_DOMAIN.

Next steps:

  1. Edit ${APP_DIR}/.env and fill in:
       OPENAI_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_TEST_CHANNEL
     Passwords for Postgres and the admin UI were generated for you.
  2. Start the stack:
       cd ${APP_DIR}
       docker compose -f deploy/docker-compose.prod.yml --env-file .env up -d --build
  3. Seed and check:
       docker compose -f deploy/docker-compose.prod.yml exec api wgt seed
       docker compose -f deploy/docker-compose.prod.yml exec api wgt doctor
       docker compose -f deploy/docker-compose.prod.yml exec api wgt check-telegram
EOF
