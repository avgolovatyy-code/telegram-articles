#!/usr/bin/env bash
# Deploy this repo onto the existing droplet from a Cloud Agent.
#
# Required in the agent environment (Cursor Secrets):
#   DEPLOY_HOST, DEPLOY_USER, DEPLOY_SSH_KEY  (or DEPLOY_SSH_PRIVATE_KEY)
# Also used when present: OPENAI_API_KEY, TELEGRAM_BOT_TOKEN, Slack tokens, ACME_EMAIL
#
#   bash deploy/from-agent.sh

set -euo pipefail

HOST="${DEPLOY_HOST:-}"
USER="${DEPLOY_USER:-root}"
KEY_TEXT="${DEPLOY_SSH_PRIVATE_KEY:-${DEPLOY_SSH_KEY:-${DROPLET_SSH_PRIVATE_KEY:-}}}"
BRANCH="${DEPLOY_BRANCH:-cursor/wegotrip-telegram-content-engine-64e7}"
REPO_URL="${REPO_URL:-https://github.com/avgolovatyy-code/telegram-articles.git}"
APP_DIR="${APP_DIR:-/opt/wegotrip-content-engine}"
SLACK_CHANNEL_VALUE="${SLACK_CHANNEL:-#telegram-articles}"
DOMAIN_VALUE="${DEPLOY_DOMAIN:-}"
ACME_VALUE="${ACME_EMAIL:-}"

if [[ -z "$HOST" || -z "$KEY_TEXT" ]]; then
	cat <<EOF
This Cloud Agent cannot reach the droplet.

DEPLOY_HOST is $([ -n "$HOST" ] && echo set || echo MISSING)
SSH key is $([ -n "$KEY_TEXT" ] && echo set || echo MISSING)

Cursor injects Secrets only when the agent starts. Open a NEW Cloud Agent
on branch ${BRANCH} after the secrets exist in the dashboard, then run:

  bash deploy/from-agent.sh
EOF
	exit 2
fi

KEY_TEXT="${KEY_TEXT//$'\r'/}"
if [[ "$KEY_TEXT" == *'\\n'* ]]; then
	KEY_TEXT="${KEY_TEXT//\\n/$'\n'}"
fi
# Cursor Secrets often strip newlines. Rebuild OpenSSH PEM from a single line.
if [[ "$KEY_TEXT" == *"BEGIN OPENSSH PRIVATE KEY"* && "$KEY_TEXT" != *$'\n'* ]]; then
	KEY_TEXT="$(
		KEY_TEXT="$KEY_TEXT" python3 - <<'PY'
import os, re, textwrap
raw = os.environ["KEY_TEXT"].strip()
body = raw.replace("-----BEGIN OPENSSH PRIVATE KEY-----", "")
body = body.replace("-----END OPENSSH PRIVATE KEY-----", "")
body = re.sub(r"\s+", "", body)
wrapped = "\n".join(textwrap.wrap(body, 70))
print("-----BEGIN OPENSSH PRIVATE KEY-----")
print(wrapped)
print("-----END OPENSSH PRIVATE KEY-----")
PY
	)"
fi

KEYFILE="$(mktemp)"
cleanup() { rm -f "$KEYFILE"; }
trap cleanup EXIT
printf '%s\n' "$KEY_TEXT" >"$KEYFILE"
chmod 600 "$KEYFILE"
if ! ssh-keygen -y -f "$KEYFILE" >/dev/null 2>&1; then
	echo "DEPLOY_SSH_KEY is not a usable private key (ssh-keygen rejected it)."
	echo "Paste the full OpenSSH private key, including BEGIN/END lines."
	exit 2
fi

SSH=(ssh -i "$KEYFILE" -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new
	-o BatchMode=yes -o ConnectTimeout=20 "${USER}@${HOST}")

echo "==> ${USER}@${HOST}  branch=${BRANCH}"
"${SSH[@]}" "echo connected as \$(whoami) on \$(hostname)"

remote() { "${SSH[@]}" "$@"; }

if ! remote "command -v docker >/dev/null 2>&1"; then
	echo "==> Docker is not installed; running setup-droplet.sh as root"
	remote "sudo bash -s" <deploy/setup-droplet.sh
fi

if remote "ss -lnt | grep -qE ':80 |:443 '" && ! remote "test -d ${APP_DIR}"; then
	echo "Port 80 or 443 is already taken on ${HOST} and ${APP_DIR} does not exist."
	echo "This looks like the other project's droplet. Do not overwrite it."
	echo "Add DIGITALOCEAN_ACCESS_TOKEN and ask for a new droplet, or free those ports."
	exit 3
fi

echo "==> Syncing repository"
remote "sudo mkdir -p ${APP_DIR} && sudo chown -R \$(whoami): ${APP_DIR}"
if remote "test -d ${APP_DIR}/.git"; then
	remote "git -C ${APP_DIR} fetch origin ${BRANCH} && git -C ${APP_DIR} checkout ${BRANCH} && git -C ${APP_DIR} pull --ff-only origin ${BRANCH}"
else
	remote "git clone --branch ${BRANCH} ${REPO_URL} ${APP_DIR}"
fi

if ! remote "test -f ${APP_DIR}/.env"; then
	echo "==> Creating .env"
	# Values that are not credentials go into .env. Tokens go into the encrypted store.
	remote "bash -s" <<EOF
set -euo pipefail
cd ${APP_DIR}
cp .env.example .env
chmod 600 .env
PUBLIC_IP="\$(curl -fsS --max-time 10 https://api.ipify.org || hostname -I | awk '{print \$1}')"
DOMAIN="${DOMAIN_VALUE}"
if [ -z "\$DOMAIN" ]; then
  DOMAIN="\${PUBLIC_IP//./-}.sslip.io"
fi
ACME="${ACME_VALUE}"
if [ -z "\$ACME" ]; then
  ACME="admin@\${DOMAIN}"
fi
{
  echo ""
  echo "APP_ENV=production"
  echo "LOG_FORMAT=json"
  echo "POSTGRES_USER=wegotrip"
  echo "POSTGRES_PASSWORD=\$(openssl rand -hex 24)"
  echo "POSTGRES_DB=wegotrip_engine"
  echo "ADMIN_PASSWORD=\$(openssl rand -hex 16)"
  echo "DEPLOY_DOMAIN=\${DOMAIN}"
  echo "ACME_EMAIL=\${ACME}"
  echo "SLACK_CHANNEL=${SLACK_CHANNEL_VALUE}"
  echo "AUTO_PUBLISH_EN=true"
  echo "AUTO_PUBLISH_RU=true"
} >> .env
EOF
fi

COMPOSE="docker compose -f deploy/docker-compose.prod.yml --env-file .env"
echo "==> Building and starting the stack"
remote "cd ${APP_DIR} && ${COMPOSE} up -d --build"

echo "==> Storing credentials encrypted (piped over SSH, not written to .env)"
store_secret() {
	local name="$1" value="${2:-}"
	if [[ -z "$value" ]]; then
		echo "    skip ${name} (not in this agent environment)"
		return 0
	fi
	printf '%s' "$value" | remote "cd ${APP_DIR} && ${COMPOSE} exec -T api wgt secrets set ${name}"
}

store_secret OPENAI_API_KEY "${OPENAI_API_KEY:-}"
store_secret TELEGRAM_BOT_TOKEN "${TELEGRAM_BOT_TOKEN:-}"
store_secret SLACK_BOT_TOKEN "${SLACK_BOT_TOKEN:-${SLACK_BOT_TOKEN_TG:-}}"
store_secret SLACK_SIGNING_SECRET "${SLACK_SIGNING_SECRET:-${SLACK_SIGNING_SECRET_TG:-}}"

echo "==> Doctor"
remote "cd ${APP_DIR} && ${COMPOSE} exec -T api wgt doctor || true"
remote "cd ${APP_DIR} && ${COMPOSE} exec -T api wgt slack-check || true"

DOMAIN="$(remote "grep -E '^DEPLOY_DOMAIN=' ${APP_DIR}/.env | cut -d= -f2-")"
echo
echo "Admin: https://${DOMAIN}/admin"
echo "Slack interactivity: https://${DOMAIN}/slack/interactions"
echo "Slack command:       https://${DOMAIN}/slack/commands"
