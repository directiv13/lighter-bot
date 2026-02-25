# ── Stage 1: build deps ───────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build tools
RUN apt-get update && apt-get install -y --no-install-recommends gcc && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip \
 && pip install --prefix=/install --no-cache-dir -r requirements.txt

# ── Stage 2: runtime image ────────────────────────────────────────────────────
FROM python:3.12-slim

# Non-root user for security
RUN groupadd -r appuser && useradd -r -g appuser appuser

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy source
COPY bot/ ./bot/

# Persistent data volume mount point
RUN mkdir -p /data && chown appuser:appuser /data

USER appuser

# Health-check: verify SQLite DB dir is writable
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import os; os.access('/data', os.W_OK) or exit(1)"

CMD ["python", "-m", "bot.main"]
