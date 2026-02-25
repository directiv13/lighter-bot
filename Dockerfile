FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN addgroup --system bot && adduser --system --ingroup bot bot

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY lighter_bot ./lighter_bot
COPY bot.py ./

RUN mkdir -p /data && chown -R bot:bot /app /data

USER bot

CMD ["python", "-m", "lighter_bot.main"]
