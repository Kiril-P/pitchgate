FROM python:3.15.1-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Debian publishes security fixes before the Python base image is rebuilt; the image scan in CI fails on any fixable HIGH or CRITICAL.
RUN apt-get update && apt-get upgrade -y --no-install-recommends && rm -rf /var/lib/apt/lists/*

RUN groupadd --system app && useradd --system --gid app --no-create-home app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY migrations/ migrations/
COPY ideas/ ideas/
COPY wsgi.py .

ARG VERSION=dev
ENV VERSION=${VERSION} \
    PORT=8000

USER app
EXPOSE 8000

# Docker and compose report the container's health from /health; Container Apps runs its own probes.
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
  CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/health' % os.environ['PORT'], timeout=4)"]

# --preload builds the app once, in the master process, so startup migrations run once and not once per worker.
CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:${PORT} --workers 2 --threads 4 --timeout 60 --preload --no-control-socket wsgi:app"]
