FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg curl ca-certificates \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
    libgbm1 libpango-1.0-0 libcairo2 libasound2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    playwright install chromium

# Офіційний бінарний сервер telegram-bot-api (підтримка файлів до 2 ГБ прямо в чаті)
COPY --from=aiogram/telegram-bot-api:latest /usr/local/bin/telegram-bot-api /usr/local/bin/telegram-bot-api

COPY . .

RUN mkdir -p data downloads temp credentials

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

CMD ["python", "run_all_bots.py"]
