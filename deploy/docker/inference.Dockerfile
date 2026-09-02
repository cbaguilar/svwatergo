FROM python:3.12-slim-bookworm

WORKDIR /app

RUN apt-get update \
  && apt-get install -y --no-install-recommends ffmpeg curl \
  && rm -rf /var/lib/apt/lists/*

COPY python/analytics/requirements.txt /tmp/analytics-requirements.txt
RUN pip install --no-cache-dir -r /tmp/analytics-requirements.txt

COPY python ./python

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
EXPOSE 8788

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8788/health || exit 1

CMD ["python", "python/analytics/inference_service.py", "--host", "0.0.0.0", "--port", "8788", "--artifacts-root", "/app/data/analytics/inference_service"]
