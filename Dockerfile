FROM python:3.11-slim@sha256:db3ff2e1800a8581e2c48a27c3995339d47bdf046da21c7627accd3d51053a93 AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY app/requirements.txt requirements.txt
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

FROM python:3.11-slim@sha256:db3ff2e1800a8581e2c48a27c3995339d47bdf046da21c7627accd3d51053a93 AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --system hereiam && useradd --system --gid hereiam --home-dir /nonexistent --shell /usr/sbin/nologin hereiam

WORKDIR /app
COPY --from=builder /wheels /wheels
COPY app/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --no-index --find-links=/wheels -r /app/requirements.txt \
    && rm -rf /wheels

COPY --chown=hereiam:hereiam app /app

USER hereiam

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl --fail --silent --max-time 4 http://127.0.0.1:8000/api/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--timeout-keep-alive", "10", "--limit-concurrency", "32", "--backlog", "64"]

FROM runtime AS test
USER root
COPY requirements-dev.txt /app/requirements-dev.txt
RUN pip install --no-cache-dir -r /app/requirements-dev.txt
COPY --chown=hereiam:hereiam app /workspace/app
COPY --chown=hereiam:hereiam tests /workspace/tests
COPY --chown=hereiam:hereiam scripts /workspace/scripts
COPY --chown=hereiam:hereiam pyproject.toml /workspace/pyproject.toml
WORKDIR /workspace
ENV PYTHONPATH=/workspace/app
USER hereiam
CMD ["pytest", "-q"]
