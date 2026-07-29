# Shared base image for API and worker.
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps (libpq for psycopg, build tools kept minimal via binary wheels).
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first for better layer caching.
COPY pyproject.toml ./
RUN pip install --upgrade pip \
    && pip install \
        "fastapi>=0.115" "uvicorn[standard]>=0.30" "sqlalchemy>=2.0" "alembic>=1.13" \
        "httpx>=0.27" "msal>=1.30" "apscheduler>=3.10" "pydantic>=2.7" \
        "pydantic-settings>=2.3" "psycopg[binary]>=3.2" "cryptography>=42" \
        "python-jose[cryptography]>=3.3" "bcrypt>=4.1" "python-multipart>=0.0.9"

COPY . .

# ---- Frontend build (produces the static SPA bundle) ----
FROM node:20-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# ---- API image ----
FROM base AS api
# Bake the built SPA into the image so FastAPI serves it in production.
COPY --from=frontend-build /app/frontend/dist ./frontend/dist
EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]

# ---- Worker image ----
FROM base AS worker
CMD ["python", "-m", "worker.main"]
