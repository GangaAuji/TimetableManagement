"""Request ids, JSON log lines, and error alerts.

Every request gets a request id (the incoming X-Request-ID when the proxy
sets one, else a fresh one), echoed back in the X-Request-ID response header
and stamped on every log record written while the request runs, together
with the tenant slug. LOG_FORMAT=json turns each record into one JSON object
per line for a log shipper; text keeps the familiar format with the request
id appended.

ERROR and above can be forwarded: ALERT_WEBHOOK_URL receives a JSON POST
(Slack-style `text` plus the fields), ALERT_MAIL_TO receives a mail through
SMTP_*. Identical messages are sent once per ALERT_QUIET_SECONDS so a loop
does not become a flood. Sending happens on a thread; a failing sink is
reported once to stderr and never raises into the app.
"""

import json
import logging
import smtplib
import sys
import threading
import time
import traceback
import uuid
from datetime import datetime, timezone
from email.message import EmailMessage
from urllib import request as urlrequest

from flask import g, has_request_context, request

REQUEST_ID_HEADER = 'X-Request-ID'
_MAX_HEADER_ID = 128
_SKIP_RECORD_FIELDS = frozenset((
    'args', 'asctime', 'created', 'exc_info', 'exc_text', 'filename', 'funcName', 'levelname', 'levelno',
    'lineno', 'message', 'module', 'msecs', 'msg', 'name', 'pathname', 'process', 'processName',
    'relativeCreated', 'stack_info', 'thread', 'threadName', 'taskName', 'request_id', 'tenant',
))


def new_request_id():
    return uuid.uuid4().hex


def current_request_id():
    if has_request_context():
        return getattr(g, 'request_id', None)
    return None


def _incoming_request_id():
    value = (request.headers.get(REQUEST_ID_HEADER) or '').strip()
    if value and len(value) <= _MAX_HEADER_ID and value.isprintable():
        return value
    return None


def install_request_ids(app):
    @app.before_request
    def assign_request_id():
        g.request_id = _incoming_request_id() or new_request_id()

    @app.after_request
    def echo_request_id(response):
        request_id = getattr(g, 'request_id', None)
        if request_id:
            response.headers[REQUEST_ID_HEADER] = request_id
        return response


class ContextFilter(logging.Filter):
    """Adds request_id and tenant to every record (empty outside a request)."""

    def filter(self, record):
        record.request_id = getattr(record, 'request_id', None) or current_request_id() or '-'
        tenant = None
        if has_request_context():
            tenant = getattr(g, 'tenant_slug', None)
        record.tenant = getattr(record, 'tenant', None) or tenant or '-'
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record):
        payload = {
            'time': datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec='milliseconds'),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'request_id': getattr(record, 'request_id', '-'),
            'tenant': getattr(record, 'tenant', '-'),
            'process': record.process,
            'thread': record.threadName,
        }
        if record.exc_info:
            payload['exception'] = ''.join(traceback.format_exception(*record.exc_info)).rstrip()
        for key, value in record.__dict__.items():
            if key not in _SKIP_RECORD_FIELDS and not key.startswith('_') and key not in payload:
                try:
                    json.dumps(value)
                    payload[key] = value
                except (TypeError, ValueError):
                    payload[key] = repr(value)
        return json.dumps(payload, ensure_ascii=False)


TEXT_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - [%(request_id)s %(tenant)s] %(message)s'


def make_formatter(log_format):
    if (log_format or 'text').lower() == 'json':
        return JsonFormatter()
    return logging.Formatter(TEXT_FORMAT)


class AlertHandler(logging.Handler):
    """Forwards ERROR+ records to a webhook and/or mail, at most once per message per quiet period."""

    def __init__(self, webhook_url=None, mail_to=None, smtp=None, quiet_seconds=600, service='timetable'):
        super().__init__(level=logging.ERROR)
        self.webhook_url = webhook_url
        self.mail_to = [address.strip() for address in (mail_to or '').split(',') if address.strip()]
        self.smtp = smtp or {}
        self.quiet_seconds = max(0, int(quiet_seconds))
        self.service = service
        self._recent = {}
        self._lock = threading.Lock()
        self._sink_failed = set()

    def _should_send(self, key, now=None):
        moment = time.monotonic() if now is None else now
        with self._lock:
            last = self._recent.get(key)
            if last is not None and moment - last < self.quiet_seconds:
                return False
            self._recent[key] = moment
            if len(self._recent) > 500:
                stale = [k for k, stamp in self._recent.items() if moment - stamp >= self.quiet_seconds]
                for k in stale:
                    self._recent.pop(k, None)
        return True

    def payload_for(self, record):
        message = record.getMessage()
        payload = {
            'service': self.service,
            'level': record.levelname,
            'logger': record.name,
            'message': message,
            'request_id': getattr(record, 'request_id', '-'),
            'tenant': getattr(record, 'tenant', '-'),
            'time': datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec='seconds'),
        }
        if record.exc_info:
            payload['exception'] = ''.join(traceback.format_exception(*record.exc_info))[-4000:]
        payload['text'] = f"[{self.service}] {record.levelname} {record.name}: {message[:500]}"
        return payload

    def emit(self, record):
        try:
            key = (record.name, record.levelno, record.getMessage()[:200])
            if not self._should_send(key):
                return
            payload = self.payload_for(record)
        except Exception:
            self.handleError(record)
            return
        threading.Thread(target=self._deliver, args=(payload,), name='alert-delivery', daemon=True).start()

    def _deliver(self, payload):
        if self.webhook_url:
            self._try('webhook', self._post_webhook, payload)
        if self.mail_to and self.smtp.get('host'):
            self._try('mail', self._send_mail, payload)

    def _try(self, sink, action, payload):
        try:
            action(payload)
            self._sink_failed.discard(sink)
        except Exception as exc:
            if sink not in self._sink_failed:
                self._sink_failed.add(sink)
                print(f'Alert {sink} failed: {exc.__class__.__name__}: {exc}', file=sys.stderr)

    def _post_webhook(self, payload):
        body = json.dumps(payload).encode('utf-8')
        req = urlrequest.Request(
            self.webhook_url, data=body, method='POST', headers={'Content-Type': 'application/json'},
        )
        with urlrequest.urlopen(req, timeout=10):
            pass

    def _send_mail(self, payload):
        message = EmailMessage()
        message['Subject'] = payload['text'][:200]
        message['From'] = self.smtp.get('from') or self.smtp.get('user') or f'{self.service}@localhost'
        message['To'] = ', '.join(self.mail_to)
        lines = [f'{key}: {value}' for key, value in payload.items() if key not in ('text', 'exception')]
        if payload.get('exception'):
            lines += ['', payload['exception']]
        message.set_content('\n'.join(lines))
        with smtplib.SMTP(self.smtp['host'], int(self.smtp.get('port') or 587), timeout=15) as client:
            if self.smtp.get('starttls', True):
                client.starttls()
            if self.smtp.get('user'):
                client.login(self.smtp['user'], self.smtp.get('password') or '')
            client.send_message(message)


def alert_handler_from_config(config):
    """An AlertHandler for this config, or None when no sink is configured."""
    webhook = config.get('ALERT_WEBHOOK_URL')
    mail_to = config.get('ALERT_MAIL_TO')
    if not webhook and not (mail_to and config.get('SMTP_HOST')):
        return None
    smtp = {
        'host': config.get('SMTP_HOST'),
        'port': config.get('SMTP_PORT'),
        'user': config.get('SMTP_USER'),
        'password': config.get('SMTP_PASSWORD'),
        'from': config.get('SMTP_FROM'),
        'starttls': config.get('SMTP_STARTTLS', True),
    }
    return AlertHandler(
        webhook_url=webhook,
        mail_to=mail_to,
        smtp=smtp,
        quiet_seconds=config.get('ALERT_QUIET_SECONDS', 600),
        service=config.get('INSTITUTION_SHORT_NAME') or 'timetable',
    )
