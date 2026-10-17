# ── Build Stage ──────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# System deps for the SQLite-backed stores and Playwright
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libffi-dev libsqlite3-dev \
    && rm -rf /var/lib/apt/lists/*

# A built image is a copy of the Licensed Work, so the licence travels inside it.
COPY LICENSE NOTICE ./

COPY pyproject.toml README.md ./
COPY core/ core/
COPY server/ server/
COPY ui/ ui/
COPY utils/ utils/
COPY skills/ skills/
COPY app/ app/
COPY knowledge/ knowledge/
COPY run_server.py ephe.py ephe_cli.py ./

RUN pip install --no-cache-dir .

# ── Frontend Stage ───────────────────────────────────────────────
# app/dist is a git-ignored build artifact, so an image built without this
# stage ships source only and "/" answers with the "build the PWA" hint page
# instead of the app. Node 22 matches .nvmrc; pnpm is activated from the
# packageManager pin in app/package.json, the way CI does it.
FROM node:22-slim AS frontend

# CI=true matches frontend-build.yml (pnpm/vite behave the same here as in CI and
# never block on a prompt in a build with no TTY).
ENV CI=true

WORKDIR /build/app

COPY app/ ./

RUN corepack enable \
    && corepack prepare "$(node -p 'require("./package.json").packageManager')" --activate \
    && pnpm install --frozen-lockfile \
    && pnpm run build

# ── Runtime Stage ────────────────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

# Runtime deps only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsqlite3-0 curl openssh-client \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages + app
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /build /app

# The built PWA goes where server/main.py resolve_frontend_dir looks for it.
COPY --from=frontend /build/app/dist /app/app/dist

# Persistent data: memory, sessions, skills, profile
VOLUME ["/root/.ephe"]

EXPOSE 8765

# Health check against /api/health
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -sf http://localhost:8765/api/health || exit 1

# Start the web server. The engine is an explicit choice (no silent default,
# W18): pass EPHE_MODEL_PROVIDER + the matching endpoint env, or mount a
# configured ~/.ephe/engine.json into the volume. Without either, the
# container stops with an actionable hint instead of picking an engine itself.
#   docker run -e EPHE_MODEL_PROVIDER=local_ollama \
#     -e EPHE_LOCAL_OLLAMA_BASE_URL=http://host.docker.internal:11434 \
#     -e EPHE_MODEL=gemma4:12b ...
#
# Binding (I2-4). EPHE_BIND is the address *inside* the container's own network
# namespace, and it stays 0.0.0.0 on purpose: with `-p` publishing, Docker's
# proxy connects to the container's routable address, so a loopback bind here
# would be unreachable and every published port would silently stop working.
# What decides host exposure is the mapping, and both docker-compose.yml and
# the documented `docker run` publish to 127.0.0.1 only — LAN/mobile access
# stays a deliberate opt-in. Non-loopback binds force LAN auth (run_server.py
# fails closed rather than exposing an unauthenticated API).
# For `--network host`, where the container shares the host's loopback, set
# EPHE_BIND=127.0.0.1 to keep it loopback-only.
ENV EPHE_BIND=0.0.0.0
CMD ["sh", "-c", "exec python run_server.py --host \"$EPHE_BIND\" --port 8765"]
