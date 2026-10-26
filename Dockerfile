FROM node:22-alpine AS frontend
WORKDIR /ui/frontend
COPY frontend/package*.json ./
RUN --mount=type=cache,target=/root/.npm npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DEFAULT_TIMEOUT=120 ATLAS_DATA_DIR=/app/data
WORKDIR /app
RUN --mount=type=cache,id=atlas-pip,target=/root/.cache/pip pip install torch --index-url https://download.pytorch.org/whl/cpu
COPY pyproject.toml README.md ./
COPY src ./src
COPY --from=frontend /ui/src/atlas_rag/web ./src/atlas_rag/web
COPY data/examples ./data/examples
COPY data/training ./data/training
RUN --mount=type=cache,id=atlas-pip,target=/root/.cache/pip pip install '.[models]' && useradd --create-home app && mkdir -p /app/artifacts /home/app/.cache/huggingface && chown -R app:app /app /home/app
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"
CMD ["uvicorn", "atlas_rag.api:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
