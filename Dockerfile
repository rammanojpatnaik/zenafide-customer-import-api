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
COPY start.sh /start.sh

RUN chmod +x /start.sh \
    && mkdir -p /var/log/zenafide /var/lib/zenafide/uploads

EXPOSE 8000

# Runs migrations first, then starts API + Celery worker via supervisord.
CMD ["/start.sh"]
