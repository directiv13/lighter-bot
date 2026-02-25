# VPS Setup Guide

This guide walks you through setting up a production Linux VPS to host the
Lighter Whale Tracker bot using Docker, GitHub Actions, and a dedicated
non-root deploy user.

> **Tested on** Ubuntu 22.04 LTS (works on Debian 12 and Ubuntu 24.04 too).

---

## Table of Contents

1. [Server provisioning](#1-server-provisioning)
2. [Initial server hardening](#2-initial-server-hardening)
3. [Create a deploy user](#3-create-a-deploy-user)
4. [Install Docker](#4-install-docker)
5. [Firewall configuration](#5-firewall-configuration)
6. [Application directory setup](#6-application-directory-setup)
7. [Configure environment variables](#7-configure-environment-variables)
8. [First manual deployment](#8-first-manual-deployment)
9. [Configure GitHub Actions secrets](#9-configure-github-actions-secrets)
10. [TLS / HTTPS (optional)](#10-tls--https-optional)
11. [Monitoring & log rotation](#11-monitoring--log-rotation)
12. [Updating the bot](#12-updating-the-bot)
13. [Troubleshooting](#13-troubleshooting)

---

## 1. Server Provisioning

Minimum recommended specs:

| Resource | Minimum | Recommended |
|---|---|---|
| CPU | 1 vCPU | 2 vCPU |
| RAM | 512 MB | 1 GB |
| Disk | 10 GB SSD | 20 GB SSD |
| OS | Ubuntu 22.04 | Ubuntu 22.04 |

Providers that work well: **Hetzner Cloud** (CX11), **DigitalOcean Droplet**, **Vultr**.

---

## 2. Initial Server Hardening

Connect as root and perform basic hardening:

```bash
# Update all packages
apt-get update && apt-get upgrade -y

# Set hostname (optional but useful)
hostnamectl set-hostname whale-tracker

# Configure timezone
timedatectl set-timezone UTC

# Disable password login for root (we'll use SSH keys)
sed -i 's/^#*PermitRootLogin.*/PermitRootLogin without-password/' /etc/ssh/sshd_config
sed -i 's/^#*PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
systemctl reload sshd
```

---

## 3. Create a Deploy User

Create a dedicated `deploy` user that GitHub Actions will SSH into:

```bash
# Create user
adduser --disabled-password --gecos "" deploy

# Add to docker group (so it can run docker commands without sudo)
usermod -aG docker deploy

# Create SSH directory
mkdir -p /home/deploy/.ssh
chmod 700 /home/deploy/.ssh
chown deploy:deploy /home/deploy/.ssh
```

### Generate an SSH key pair for CI/CD

Run this **on your local machine** (not on the VPS):

```bash
ssh-keygen -t ed25519 -C "github-actions-deploy" -f ~/.ssh/deploy_key -N ""
```

This creates:
- `~/.ssh/deploy_key`       ← **private key** – add to GitHub Secrets
- `~/.ssh/deploy_key.pub`   ← **public key**  – add to the VPS

### Authorise the public key on the VPS

```bash
# On the VPS (as root):
cat >> /home/deploy/.ssh/authorized_keys << 'EOF'
<paste contents of deploy_key.pub here>
EOF
chmod 600 /home/deploy/.ssh/authorized_keys
chown deploy:deploy /home/deploy/.ssh/authorized_keys
```

### Verify SSH access

```bash
# From your local machine:
ssh -i ~/.ssh/deploy_key deploy@<VPS_IP>
```

---

## 4. Install Docker

```bash
# Install prerequisites
apt-get install -y ca-certificates curl gnupg lsb-release

# Add Docker's official GPG key
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg

# Add the Docker repository
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
  | tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker Engine and Compose plugin
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Enable Docker service
systemctl enable --now docker

# Verify
docker --version
docker compose version
```

---

## 5. Firewall Configuration

```bash
# Install UFW if not present
apt-get install -y ufw

# Default deny inbound, allow outbound
ufw default deny incoming
ufw default allow outgoing

# Allow SSH (change port if you use a custom SSH port)
ufw allow 22/tcp

# Enable firewall
ufw enable

# Verify
ufw status verbose
```

> The bot only makes **outbound** connections (Telegram, Lighter WS, Pushover).
> No inbound ports are required for the bot itself.

---

## 6. Application Directory Setup

```bash
# Create the deployment directory
mkdir -p /opt/lighter-whale-tracker
chown deploy:deploy /opt/lighter-whale-tracker

# Create persistent data directory (SQLite DB)
mkdir -p /opt/lighter-whale-tracker/data
chown deploy:deploy /opt/lighter-whale-tracker/data
```

Switch to the deploy user and clone the project:

```bash
su - deploy
cd /opt/lighter-whale-tracker

# Clone your repository
git clone https://github.com/<your-org>/lighter-whale-tracker.git .
```

---

## 7. Configure Environment Variables

```bash
# As the deploy user:
cd /opt/lighter-whale-tracker
cp .env.example .env
nano .env   # or vim .env
```

Fill in **all required variables** – see the [Environment Variables table in README.md](../README.md#environment-variables).

Important production settings:

```dotenv
DATABASE_PATH=/opt/lighter-whale-tracker/data/whale_tracker.db
REDIS_HOST=redis
LOG_LEVEL=INFO
```

Protect the file:

```bash
chmod 600 .env
```

---

## 8. First Manual Deployment

Authenticate with GitHub Container Registry (so you can pull the image):

```bash
# As deploy user:
# Generate a GitHub PAT with `read:packages` scope and use it here:
echo "<YOUR_PAT>" | docker login ghcr.io -u <your-github-username> --password-stdin
```

Pull and start services:

```bash
cd /opt/lighter-whale-tracker

# Pull images
docker compose pull

# Start in detached mode
docker compose up -d

# Check status
docker compose ps
docker compose logs -f bot
```

You should see:

```
bot    | 2026-02-25 10:00:00  INFO      __main__  Starting Lighter Whale Tracker ...
bot    | 2026-02-25 10:00:01  INFO      bot.database  Database initialised at /data/whale_tracker.db
bot    | 2026-02-25 10:00:01  INFO      bot.redis_client  Redis connection pool created (redis:6379)
bot    | 2026-02-25 10:00:01  INFO      bot.scheduler  Scheduler started – trade report interval: 5 min
bot    | 2026-02-25 10:00:02  INFO      bot.lighter_ws  Connecting to Lighter WebSocket ...
bot    | 2026-02-25 10:00:02  INFO      bot.lighter_ws  Connected. Subscribing to account_all_trades/...
```

---

## 9. Configure GitHub Actions Secrets

In your GitHub repository go to **Settings → Secrets and variables → Actions** and add:

| Secret name | Value |
|---|---|
| `VPS_HOST` | Your VPS IP or hostname |
| `VPS_USER` | `deploy` |
| `VPS_SSH_KEY` | Contents of `~/.ssh/deploy_key` (private key) |
| `VPS_PORT` | `22` (or your custom SSH port) |
| `DEPLOY_PATH` | `/opt/lighter-whale-tracker` |

After adding secrets, push a commit to `main` and watch the **Actions** tab – the pipeline will:
1. Lint the code
2. Build and push the Docker image to GHCR
3. SSH into the VPS and restart the services

---

## 10. TLS / HTTPS (optional)

The bot does not expose any HTTP port by default. If you add a web dashboard in
the future, use **Caddy** as a reverse-proxy:

```bash
apt-get install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list
apt-get update && apt-get install -y caddy
```

Then add a `Caddyfile`:

```
yourdomain.com {
    reverse_proxy localhost:8080
}
```

---

## 11. Monitoring & Log Rotation

### View live logs

```bash
docker compose logs -f bot         # bot service
docker compose logs -f redis       # redis service
```

### Automatic log rotation

Docker's `json-file` driver is already configured in `docker-compose.yml` with
`max-size: 10m` and `max-file: 3` (30 MB total cap per service).

### System resource monitoring

```bash
# Install htop
apt-get install -y htop
htop

# Docker stats
docker stats
```

### Set up automatic container restarts

All services in `docker-compose.yml` have `restart: unless-stopped` so they
restart automatically after a reboot or crash.

Enable Docker to start on boot:

```bash
systemctl enable docker
```

---

## 12. Updating the Bot

### Via GitHub Actions (recommended)

Simply push a commit to `main`. The pipeline handles everything.

### Manual update on the VPS

```bash
# As deploy user:
cd /opt/lighter-whale-tracker

git pull origin main           # update compose file / .env.example if needed
docker compose pull bot        # pull latest image
docker compose up -d bot       # rolling restart
docker image prune -f          # clean up old images
```

---

## 13. Troubleshooting

### Bot not connecting to WebSocket

```bash
docker compose logs bot | grep "WebSocket\|Connecting\|reconnect"
```

Check that `LIGHTER_AUTH_TOKEN` and `LIGHTER_ACCOUNT_ID` are correct in `.env`.

### Redis connection refused

```bash
docker compose ps redis
docker compose logs redis
```

Ensure the `redis` service is healthy before `bot` starts (the `depends_on`
condition handles this at startup).

### Telegram messages not sending

1. Verify `TELEGRAM_BOT_TOKEN` is valid: `curl https://api.telegram.org/bot<TOKEN>/getMe`
2. Confirm the bot is an **admin** of the channel.
3. Confirm `TELEGRAM_CHANNEL_ID` starts with `-100` for public channels.

### Pushover alerts not arriving

1. Confirm the Pushover **User Key** is correct (not the App API Token).
2. Check logs: `docker compose logs bot | grep -i pushover`
3. Verify the user's cooldown window: `last_notification_at` in the SQLite DB.

```bash
# Inspect the SQLite database directly:
docker compose exec bot sqlite3 /data/whale_tracker.db "SELECT * FROM users;"
```

### Re-initialise (full reset)

```bash
docker compose down -v   # removes volumes including Redis data
rm -f /opt/lighter-whale-tracker/data/whale_tracker.db
docker compose up -d
```

---

*Generated for Lighter Whale Tracker – February 2026*
