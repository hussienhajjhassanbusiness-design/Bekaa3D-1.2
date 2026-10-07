# syntax=docker/dockerfile:1

# ---- Builder: compile deps into a venv ----
FROM python:3.13-slim AS builder

# Use HTTPS to avoid transparent HTTP caches serving mismatched archives.
RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' \
        /etc/apt/sources.list.d/debian.sources \
    && apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

ENV VENV_PATH=/opt/venv
RUN python -m venv "$VENV_PATH"
ENV PATH="$VENV_PATH/bin:$PATH"

WORKDIR /build
COPY pyproject.toml requirements.txt ./
COPY src ./src

# Runtime lock only: exact, hash-checked versions (CONTRIBUTING.md
# "Dependencies"), then the project without resolving anything further.
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir --require-hashes -r requirements.txt \
    && pip install --no-cache-dir --no-deps .

# ---- Runtime: slim image, no compilers ----
FROM python:3.13-slim AS runtime

# Use HTTPS to avoid transparent HTTP caches serving mismatched archives.
RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' \
        /etc/apt/sources.list.d/debian.sources \
    && apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 appuser

ENV VENV_PATH=/opt/venv
COPY --from=builder "$VENV_PATH" "$VENV_PATH"
ENV PATH="$VENV_PATH/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app
COPY --chown=appuser:appuser src ./src
COPY --chown=appuser:appuser alembic.ini ./
COPY --chown=appuser:appuser migrations ./migrations

USER appuser
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health/live || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--app-dir", "src"]
