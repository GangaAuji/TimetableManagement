"""Integrations screen: API keys for /api/v1, webhook endpoints and deliveries, OIDC SSO settings.

GET    /api/sso                                  public: is SSO on, and the button label (sign-in page)
GET    /api/integrations                         everything the screen shows
POST   /api/integrations/api-keys                create a key; the plaintext is in this response only
DELETE /api/integrations/api-keys/<id>           revoke
POST   /api/integrations/webhooks                create an endpoint; the signing secret is in this response only
PUT    /api/integrations/webhooks/<id>           change name, url, events, active; `rotate_secret` returns a new secret
DELETE /api/integrations/webhooks/<id>           delete the endpoint and its deliveries
GET    /api/integrations/webhooks/deliveries     recent deliveries (`endpoint_id` filters)
POST   /api/integrations/webhooks/deliveries/<id>/retry
PUT    /api/integrations/sso                     save SSO settings; `client_secret` sets a new one, `clear_secret` removes it
DELETE /api/integrations/sso/identities/<id>     unlink a provider subject from a user

Viewing needs admin_view_settings, changing needs admin_change_settings.
"""

from datetime import datetime

from flask import current_app, request, session

from api.web.access import InputError, allowed, body, close, flag, optional_text, permission_denied, reject_input, required_text
from api.web.responses import json_error, json_ok
from api.web.security import safe_count, safe_stamp, safe_text
from data_access import webhooks as webhook_rows
from extensions import get_db_connection
from security import log_activity
from services import api_keys, sso, webhooks
from services.api_keys import ApiKeyError
from services.sso import SsoError
from services.webhooks import WebhookError

_MESSAGES = {
    'integrations_unavailable': 'Integration settings could not be loaded.',
    'invalid_body': 'The request could not be accepted.',
    'api_key_name_invalid': 'Give the key a name of up to 100 characters.',
    'api_key_scopes_invalid': 'Choose at least one scope.',
    'api_key_expires_invalid': 'The expiry must be a future date.',
    'api_key_not_found': 'That API key does not exist.',
    'api_key_failed': 'The key could not be created. Try again.',
    'webhook_name_invalid': 'Give the endpoint a name of up to 100 characters.',
    'webhook_url_invalid': 'Enter an https:// URL.',
    'webhook_url_private': 'Webhook URLs must point at a public host.',
    'webhook_events_invalid': 'Choose at least one event.',
    'webhook_not_found': 'That webhook endpoint does not exist.',
    'webhook_delivery_not_found': 'That delivery is not failed, so it cannot be retried.',
    'sso_invalid': 'Check the SSO fields and try again.',
    'sso_issuer_invalid': 'The issuer must be an https:// URL.',
    'sso_incomplete': 'SSO needs an issuer, a client ID and a client secret before it can be enabled.',
    'sso_no_key': 'The client secret cannot be stored: no encryption key is configured on the server.',
    'sso_identity_not_found': 'That SSO link does not exist.',
}
_KEY_FIELDS = frozenset(('name', 'scopes', 'expires_at'))
_WEBHOOK_FIELDS = frozenset(('name', 'url', 'events', 'is_active', 'rotate_secret'))
_SSO_FIELDS = frozenset((*sso.SETTING_FIELDS, 'client_secret', 'clear_secret'))


def register_integration_routes(blueprint):
    blueprint.add_url_rule('/sso', 'sso_public', _sso_public, methods=['GET'])
    blueprint.add_url_rule('/integrations', 'integrations', _overview, methods=['GET'])
    blueprint.add_url_rule('/integrations/api-keys', 'integrations_key_create', _create_key, methods=['POST'])
    blueprint.add_url_rule('/integrations/api-keys/<int:key_id>', 'integrations_key_revoke', _revoke_key, methods=['DELETE'])
    blueprint.add_url_rule('/integrations/webhooks', 'integrations_webhook_create', _create_webhook, methods=['POST'])
    blueprint.add_url_rule('/integrations/webhooks/<int:endpoint_id>', 'integrations_webhook_update', _update_webhook, methods=['PUT'])
    blueprint.add_url_rule('/integrations/webhooks/<int:endpoint_id>', 'integrations_webhook_delete', _delete_webhook, methods=['DELETE'])
    blueprint.add_url_rule('/integrations/webhooks/deliveries', 'integrations_deliveries', _deliveries, methods=['GET'])
    blueprint.add_url_rule(
        '/integrations/webhooks/deliveries/<int:delivery_id>/retry', 'integrations_delivery_retry', _retry_delivery, methods=['POST']
    )
    blueprint.add_url_rule('/integrations/sso', 'integrations_sso_save', _save_sso, methods=['PUT'])
    blueprint.add_url_rule('/integrations/sso/identities/<int:identity_id>', 'integrations_sso_unlink', _unlink_identity, methods=['DELETE'])


def _view_denied():
    if allowed('integrations_view') or allowed('admin_view_settings'):
        return None
    return permission_denied('integrations_view', 'integrations_unavailable', _MESSAGES['integrations_unavailable'])


def _change_denied():
    if allowed('integrations_change') or allowed('admin_change_settings'):
        return None
    return permission_denied('integrations_change', 'integrations_unavailable', _MESSAGES['integrations_unavailable'])


def _key_row(row):
    return {
        'id': safe_count(row['id']), 'name': safe_text(row['name'], 100), 'prefix': safe_text(row['key_prefix'], 12),
        'scopes': list(api_keys.parse_scopes(row.get('scopes'))), 'created_at': safe_stamp(row.get('created_at')),
        'expires_at': safe_stamp(row.get('expires_at')), 'last_used_at': safe_stamp(row.get('last_used_at')),
        'revoked_at': safe_stamp(row.get('revoked_at')),
    }


def _endpoint_row(row):
    return {
        'id': safe_count(row['id']), 'name': safe_text(row['name'], 100), 'url': safe_text(row['url'], 500),
        'events': list(webhooks.parse_events(row.get('events'))), 'is_active': bool(row.get('is_active')),
        'created_at': safe_stamp(row.get('created_at')), 'last_delivery_at': safe_stamp(row.get('last_delivery_at')),
        'last_status': safe_text(row.get('last_status') or '', 20),
    }


def _delivery_row(row):
    return {
        'id': safe_count(row['id']), 'endpoint_id': safe_count(row['endpoint_id']), 'endpoint_name': safe_text(row.get('endpoint_name') or '', 100),
        'event': safe_text(row['event'], 60), 'delivery_key': safe_text(row['delivery_key'], 36), 'status': safe_text(row['status'], 20),
        'attempts': safe_count(row.get('attempts')), 'response_status': safe_count(row.get('response_status')) or None,
        'last_error': safe_text(row.get('last_error') or '', 200), 'created_at': safe_stamp(row.get('created_at')),
        'sent_at': safe_stamp(row.get('sent_at')),
    }


def _identity_row(row):
    return {
        'id': safe_count(row['id']), 'user_id': safe_count(row['user_id']), 'username': safe_text(row.get('username') or '', 50),
        'role': safe_text(row.get('role') or '', 50), 'issuer': safe_text(row.get('issuer') or '', 255), 'email': safe_text(row.get('email') or '', 190),
        'created_at': safe_stamp(row.get('created_at')), 'last_login_at': safe_stamp(row.get('last_login_at')),
    }


def _sso_settings(settings):
    return {
        'enabled': bool(settings.get('enabled')), 'provider': safe_text(settings.get('provider') or 'oidc', 20),
        'issuer': safe_text(settings.get('issuer') or '', 255), 'client_id': safe_text(settings.get('client_id') or '', 255),
        'allowed_domains': safe_text(settings.get('allowed_domains') or '', 500), 'link_by_email': bool(settings.get('link_by_email', True)),
        'button_label': safe_text(settings.get('button_label') or '', 60), 'has_client_secret': bool(settings.get('has_client_secret')),
        'updated_at': safe_stamp(settings.get('updated_at')),
    }


def _payload(cursor):
    base = current_app.config.get('SSO_REDIRECT_BASE_URL') or request.url_root.rstrip('/')
    return {
        'api_keys': [_key_row(row) for row in api_keys.list_keys(cursor)],
        'scopes': [{'name': name, 'description': description} for name, description in api_keys.SCOPES.items()],
        'webhooks': [_endpoint_row(row) for row in webhooks.list_endpoints(cursor)],
        'events': [{'name': name, 'description': description} for name, description in webhooks.EVENTS.items()],
        'webhook_status': webhooks.status(cursor),
        'sso': _sso_settings(sso.load_settings(cursor)),
        'sso_identities': [_identity_row(row) for row in sso.list_identities(cursor)],
        'sso_redirect_uri': f'{base}/auth/sso/callback',
        'providers': [{'name': name, 'label': spec['label'], 'issuer': spec['issuer']} for name, spec in sso.PROVIDERS.items()],
        'openapi_url': f'{request.url_root.rstrip("/")}/api/v1/openapi.json',
        'can_change': allowed('integrations_change') or allowed('admin_change_settings'),
    }


def _run(label, work, *, denied, writes=False):
    """Open a connection, run `work(cursor)` and return its response. Writes commit; failures roll back."""
    if denied:
        return denied
    connection = cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        response = work(cursor)
        if writes:
            connection.commit()
        return response
    except InputError as exc:
        if connection is not None and writes:
            connection.rollback()
        return reject_input(_MESSAGES, exc.code)
    except (ApiKeyError, WebhookError, SsoError) as exc:
        if connection is not None and writes:
            connection.rollback()
        return reject_input(_MESSAGES, exc.code)
    except RuntimeError:
        if connection is not None and writes:
            connection.rollback()
        return json_error(_MESSAGES['sso_no_key'], 400, 'sso_no_key')
    except Exception:
        if connection is not None and writes:
            connection.rollback()
        current_app.logger.exception('%s failed', label)
        return json_error(_MESSAGES['integrations_unavailable'], 500, 'integrations_unavailable')
    finally:
        close(cursor, connection)


def _sso_public():
    return _run('SSO public settings', lambda cursor: json_ok(sso.public_settings(cursor)), denied=None)


def _overview():
    return _run('Integrations overview', lambda cursor: json_ok(_payload(cursor)), denied=_view_denied())


def _expiry(value):
    if value in (None, ''):
        return None
    text = optional_text(value, 10, 'api_key_expires_invalid')
    try:
        moment = datetime.strptime(text, '%Y-%m-%d')
    except ValueError:
        raise InputError('api_key_expires_invalid')
    if moment <= datetime.utcnow():
        raise InputError('api_key_expires_invalid')
    return moment.replace(hour=23, minute=59, second=59)


def _create_key():
    def work(cursor):
        payload = body(_KEY_FIELDS)
        name = required_text(payload.get('name'), 100, 'api_key_name_invalid')
        scopes = payload.get('scopes')
        if not isinstance(scopes, list) or not all(isinstance(scope, str) for scope in scopes):
            raise InputError('api_key_scopes_invalid')
        key_id, plaintext = api_keys.create_key(
            cursor, name=name, scopes=scopes, created_by=session.get('user_id'), expires_at=_expiry(payload.get('expires_at'))
        )
        log_activity(
            session.get('user_id'), 'api_key_created', f'API key "{name}" created', entity_type='api_key', entity_id=key_id,
            new_values={'name': name, 'scopes': list(api_keys.parse_scopes(scopes))}, cursor=cursor,
        )
        return json_ok({'id': key_id, 'key': plaintext, **_payload(cursor)})
    return _run('API key create', work, denied=_change_denied(), writes=True)


def _revoke_key(key_id):
    def work(cursor):
        api_keys.revoke_key(cursor, key_id)
        log_activity(session.get('user_id'), 'api_key_revoked', f'API key {key_id} revoked', entity_type='api_key', entity_id=key_id, cursor=cursor)
        return json_ok({'revoked': True, **_payload(cursor)})
    return _run('API key revoke', work, denied=_change_denied(), writes=True)


def _webhook_fields(payload):
    name = required_text(payload.get('name'), 100, 'webhook_name_invalid')
    url = required_text(payload.get('url'), 500, 'webhook_url_invalid')
    events = payload.get('events')
    if not isinstance(events, list) or not all(isinstance(event, str) for event in events):
        raise InputError('webhook_events_invalid')
    return name, url, events


def _create_webhook():
    def work(cursor):
        payload = body(_WEBHOOK_FIELDS - {'is_active', 'rotate_secret'})
        name, url, events = _webhook_fields(payload)
        endpoint_id, secret = webhooks.create_endpoint(cursor, name=name, url=url, events=events, created_by=session.get('user_id'))
        log_activity(
            session.get('user_id'), 'webhook_created', f'Webhook "{name}" created', entity_type='webhook_endpoint', entity_id=endpoint_id,
            new_values={'name': name, 'url': url, 'events': list(webhooks.parse_events(events))}, cursor=cursor,
        )
        return json_ok({'id': endpoint_id, 'secret': secret, **_payload(cursor)})
    return _run('Webhook create', work, denied=_change_denied(), writes=True)


def _update_webhook(endpoint_id):
    def work(cursor):
        payload = body(_WEBHOOK_FIELDS)
        name, url, events = _webhook_fields(payload)
        is_active = flag(payload.get('is_active', True))
        rotate = flag(payload.get('rotate_secret', False))
        secret = webhooks.update_endpoint(cursor, endpoint_id, name=name, url=url, events=events, is_active=is_active, rotate_secret=rotate)
        log_activity(
            session.get('user_id'), 'webhook_changed', f'Webhook "{name}" changed', entity_type='webhook_endpoint', entity_id=endpoint_id,
            new_values={'name': name, 'url': url, 'events': list(webhooks.parse_events(events)), 'is_active': is_active, 'secret_rotated': rotate},
            cursor=cursor,
        )
        return json_ok({'saved': True, 'secret': secret, **_payload(cursor)})
    return _run('Webhook update', work, denied=_change_denied(), writes=True)


def _delete_webhook(endpoint_id):
    def work(cursor):
        webhooks.delete_endpoint(cursor, endpoint_id)
        log_activity(session.get('user_id'), 'webhook_deleted', f'Webhook {endpoint_id} deleted', entity_type='webhook_endpoint', entity_id=endpoint_id, cursor=cursor)
        return json_ok({'deleted': True, **_payload(cursor)})
    return _run('Webhook delete', work, denied=_change_denied(), writes=True)


def _deliveries():
    def work(cursor):
        endpoint_id = safe_count(request.args.get('endpoint_id')) or None
        rows = webhook_rows.recent_deliveries(cursor, endpoint_id=endpoint_id, limit=200) if webhook_rows.table_exists(cursor, webhooks.TABLE) else []
        return json_ok({'deliveries': [_delivery_row(row) for row in rows], 'status': webhooks.status(cursor)})
    return _run('Webhook deliveries', work, denied=_view_denied())


def _retry_delivery(delivery_id):
    def work(cursor):
        if not webhooks.retry_delivery(cursor, delivery_id):
            raise InputError('webhook_delivery_not_found')
        return json_ok({'queued': True, 'status': webhooks.status(cursor)})
    return _run('Webhook retry', work, denied=_change_denied(), writes=True)


def _save_sso():
    def work(cursor):
        payload = body(_SSO_FIELDS)
        values = {}
        for key in ('enabled', 'link_by_email'):
            if key in payload:
                values[key] = flag(payload[key])
        for key, limit in (('provider', 20), ('issuer', 255), ('client_id', 255), ('allowed_domains', 500), ('button_label', 60)):
            if key in payload:
                values[key] = optional_text(payload.get(key), limit, 'sso_invalid')
        secret = payload.get('client_secret')
        if secret is not None and (not isinstance(secret, str) or len(secret) > 500):
            raise InputError('sso_invalid')
        clear = flag(payload.get('clear_secret', False))
        sso.save_settings(cursor, values, session.get('user_id'), client_secret=(secret or None), clear_secret=clear)
        log_activity(
            session.get('user_id'), 'sso_settings_changed', 'SSO settings changed', entity_type='sso_settings', entity_id=1,
            new_values={**values, 'secret_changed': bool(secret or clear)}, cursor=cursor,
        )
        return json_ok({'saved': True, **_payload(cursor)})
    return _run('SSO settings save', work, denied=_change_denied(), writes=True)


def _unlink_identity(identity_id):
    def work(cursor):
        if not sso.unlink_identity(cursor, identity_id):
            raise InputError('sso_identity_not_found')
        log_activity(session.get('user_id'), 'sso_identity_unlinked', f'SSO identity {identity_id} unlinked', entity_type='sso_identity', entity_id=identity_id, cursor=cursor)
        return json_ok({'unlinked': True, **_payload(cursor)})
    return _run('SSO unlink', work, denied=_change_denied(), writes=True)
