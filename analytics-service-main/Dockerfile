# analytics-service-main
# =========================================================
# Etapa 1: Build
# =========================================================
FROM python:3.12.18-slim as builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# =========================================================
# Etapa 2: Runtime
# =========================================================
FROM python:3.12.18-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

RUN groupadd -r appuser && useradd -r -g appuser appuser

COPY --from=builder /opt/venv /opt/venv

COPY --chown=appuser:appuser . .

USER appuser

EXPOSE 8005

CMD ["gunicorn", "--bind", "0.0.0.0:8005", "app:app"]