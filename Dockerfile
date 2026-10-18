# --- build the frontend ---
FROM node:22-slim AS web
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- run the backend ---
FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:0.10 /uv /uvx /bin/
WORKDIR /app
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1
COPY backend/pyproject.toml backend/uv.lock backend/.python-version backend/
RUN cd backend && uv sync --frozen --no-dev --no-install-project
COPY backend/ backend/
COPY samples/ samples/
COPY --from=web /app/frontend/dist frontend/dist
RUN cd backend && uv sync --frozen --no-dev
ENV MCS_HOST=0.0.0.0 \
    MCS_PORT=8080 \
    MCS_DATA_DIR=/data \
    MCS_USE_KEYCHAIN=false \
    MCS_EPHEMERAL=true \
    MCS_EXTRACTOR=anthropic
EXPOSE 8080
CMD ["/app/backend/.venv/bin/mcs", "serve", "--seed-sample-roster"]
