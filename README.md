# Lighter Whale Tracker

A Telegram bot that monitors a **Lighter DEX** whale account in real-time, delivers
5-minute cumulative trade reports to a Telegram channel, and sends instant sell-alert
push notifications via **Pushover**.

---

## Features

| Feature | Details |
|---|---|
| **Live trade monitoring** | WebSocket connection to `wss://mainnet.zklighter.elliot.ai/stream` |
| **5-min Telegram reports** | Cumulative buy/sell volumes per market posted to a channel |
| **Instant sell alerts** | Pushover notification fired on every detected sell |
| **Spam prevention** | Per-user 2-hour cooldown between Pushover alerts |
| **Subscriber management** | `/enable_pushover` / `/disable_pushover` Telegram commands |
| **Persistent storage** | SQLite for user data, Redis Sorted-Sets for rolling trade cache |
| **Auto-reconnect** | Exponential back-off if the WebSocket drops |
| **Dockerised** | Single `docker compose up -d` to run everything |
| **CI / CD** | GitHub Actions: lint → build image → push to GHCR → deploy to VPS |

---

## Architecture

```
┌─────────────────────┐      WebSocket      ┌──────────────────┐
│  Lighter Exchange   │ ──────────────────▶ │  lighter_ws.py   │
│  (mainnet stream)   │                     │  (reconnecting)  │
└─────────────────────┘                     └────────┬─────────┘
                                                     │ store trades
                                          ┌──────────▼──────────┐
                                          │    Redis             │
                                          │  Sorted Set          │
                                          │  trades:{account}    │
                                          └──────────┬──────────┘
                                                     │ read every 5 min
                                          ┌──────────▼──────────┐
                                          │   scheduler.py       │
                                          │   (APScheduler)      │
                                          └──────────┬──────────┘
                                                     │ post report
                                          ┌──────────▼──────────┐
                                          │  Telegram Channel    │
                                          └─────────────────────┘

  On every SELL detected:
  lighter_ws.py ──▶ pushover.py ──▶ Pushover API ──▶ User device

  Telegram commands:
  User ──▶ telegram_bot.py ──▶ SQLite (users table)
```

---

## Quick Start (local)

### Prerequisites

- Docker ≥ 24 and Docker Compose v2
- A Telegram bot token (from [@BotFather](https://t.me/BotFather))
- A Telegram channel where the bot is an **admin**
- A Lighter account ID and auth token
- *(optional)* Pushover account for sell alerts

### 1 – Clone and configure

```bash
git clone https://github.com/<your-org>/lighter-whale-tracker.git
cd lighter-whale-tracker

cp .env.example .env
# Edit .env with your real values
```

### 2 – Run

```bash
docker compose up -d
docker compose logs -f bot   # tail logs
```

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `LIGHTER_ACCOUNT_ID` | ✅ | – | Lighter account ID to monitor |
| `LIGHTER_AUTH_TOKEN` | ✅ | – | Lighter WebSocket auth token |
| `LIGHTER_WS_URL` | – | `wss://mainnet.zklighter.elliot.ai/stream` | WebSocket endpoint |
| `TELEGRAM_BOT_TOKEN` | ✅ | – | Token from BotFather |
| `TELEGRAM_CHANNEL_ID` | ✅ | – | Channel chat ID (e.g. `-1001234567890`) |
| `REDIS_HOST` | – | `redis` | Redis hostname |
| `REDIS_PORT` | – | `6379` | Redis port |
| `REDIS_DB` | – | `0` | Redis database index |
| `REDIS_PASSWORD` | – | ─ | Redis password (blank = no auth) |
| `DATABASE_PATH` | – | `/data/whale_tracker.db` | SQLite file path |
| `REPORT_INTERVAL_MINUTES` | – | `5` | Telegram report cadence |
| `SELL_NOTIFY_COOLDOWN_HOURS` | – | `2` | Min hours between Pushover alerts per user |
| `LOG_LEVEL` | – | `INFO` | Python log level |

---

## Telegram Commands

| Command | Description |
|---|---|
| `/start` | Welcome message |
| `/help` | Show available commands |
| `/enable_pushover <key>` | Subscribe to Pushover sell alerts |
| `/disable_pushover` | Unsubscribe from Pushover alerts |
| `/status` | Bot health and subscriber count |

### Getting your Pushover user key

1. Sign up at [pushover.net](https://pushover.net).
2. Install the Pushover app on your device.
3. Your **User Key** is shown on the dashboard.
4. Send `/enable_pushover <your-user-key>` to the bot.

---

## Project Structure

```
lighter-whale-tracker/
├── bot/
│   ├── __init__.py
│   ├── config.py          # Env-var configuration (singleton)
│   ├── database.py        # SQLite helpers (aiosqlite)
│   ├── lighter_ws.py      # Lighter WebSocket client
│   ├── main.py            # Application entry-point
│   ├── pushover.py        # Pushover notification service
│   ├── redis_client.py    # Redis Sorted-Set helpers
│   ├── scheduler.py       # APScheduler – 5-min report job
│   └── telegram_bot.py    # Telegram command handlers
├── docs/
│   └── VPS_SETUP.md       # Step-by-step VPS deployment guide
├── .env.example
├── .gitignore
├── .github/
│   └── workflows/
│       └── deploy.yml     # CI/CD pipeline
├── docker-compose.yml
├── Dockerfile
├── README.md
└── requirements.txt
```

---

## Development

```bash
# Create a virtual environment
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux / macOS

pip install -r requirements.txt

cp .env.example .env            # fill in values
python -m bot.main
```

---

## CI / CD

The GitHub Actions workflow (`.github/workflows/deploy.yml`) runs on every push to `main`:

1. **Lint** – `ruff check bot/`
2. **Build & Push** – multi-stage Docker image pushed to GHCR
3. **Deploy** – SSH into the VPS, pull the new image, restart with `docker compose`

### Required GitHub Secrets

| Secret | Description |
|---|---|
| `VPS_HOST` | VPS IP address or hostname |
| `VPS_USER` | SSH username (e.g. `deploy`) |
| `VPS_SSH_KEY` | Private SSH key (ED25519 or RSA) |
| `VPS_PORT` | SSH port (default `22`) |
| `DEPLOY_PATH` | Absolute path on VPS (e.g. `/opt/lighter-whale-tracker`) |

---

## License

MIT
