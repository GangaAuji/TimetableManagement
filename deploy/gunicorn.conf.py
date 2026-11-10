"""gunicorn settings for the web tier. Workers never run inside gunicorn: BACKGROUND_WORKERS=False in .env."""

import multiprocessing
import os

bind = os.environ.get('GUNICORN_BIND', '127.0.0.1:8000')
workers = int(os.environ.get('GUNICORN_WORKERS', max(2, min(4, multiprocessing.cpu_count()))))
threads = int(os.environ.get('GUNICORN_THREADS', 4))
worker_class = 'gthread'
timeout = int(os.environ.get('GUNICORN_TIMEOUT', 120))
graceful_timeout = 30
keepalive = 5
max_requests = 2000
max_requests_jitter = 200
# Log to stdout/stderr; systemd keeps them in the journal. The app's own LOG_FILE has the application log.
accesslog = '-'
errorlog = '-'
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %({x-request-id}o)s %(L)s'
forwarded_allow_ips = os.environ.get('GUNICORN_FORWARDED_ALLOW_IPS', '127.0.0.1')
