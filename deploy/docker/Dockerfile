# syntax=docker/dockerfile:1
# Two images from one file: `app` (gunicorn and workers) and `web` (nginx plus the built React app).

FROM node:22-bookworm-slim AS frontend
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim-bookworm AS app
RUN apt-get update \
    && apt-get install -y --no-install-recommends bash gcc pkg-config default-libmysqlclient-dev mariadb-client \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/timetable/app
COPY requirements.txt ./requirements.txt
COPY deploy/requirements-prod.txt deploy/requirements-prod.txt
RUN pip install --no-cache-dir -r deploy/requirements-prod.txt
COPY . .
RUN useradd --system --home-dir /opt/timetable --shell /usr/sbin/nologin timetable \
    && mkdir -p logs uploads static/uploads /var/backups/timetable \
    && chown -R timetable:timetable logs uploads static/uploads /var/backups/timetable \
    && chmod 755 deploy/docker/entrypoint.sh deploy/backup.sh deploy/restore.sh
USER timetable
ENV FLASK_APP=wsgi:app \
    BACKGROUND_WORKERS=False \
    GUNICORN_BIND=0.0.0.0:8000 \
    PYTHONUNBUFFERED=1
EXPOSE 8000
ENTRYPOINT ["/opt/timetable/app/deploy/docker/entrypoint.sh"]
CMD ["gunicorn", "--config", "deploy/gunicorn.conf.py", "wsgi:app"]

FROM nginx:1.27-alpine AS web
COPY deploy/nginx/timetable-docker.conf /etc/nginx/conf.d/default.conf
COPY deploy/nginx/timetable-proxy.conf /etc/nginx/timetable-proxy.conf
COPY --from=frontend /src/frontend/dist /usr/share/nginx/html
