# Multi-stage build for backend
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies in a virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir -r requirements.txt

# -----------------------------------------------------------------------------
# Test stage (dev-only). Layers pytest + the tests/ tree on top of the builder
# venv. NOT part of the runtime image: the `runtime` stage below is the default
# build target, so `docker compose build` / `up` never include test tooling.
# Build explicitly with `--target tests` (or the gated `backend_tests` compose
# service) to run the suite.
# -----------------------------------------------------------------------------
FROM builder AS tests

WORKDIR /app

# Base deps are already installed in the builder venv; add only the test tooling.
COPY requirements-dev.txt .
RUN pip install --no-cache-dir -r requirements-dev.txt

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini .
COPY pytest.ini .
COPY tests ./tests

ENV PYTHONUNBUFFERED=1
CMD ["python", "-m", "pytest", "-q"]


# Final stage
FROM python:3.11-slim AS runtime

WORKDIR /app

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Copy application code
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini .

# Set environment variables
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Health check
HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "from urllib.request import urlopen; res = urlopen('http://localhost:8000/health', timeout=3); exit(0 if res.status == 200 else 1)"

EXPOSE 8000

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
