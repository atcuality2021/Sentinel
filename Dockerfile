# Sentinel — container image for Cloud Run (and any OCI host).
# Single stage: the app is pure-Python, so a slim base + pip install is enough.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080

WORKDIR /app

# Install dependencies first (layer cache: deps change less often than source).
COPY pyproject.toml ./
COPY src ./src
RUN pip install --upgrade pip && pip install .

# Cloud Run sends SIGTERM and provides $PORT; uvicorn binds 0.0.0.0:$PORT.
EXPOSE 8080
CMD ["sh", "-c", "uvicorn sentinel.web.app:app --host 0.0.0.0 --port ${PORT}"]
