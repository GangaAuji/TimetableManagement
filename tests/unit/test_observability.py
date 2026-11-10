"""Request ids, JSON log lines, alert de-duplication, and the worker heartbeat file. No live database."""

import json
import logging

from flask import Flask

from core.observability import (
    REQUEST_ID_HEADER,
    AlertHandler,
    ContextFilter,
    JsonFormatter,
    alert_handler_from_config,
    install_request_ids,
    make_formatter,
)
from services import worker_process


def _app():
    app = Flask('observability-unit')
    install_request_ids(app)

    @app.route('/echo')
    def echo():
        from flask import g, jsonify

        return jsonify(request_id=g.request_id)

    return app


def test_request_id_is_generated_or_taken_from_the_proxy_and_echoed():
    client = _app().test_client()
    first = client.get('/echo')
    generated = first.headers[REQUEST_ID_HEADER]
    assert len(generated) == 32 and first.get_json()['request_id'] == generated

    second = client.get('/echo', headers={REQUEST_ID_HEADER: 'nginx-abc-123'})
    assert second.headers[REQUEST_ID_HEADER] == 'nginx-abc-123'
    assert second.get_json()['request_id'] == 'nginx-abc-123'

    bad = client.get('/echo', headers={REQUEST_ID_HEADER: 'x' * 300})
    assert bad.headers[REQUEST_ID_HEADER] != 'x' * 300


def test_json_formatter_includes_context_and_exception():
    app = _app()
    record = logging.LogRecord('tests.obs', logging.ERROR, __file__, 1, 'boom %s', ('here',), None)
    with app.test_request_context('/echo', headers={REQUEST_ID_HEADER: 'req-1'}):
        from flask import g

        g.request_id = 'req-1'
        g.tenant_slug = 'alpha'
        assert ContextFilter().filter(record) is True
    try:
        raise ValueError('bad value')
    except ValueError:
        import sys

        record.exc_info = sys.exc_info()
    line = JsonFormatter().format(record)
    payload = json.loads(line)
    assert payload['message'] == 'boom here'
    assert payload['request_id'] == 'req-1' and payload['tenant'] == 'alpha'
    assert payload['level'] == 'ERROR' and 'ValueError: bad value' in payload['exception']

    plain = logging.LogRecord('tests.obs', logging.INFO, __file__, 1, 'hello', (), None)
    ContextFilter().filter(plain)
    text = make_formatter('text').format(plain)
    assert text.endswith('[- -] hello')
    assert isinstance(make_formatter('json'), JsonFormatter)


def test_alert_handler_sends_once_per_quiet_period_and_only_errors():
    handler = AlertHandler(webhook_url='http://alerts.example/hook', quiet_seconds=600)
    # emit() starts a delivery thread; the pieces are checked directly so the test stays deterministic.
    record = logging.LogRecord('tests.obs', logging.ERROR, __file__, 1, 'disk full', (), None)
    ContextFilter().filter(record)
    key = ('tests.obs', logging.ERROR, 'disk full')
    assert handler._should_send(key, now=100) is True
    assert handler._should_send(key, now=400) is False
    assert handler._should_send(('tests.obs', logging.ERROR, 'other'), now=400) is True
    assert handler._should_send(key, now=800) is True
    payload = handler.payload_for(record)
    assert payload['text'].endswith('ERROR tests.obs: disk full') and payload['request_id'] == '-'
    assert handler.level == logging.ERROR

    assert alert_handler_from_config({'ALERT_WEBHOOK_URL': None, 'ALERT_MAIL_TO': None}) is None
    assert alert_handler_from_config({'ALERT_WEBHOOK_URL': None, 'ALERT_MAIL_TO': 'ops@example.test', 'SMTP_HOST': None}) is None
    configured = alert_handler_from_config({
        'ALERT_WEBHOOK_URL': None, 'ALERT_MAIL_TO': 'ops@example.test, two@example.test', 'SMTP_HOST': 'smtp.example',
        'SMTP_PORT': 25, 'INSTITUTION_SHORT_NAME': 'ABC',
    })
    assert configured.mail_to == ['ops@example.test', 'two@example.test'] and configured.service == 'ABC'


def test_log_file_records_errors_only(tmp_path):
    app = Flask('log-file-probe')
    app.config['LOG_FILE'] = str(tmp_path / 'app.log')
    app.config['LOG_LEVEL'] = 'DEBUG'
    app.config['LOG_FORMAT'] = 'text'
    root = logging.getLogger()
    previous_handlers = list(root.handlers)
    previous_level = root.level
    watched = ('mysql.connector', 'MySQLdb', 'werkzeug', 'app')
    previous_logger_levels = {name: logging.getLogger(name).level for name in watched}
    try:
        from app_factory import _configure_logging

        _configure_logging(app)
        logging.getLogger('mysql.connector').debug('Starting authorization phase')
        logging.getLogger('werkzeug').info('GET /health')
        logging.getLogger('app').error('disk full')
    finally:
        fresh = list(root.handlers)
        root.handlers.clear()
        for handler in fresh:
            handler.close()
        for handler in previous_handlers:
            root.addHandler(handler)
        root.setLevel(previous_level)
        for name, level in previous_logger_levels.items():
            logging.getLogger(name).setLevel(level)
    text = (tmp_path / 'app.log').read_text(encoding='utf-8')
    assert 'authorization' not in text
    assert 'GET /health' not in text
    assert 'disk full' in text


def test_heartbeat_file_round_trip_and_problems(tmp_path, monkeypatch):
    app = Flask('heartbeat-unit')
    app.config.update(WORKERS_HEARTBEAT_FILE=str(tmp_path / 'hb.json'), ATTENDANCE_CLOSE_DAY_HOUR=-1,
                      QUALITY_MODEL_RETRAIN_INTERVAL_MINUTES=0, WORKERS_STALE_SECONDS=180)
    assert worker_process.heartbeat_problem(app).startswith('No worker heartbeat')
    assert worker_process.read_heartbeat(app) is None

    # Other tests in the same process may have started real queue threads; pretend none are alive.
    monkeypatch.setattr(worker_process.threading, 'enumerate', lambda: [])
    written = worker_process.write_heartbeat(app, {'mode': 'serve'})
    assert set(written['threads']) == {'export-queue', 'timetable-queue', 'notification-outbox', 'webhook-outbox'}
    assert set(written['threads'].values()) == {False}
    problem = worker_process.heartbeat_problem(app)
    assert problem.startswith(
        'Worker thread(s) not running: export-queue, notification-outbox, timetable-queue, webhook-outbox'
    )

    app.config['NOTIFICATIONS_ENABLED'] = False
    app.config['WEBHOOKS_ENABLED'] = False
    assert set(worker_process.write_heartbeat(app, {'mode': 'serve'})['threads']) == {'export-queue', 'timetable-queue'}
    app.config['NOTIFICATIONS_ENABLED'] = True
    app.config['WEBHOOKS_ENABLED'] = True

    read = worker_process.read_heartbeat(app)
    assert read['worker_id'] == written['worker_id'] and read['age_seconds'] >= 0

    app.config['WORKERS_STALE_SECONDS'] = -1
    assert 'old' in worker_process.heartbeat_problem(app)

    once = worker_process.write_heartbeat(app, {'mode': 'once'})
    assert once['threads'] == {}
    app.config['WORKERS_STALE_SECONDS'] = 180
    assert worker_process.heartbeat_problem(app) is None

    default_app = Flask('heartbeat-default')
    default_app.config['LOG_FILE'] = str(tmp_path / 'logs' / 'app.log')
    assert worker_process.heartbeat_path(default_app) == str(tmp_path / 'logs' / 'workers.heartbeat')
