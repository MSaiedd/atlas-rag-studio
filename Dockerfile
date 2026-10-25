FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DB_PATH=/app/data/app.db
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir . && useradd --create-home app && mkdir -p /app/data /app/artifacts && chown -R app:app /app
USER app
EXPOSE 8000
CMD ["uvicorn", "supportpilot.api:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
