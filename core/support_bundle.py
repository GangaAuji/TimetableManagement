"""A diagnosis archive for support. It is not a backup.

Secrets are removed before anything is written: database passwords, signing
keys, tokens, and the same values if they appear in the log tail.
"""

import json
import re
from datetime import datetime, timezone

_SECRET_NAME = re.compile(r'(password|secret|token|private|credential|api_key|_key)$', re.IGNORECASE)


def secret_name(name):
    """True when this setting's value must not leave the server."""
    return bool(_SECRET_NAME.search(str(name or '')))


def redact_env(mapping):
    """Copy of the environment with secret values replaced. Names are kept."""
    redacted = {}
    for name in sorted(mapping):
        if not isinstance(name, str):
            continue
        value = mapping[name]
        if secret_name(name):
            redacted[name] = ''
        elif value is None:
            redacted[name] = ''
        else:
            redacted[name] = str(value)
    return redacted


def scrub(text, secret_values):
    """Replace known secret values in a log excerpt. Short values are left, so redaction cannot eat ordinary words."""
    cleaned = text or ''
    for value in secret_values:
        if isinstance(value, str) and len(value) >= 8:
            cleaned = cleaned.replace(value, '[redacted]')
    return cleaned


def _log_tail(path, secret_values, limit=200):
    if not path:
        return ''
    try:
        with open(path, encoding='utf-8', errors='replace') as handle:
            lines = handle.readlines()[-limit:]
    except OSError:
        return ''
    return scrub(''.join(lines), secret_values)


def build_report(app, database='not checked'):
    """JSON-ready diagnosis. Call inside an application context. No secret values are included.

    ``database`` is the schema sentence already collected by the caller, so this function
    does not open a database connection of its own.
    """
    from core.license import evaluate
    from core.schema.status import head_revision

    config = app.config
    raw_env = {
        key: config.get(key)
        for key in (
            'FLASK_ENV', 'MYSQL_HOST', 'MYSQL_USER', 'MYSQL_DB', 'TENANT_REGISTRY_DB',
            'MYSQL_PASSWORD', 'SECRET_KEY', 'FACE_TEMPLATE_KEY', 'FACE_TEMPLATE_KEY_PREVIOUS',
            'SETTINGS_ENCRYPTION_KEY', 'SMTP_PASSWORD', 'SMTP_HOST', 'MOBILE_SYNC_API_KEY',
            'LICENSE_REQUIRED', 'LICENSE_FILE', 'BACKUP_DIR', 'LOG_FILE',
        )
    }
    secrets = [value for key, value in raw_env.items() if secret_name(key) and isinstance(value, str)]
    return {
        'generated_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'head_revision': head_revision(),
        'database': database,
        'license': evaluate(config),
        'environment': redact_env(raw_env),
        'log_tail': _log_tail(config.get('LOG_FILE'), secrets),
    }
