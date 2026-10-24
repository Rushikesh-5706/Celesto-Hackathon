FROM python:3.12-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --shell /bin/bash appuser

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY seeds/ ./seeds/
COPY reports/ ./reports/
COPY logs/ ./logs/
COPY fixtures/ ./fixtures/
COPY README.md ./
COPY pyproject.toml ./
RUN pip install --no-cache-dir .

RUN mkdir -p /app/var && chown appuser:appuser /app/var

USER appuser

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

EXPOSE 8080

CMD ["python", "-m", "reprobox", "serve"]
