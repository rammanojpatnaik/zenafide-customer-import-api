FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev supervisor \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini .
COPY tests ./tests
COPY supervisord.conf /etc/supervisor/conf.d/zenafide.conf

RUN mkdir -p /var/log/zenafide /var/lib/zenafide/uploads

EXPOSE 8000

# Default: single-container mode (API + Celery worker via supervisord).
# Override CMD in docker-compose.dev.yml or Railway worker service if needed.
CMD ["supervisord", "-c", "/etc/supervisor/supervisord.conf"]
