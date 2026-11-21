FROM python:3.12.14-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN groupadd --system app && useradd --system --gid app --no-create-home app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY migrations/ migrations/
COPY review/ review/
COPY wsgi.py .

ARG VERSION=dev
ENV VERSION=${VERSION} \
    PORT=8000

USER app
EXPOSE 8000

# --preload builds the app once, in the master process, so startup migrations run once and not once per worker.
CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:${PORT} --workers 2 --threads 4 --timeout 60 --preload --no-control-socket wsgi:app"]
