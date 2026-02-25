# Lighter Trade Monitor Bot

Asynchronous Telegram bot that polls Lightalytics every 5 minutes and sends:
- Immediate alert for every `Sell` trade
- Batch summary with cumulative Buy/Sell USD totals
- Pushover alerts for subscribed users on `Sell` with anti-spam cooldown (1 notification per user per 2 hours by default)

## Stack

- Python 3.11+
- `httpx` (async HTTP)
- `aiogram` (Telegram API)
- `apscheduler` (5-minute scheduling)
- `pydantic` (payload validation)
- `aiosqlite` (subscription storage)

## Local Run

1. Create and activate virtual environment.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Create `.env` from `.env.example` and set values:
   - `TELEGRAM_BOT_TOKEN`
   - `CHANNEL_ID`
  - `PUSHOVER_APP_TOKEN`
4. Run:
   ```bash
  python -m lighter_bot.main
   ```

## Project Structure (Clean Architecture)

```text
lighter_bot/
  core/             # configuration and app settings
  domain/           # core entities/models
  application/      # use-case orchestration
  infrastructure/   # HTTP clients and persistence adapters
  interfaces/       # Telegram command handlers
  main.py           # composition root / app bootstrap
bot.py              # compatibility wrapper
```

## Telegram Commands

Users can self-subscribe for Pushover sell notifications:

- `/enable_pushover <user-key>`
  - Stores `user_id` + `pushover_user_key` in SQLite
- `/disable_pushover`
  - Deletes subscription from SQLite

Database table stores:
- `user_id`
- `pushover_user_key`
- `last_notification_at`

Cooldown behavior:
- On each sell, subscribed users receive a Pushover alert only if their last Pushover notification was more than `NOTIFICATION_COOLDOWN_MINUTES` ago (default `120`).

## Docker Run

Build local image:
```bash
docker build -t lighter-bot:local .
```

Run container:
```bash
docker run --name lighter-bot --restart unless-stopped --env-file .env -e STATE_FILE=/data/state.json -v lighter_bot_data:/data lighter-bot:local
```

Container entrypoint runs:
```bash
python -m lighter_bot.main
```

## Docker Compose (VPS)

`docker-compose.yml` expects:
- `.env` file in the same directory
- Image configured via `BOT_IMAGE` (default: `ghcr.io/your-org/lighter-bot:latest`)
- Volume-backed files under `/data`:
  - `STATE_FILE=/data/state.json`
  - `DB_FILE=/data/subscriptions.db`

Start:
```bash
docker compose up -d
```

## GitHub Actions Pipelines

- **CI**: `.github/workflows/ci.yml`
  - Runs on push/PR
  - Installs dependencies and checks Python syntax

- **Docker Publish**: `.github/workflows/docker-publish.yml`
  - Runs on push to `main` and version tags
  - Builds and pushes image to GHCR:
    - `ghcr.io/<owner>/lighter-bot:latest`
    - `ghcr.io/<owner>/lighter-bot:<tag>`
    - `ghcr.io/<owner>/lighter-bot:sha-...`

- **Deploy to VPS**: `.github/workflows/deploy-vps.yml`
  - Manual trigger (`workflow_dispatch`)
  - SSH to VPS, pull latest image, restart compose service

## Required GitHub Secrets

For deployment workflow, add repository secrets:
- `VPS_HOST`
- `VPS_USER`
- `VPS_PORT`
- `VPS_SSH_KEY`
- `GHCR_USERNAME`
- `GHCR_TOKEN` (PAT with `read:packages`)

## VPS Setup Guide

Detailed instructions are in [docs/VPS_SETUP.md](docs/VPS_SETUP.md).

## Operations

Check logs:
```bash
docker compose logs -f lighter-bot
```

Restart bot:
```bash
docker compose restart lighter-bot
```

Update to latest image:
```bash
docker compose pull && docker compose up -d
```
