# Multi-stage, non-root, slim, pinned base by digest at deploy time (see SECURITY.md).
FROM python:3.12-slim AS base

# Drop privileges + sane Python runtime flags.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# --- builder: install deps into a venv ---
FROM base AS builder
WORKDIR /app
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY requirements.txt .
RUN pip install -r requirements.txt

# --- runtime ---
FROM base AS runtime
# Non-root user (CIS / Azure baseline).
RUN useradd --create-home --uid 10001 appuser
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
WORKDIR /app
COPY app ./app
COPY migrations ./migrations
USER appuser
EXPOSE 8000
# Healthcheck hits liveness; orchestrator readiness uses /readyz.
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz').status==200 else 1)"
# 2 workers is plenty for an I/O-bound single-user MVP; scale via replicas in Azure.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--proxy-headers"]
