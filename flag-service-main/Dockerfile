# analytics-service-main
# =========================================================
# Etapa 1: Build
# =========================================================
FROM python:3.9.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends libpq-dev gcc

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install -r requirements.txt

# =========================================================
# Etapa 2: Runtime
# =========================================================
FROM python:3.9.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

RUN groupadd -r appgroup && useradd -r -g appgroup appuser

COPY --from=builder /opt/venv /opt/venv

COPY --chown=appuser . .

USER appuser

EXPOSE 8002

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8002/health')"

CMD ["gunicorn", "--bind", "0.0.0.0:8002", "app:app"]