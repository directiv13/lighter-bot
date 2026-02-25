# Linux VPS Deployment Guide

This guide deploys the bot with Docker Compose on a Linux VPS (Ubuntu 22.04/24.04 recommended).

## 1) Provision VPS

Minimum recommendation:
- 1 vCPU
- 1 GB RAM
- 20 GB disk
- Public IPv4

Open network access:
- SSH (port `22` or your custom port)

## 2) Initial server hardening

SSH into VPS as root, then:

```bash
apt update && apt upgrade -y
adduser botadmin
usermod -aG sudo botadmin
```

Set up SSH key auth for `botadmin` and disable password auth (recommended).

Optional firewall (UFW):
```bash
ufw allow OpenSSH
ufw enable
ufw status
```

## 3) Install Docker + Compose plugin

As root or sudo user:

```bash
apt install -y ca-certificates curl gnupg
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" > /etc/apt/sources.list.d/docker.list
apt update
apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable docker
systemctl start docker
```

Add your deployment user to docker group:
```bash
usermod -aG docker botadmin
```
Log out and log in again.

## 4) Prepare deployment directory

```bash
mkdir -p /opt/lighter-bot
chown -R $USER:$USER /opt/lighter-bot
cd /opt/lighter-bot
```

Copy these files from repository into `/opt/lighter-bot`:
- `docker-compose.yml`
- `.env` (create from `.env.example`)

Create `.env`:
```env
TELEGRAM_BOT_TOKEN=<your_bot_token>
CHANNEL_ID=<telegram_channel_id>
PUSHOVER_APP_TOKEN=<your_pushover_app_token>
BOT_IMAGE=ghcr.io/<github-owner>/lighter-bot:latest

# Optional
LIGHTALYTICS_ACCOUNT_ID=714638
POLL_LIMIT=500
STATE_FILE=/data/state.json
DB_FILE=/data/subscriptions.db
NOTIFICATION_COOLDOWN_MINUTES=120
```

## 5) Configure GHCR access on VPS

Create GitHub PAT with `read:packages` scope.

Login on VPS:
```bash
docker login ghcr.io -u <github-username>
```
Use PAT as password.

## 6) Start service

```bash
cd /opt/lighter-bot
docker compose pull
docker compose up -d
```

Verify:
```bash
docker compose ps
docker compose logs -f lighter-bot
```

## 7) Configure GitHub Actions deploy

In repository settings, add secrets:
- `VPS_HOST`: server IP or domain
- `VPS_USER`: e.g., `botadmin`
- `VPS_PORT`: e.g., `22`
- `VPS_SSH_KEY`: private key content for CI deploy user
- `GHCR_USERNAME`: GitHub username
- `GHCR_TOKEN`: PAT with `read:packages`

Deploy flow:
1. Push to `main` to publish image (`docker-publish.yml`).
2. Run `Deploy to VPS` workflow manually.

## 8) Day-2 operations

Update bot:
```bash
docker compose pull && docker compose up -d
```

Restart:
```bash
docker compose restart lighter-bot
```

Stop:
```bash
docker compose down
```

Tail logs:
```bash
docker compose logs -f lighter-bot
```

## 9) Troubleshooting

- `manifest unknown`: image name/tag mismatch in `BOT_IMAGE`.
- `unauthorized`: GHCR login missing/expired token.
- Bot starts but no alerts:
  - check `TELEGRAM_BOT_TOKEN`
  - verify bot has permission to post in channel
  - verify `CHANNEL_ID` format (`-100...` for channels)
- Pushover alerts missing:
  - check `PUSHOVER_APP_TOKEN`
  - user must subscribe using `/enable_pushover <user-key>`
  - verify cooldown (`NOTIFICATION_COOLDOWN_MINUTES`) is not blocking repeated notifications
- API errors/rate limits:
  - bot already retries with backoff; inspect logs for status codes.
