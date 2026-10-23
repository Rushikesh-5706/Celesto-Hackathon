FROM python:3.12-slim

# Install curl for the healthcheck; no-install-recommends keeps the image lean.
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

# Run as non-root.
RUN useradd --create-home --shell /bin/bash appuser

WORKDIR /app

# Pin dependencies before copying the full source so Docker can cache this layer.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application source and supporting files.
COPY src/ ./src/
COPY seeds/ ./seeds/
COPY reports/ ./reports/
COPY logs/ ./logs/
COPY fixtures/ ./fixtures/
COPY pyproject.toml ./
RUN pip install --no-cache-dir .

# Writable directory for the audit log and other runtime output.
RUN mkdir -p /app/var && chown appuser:appuser /app/var

USER appuser

ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

EXPOSE 8080

CMD ["python", "-m", "reprobox", "serve"]
