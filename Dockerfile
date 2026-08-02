# syntax=docker/dockerfile:1

# ---- builder: compiles binary extensions (pyswisseph, timezonefinder deps) ----
FROM python:3.11-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        python3-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# ---- runtime: no compiler, no build headers ----
FROM python:3.11-slim AS runtime

RUN useradd --create-home --uid 1000 --shell /usr/sbin/nologin appuser

WORKDIR /app

COPY --from=builder /root/.local /home/appuser/.local
COPY . .

RUN chown -R appuser:appuser /app

# Timeweb Cloud managed PostgreSQL требует sslmode=verify-full, для чего
# libpq ищет корневой сертификат УЦ по умолчанию в ~/.postgresql/root.crt
# текущего пользователя (appuser). Сертификат публичный (не секрет,
# коммитится в репозиторий — см. certs/timeweb-root.crt и README).
# Копируется только сюда, отдельно от общего COPY . ., с правами на чтение
# только для appuser — после создания пользователя, как и требуется.
RUN mkdir -p /home/appuser/.postgresql && chown appuser:appuser /home/appuser/.postgresql
COPY --chown=appuser:appuser certs/timeweb-root.crt /home/appuser/.postgresql/root.crt
RUN chmod 400 /home/appuser/.postgresql/root.crt

USER appuser

ENV PATH=/home/appuser/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
