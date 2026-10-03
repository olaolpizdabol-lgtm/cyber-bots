FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p data downloads temp credentials

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

CMD ["python", "scripts/run_all_cyber_bots.py"]
