"""OIDC single sign-on for staff (Google Workspace, Microsoft Entra ID, or any OpenID Connect provider).

The browser flow is the authorization code grant with PKCE:

    GET /auth/sso/start      -> `begin` stores state, nonce and code verifier in the Flask session and
                                redirects to the provider's authorization endpoint
    GET /auth/sso/callback   -> `complete` checks the state, exchanges the code at the token endpoint,
                                verifies the id_token (RS256 against the provider's JWKS, issuer,
                                audience, expiry, nonce), finds or links the user and opens a session

Who may sign in: a subject already in `sso_identities`, or (when `link_by_email` is on) the one active
non-student user whose account or faculty email equals the provider's *verified* email, restricted to
`allowed_domains` when set. Students never sign in through SSO; nothing is created for an unknown
email. The client secret is encrypted at rest like SMTP passwords.

Settings live in `sso_settings` (one row per tenant database). Discovery documents and JWKS are
cached in process for an hour. The HTTP calls go through `_get_json` / `_post_form` so tests can
replace them.
"""

import base64
import hashlib
import json
import secrets
import threading
import time
import uuid
from datetime import datetime, timedelta
from urllib.parse import urlencode

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from flask import current_app, has_app_context

from data_access import sso as rows
from data_access.login import fetch_faculty_links, fetch_user_profile, insert_user_session, update_last_login
from security import log_activity, log_login_attempt
from services.secrets_at_rest import decrypt_text, encrypt_text

PROVIDERS = {
    'google': {'label': 'Google Workspace', 'issuer': 'https://accounts.google.com', 'button': 'Sign in with Google'},
    'microsoft': {'label': 'Microsoft Entra ID', 'issuer': None, 'button': 'Sign in with Microsoft'},
    'oidc': {'label': 'OpenID Connect', 'issuer': None, 'button': 'Sign in with SSO'},
}
SETTING_FIELDS = ('enabled', 'provider', 'issuer', 'client_id', 'allowed_domains', 'link_by_email', 'button_label')
_DEFAULTS = {
    'enabled': False, 'provider': 'oidc', 'issuer': '', 'client_id': '', 'allowed_domains': '', 'link_by_email': True,
    'button_label': '',
}
CACHE_SECONDS = 3600
SESSION_KEY = 'sso_flow'
_cache = {}
_cache_lock = threading.Lock()


class SsoError(Exception):
    """A sign-in that must stop. `code` is shown to the user as a short message key; `detail` is logged."""

    def __init__(self, code, detail=None):
        super().__init__(code)
        self.code = code
        self.detail = detail


# Settings ---------------------------------------------------------------------

def load_settings(cursor):
    """The settings row with defaults applied and `has_client_secret` instead of the secret."""
    row = rows.fetch_settings(cursor) if rows.table_exists(cursor) else None
    settings = dict(_DEFAULTS)
    if row:
        for key in SETTING_FIELDS:
            if row.get(key) is not None:
                settings[key] = row[key]
        settings['enabled'] = bool(row.get('enabled'))
        settings['link_by_email'] = bool(row.get('link_by_email'))
        settings['has_client_secret'] = bool(row.get('client_secret_enc'))
        settings['updated_at'] = row.get('updated_at')
    else:
        settings['has_client_secret'] = False
        settings['updated_at'] = None
    return settings


def save_settings(cursor, values, user_id, *, client_secret=None, clear_secret=False):
    """Write the changed fields. A new `client_secret` is encrypted; `clear_secret` removes it."""
    clean = {}
    for key in SETTING_FIELDS:
        if key in values:
            clean[key] = values[key]
    if 'provider' in clean and clean['provider'] not in PROVIDERS:
        raise SsoError('sso_invalid')
    provider = clean.get('provider') or load_settings(cursor).get('provider') or 'oidc'
    if 'issuer' in clean:
        issuer = (clean['issuer'] or '').strip().rstrip('/')
        if not issuer and PROVIDERS[provider]['issuer']:
            issuer = PROVIDERS[provider]['issuer']
        if issuer and not issuer.startswith('https://'):
            raise SsoError('sso_issuer_invalid')
        clean['issuer'] = issuer or None
    if 'allowed_domains' in clean:
        domains = sorted({part.strip().lower().lstrip('@') for part in str(clean['allowed_domains'] or '').replace(',', ' ').split() if part.strip()})
        clean['allowed_domains'] = ' '.join(domains) or None
    for key in ('enabled', 'link_by_email'):
        if key in clean:
            clean[key] = 1 if clean[key] else 0
    for key in ('client_id', 'button_label'):
        if key in clean:
            clean[key] = (clean[key] or '').strip() or None
    if client_secret:
        clean['client_secret_enc'] = encrypt_text(client_secret)
    elif clear_secret:
        clean['client_secret_enc'] = None
    if clean.get('enabled'):
        merged = {**load_settings(cursor), **clean}
        has_secret = bool(clean.get('client_secret_enc')) if 'client_secret_enc' in clean else merged.get('has_client_secret')
        if not (merged.get('issuer') and merged.get('client_id') and has_secret):
            raise SsoError('sso_incomplete')
    if clean:
        rows.upsert_settings(cursor, clean, user_id)
    _cache.clear()


def public_settings(cursor):
    """What the sign-in page needs: whether SSO is on and what the button says."""
    try:
        settings = load_settings(cursor)
    except Exception:
        return {'enabled': False}
    if not settings.get('enabled'):
        return {'enabled': False}
    provider = settings.get('provider') or 'oidc'
    return {
        'enabled': True, 'provider': provider,
        'button_label': settings.get('button_label') or PROVIDERS.get(provider, PROVIDERS['oidc'])['button'],
    }


def list_identities(cursor):
    return rows.fetch_identities(cursor) if rows.table_exists(cursor, 'sso_identities') else []


def unlink_identity(cursor, identity_id):
    return rows.delete_identity(cursor, identity_id) == 1


# HTTP and discovery -----------------------------------------------------------

def _get_json(url, timeout=10):
    import requests

    response = requests.get(url, timeout=timeout, headers={'Accept': 'application/json'})
    response.raise_for_status()
    return response.json()


def _post_form(url, data, timeout=10):
    import requests

    response = requests.post(url, data=data, timeout=timeout, headers={'Accept': 'application/json'})
    payload = response.json() if response.content else {}
    if response.status_code >= 400:
        raise SsoError('sso_token_failed', f"{response.status_code} {payload.get('error')}: {payload.get('error_description')}")
    return payload


def _cached(key, loader):
    now = time.time()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and hit[0] > now:
            return hit[1]
    value = loader()
    with _cache_lock:
        _cache[key] = (now + CACHE_SECONDS, value)
    return value


def discover(issuer):
    """The provider's OpenID configuration (authorization, token and JWKS endpoints)."""
    def load():
        document = _get_json(issuer.rstrip('/') + '/.well-known/openid-configuration')
        for field in ('authorization_endpoint', 'token_endpoint', 'jwks_uri', 'issuer'):
            if not document.get(field):
                raise SsoError('sso_provider_unavailable', f'discovery document lacks {field}')
        return document
    return _cached(('discovery', issuer), load)


def jwks(uri, *, refresh=False):
    if refresh:
        with _cache_lock:
            _cache.pop(('jwks', uri), None)
    return _cached(('jwks', uri), lambda: _get_json(uri))


# Token verification ----------------------------------------------------------

def _b64url_decode(text):
    padding_needed = '=' * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding_needed)


def _b64url_uint(text):
    return int.from_bytes(_b64url_decode(text), 'big')


def _public_key(jwk):
    if jwk.get('kty') != 'RSA' or not jwk.get('n') or not jwk.get('e'):
        raise SsoError('sso_token_invalid', 'unsupported key type')
    return rsa.RSAPublicNumbers(_b64url_uint(jwk['e']), _b64url_uint(jwk['n'])).public_key()


def verify_id_token(token, keys, *, issuer, audience, nonce=None, now=None, leeway=60):
    """Decode and verify an RS256 id_token. Returns the claims. Raises SsoError on any failure."""
    try:
        header_part, payload_part, signature_part = token.split('.')
        header = json.loads(_b64url_decode(header_part))
        claims = json.loads(_b64url_decode(payload_part))
        signature = _b64url_decode(signature_part)
    except (ValueError, TypeError, AttributeError) as exc:
        raise SsoError('sso_token_invalid', 'malformed id_token') from exc
    if header.get('alg') != 'RS256':
        raise SsoError('sso_token_invalid', f"unsupported alg {header.get('alg')!r}")
    candidates = [key for key in keys.get('keys', []) if key.get('kid') == header.get('kid')] if header.get('kid') else list(keys.get('keys', []))
    if not candidates:
        raise SsoError('sso_token_invalid', 'no matching signing key')
    signed = f'{header_part}.{payload_part}'.encode('ascii')
    for jwk in candidates:
        try:
            _public_key(jwk).verify(signature, signed, padding.PKCS1v15(), hashes.SHA256())
            break
        except InvalidSignature:
            continue
    else:
        raise SsoError('sso_token_invalid', 'signature does not verify')
    moment = int(now if now is not None else time.time())
    issuers = {issuer, issuer.rstrip('/'), issuer.rstrip('/') + '/'}
    if claims.get('iss') not in issuers:
        raise SsoError('sso_token_invalid', f"issuer {claims.get('iss')!r} does not match")
    aud = claims.get('aud')
    audiences = aud if isinstance(aud, list) else [aud]
    if audience not in audiences:
        raise SsoError('sso_token_invalid', 'audience does not match')
    if len(audiences) > 1 and claims.get('azp') not in (None, audience):
        raise SsoError('sso_token_invalid', 'authorized party does not match')
    try:
        if int(claims.get('exp', 0)) + leeway < moment:
            raise SsoError('sso_token_invalid', 'id_token expired')
        if int(claims.get('iat', moment)) - leeway > moment:
            raise SsoError('sso_token_invalid', 'id_token issued in the future')
        if claims.get('nbf') is not None and int(claims['nbf']) - leeway > moment:
            raise SsoError('sso_token_invalid', 'id_token not yet valid')
    except (TypeError, ValueError) as exc:
        raise SsoError('sso_token_invalid', 'bad time claim') from exc
    if nonce is not None and claims.get('nonce') != nonce:
        raise SsoError('sso_token_invalid', 'nonce does not match')
    if not claims.get('sub'):
        raise SsoError('sso_token_invalid', 'no subject')
    return claims


# The flow ---------------------------------------------------------------------

def _ready(cursor):
    settings = load_settings(cursor)
    if not settings.get('enabled'):
        raise SsoError('sso_disabled')
    row = rows.fetch_settings(cursor)
    if not (settings.get('issuer') and settings.get('client_id') and row and row.get('client_secret_enc')):
        raise SsoError('sso_incomplete')
    return settings, row


def begin(cursor, flask_session, redirect_uri):
    """Store the flow state in the session and return the provider URL to redirect the browser to."""
    settings, _row = _ready(cursor)
    document = discover(settings['issuer'])
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode('ascii')).digest()).rstrip(b'=').decode('ascii')
    flow = {'state': secrets.token_urlsafe(32), 'nonce': secrets.token_urlsafe(32), 'verifier': verifier, 'started': int(time.time())}
    flask_session[SESSION_KEY] = flow
    query = {
        'response_type': 'code', 'client_id': settings['client_id'], 'redirect_uri': redirect_uri, 'scope': 'openid email profile',
        'state': flow['state'], 'nonce': flow['nonce'], 'code_challenge': challenge, 'code_challenge_method': 'S256',
    }
    if settings.get('allowed_domains') and settings.get('provider') == 'google' and ' ' not in settings['allowed_domains']:
        query['hd'] = settings['allowed_domains']
    return f"{document['authorization_endpoint']}?{urlencode(query)}"


def _email_allowed(email, allowed_domains):
    if not allowed_domains:
        return True
    domain = email.rsplit('@', 1)[-1].lower()
    return domain in set(allowed_domains.split())


def _resolve_user(cursor, settings, claims):
    """The user this verified identity signs in as, linking by email on first use when allowed."""
    issuer = settings['issuer']
    subject = str(claims['sub'])
    email = (claims.get('email') or '').strip().lower() or None
    identity = rows.fetch_identity(cursor, issuer, subject)
    if identity:
        user = rows.fetch_user(cursor, identity['user_id'])
        if not user:
            raise SsoError('sso_no_account', 'identity points at a deleted user')
        rows.touch_identity(cursor, identity['id'], email)
        return user, False
    if not settings.get('link_by_email'):
        raise SsoError('sso_no_account', 'subject unknown and linking by email is off')
    if not email or claims.get('email_verified') is False:
        raise SsoError('sso_email_unverified', 'the provider did not assert a verified email')
    if not _email_allowed(email, settings.get('allowed_domains')):
        raise SsoError('sso_domain_not_allowed', f'{email.rsplit("@", 1)[-1]} is not an allowed domain')
    user = rows.fetch_staff_user_by_email(cursor, email)
    if not user:
        raise SsoError('sso_no_account', f'no single staff account with email {email}')
    rows.insert_identity(cursor, user_id=user['id'], issuer=issuer, subject=subject, email=email)
    return user, True


def _open_session(cursor, user, flask_session, ip_address, user_agent):
    flask_session['user_id'] = user['id']
    flask_session['username'] = user['username']
    flask_session['role'] = user['role']
    session_id = str(uuid.uuid4())
    flask_session['session_id'] = session_id
    insert_user_session(cursor, session_id, user['id'], ip_address, user_agent, datetime.now() + timedelta(days=7))
    update_last_login(cursor, user['id'])
    from services.security_policy import apply_sign_in
    apply_sign_in(cursor, user, ip_address, flask_session, session_id)
    profile = fetch_user_profile(cursor, user['id'])
    flask_session['department_id'] = profile['department_id'] if profile else None
    flask_session['is_hod'] = bool(profile['is_hod']) if profile else False
    flask_session['profile_photo'] = (profile or {}).get('profile_photo') or 'default-avatar.svg'
    flask_session['name'] = user['username']
    if user['role'] == 'Teacher':
        links = fetch_faculty_links(cursor, user['id'])
        if len(links) != 1:
            raise SsoError('sso_no_account', 'teacher account is not linked to one faculty record')
        flask_session['faculty_id'] = links[0]['id']
        flask_session['name'] = links[0]['name']
        flask_session['email'] = links[0]['email']
        flask_session['department_id'] = links[0]['department_id']
    from core.scope import apply_at_login
    apply_at_login(cursor, flask_session)
    return session_id


def complete(cursor, flask_session, args, redirect_uri, *, ip_address=None, user_agent=None):
    """Finish the callback: verify everything, open the session. Returns the user row. Raises SsoError."""
    flow = flask_session.pop(SESSION_KEY, None)
    if not flow or not args.get('state') or not secrets.compare_digest(str(flow.get('state')), str(args.get('state'))):
        raise SsoError('sso_state_mismatch')
    if int(time.time()) - int(flow.get('started', 0)) > 600:
        raise SsoError('sso_state_mismatch', 'flow older than ten minutes')
    if args.get('error'):
        raise SsoError('sso_provider_denied', f"{args.get('error')}: {args.get('error_description')}")
    code = args.get('code')
    if not code:
        raise SsoError('sso_provider_denied', 'no code in callback')
    settings, row = _ready(cursor)
    document = discover(settings['issuer'])
    tokens = _post_form(document['token_endpoint'], {
        'grant_type': 'authorization_code', 'code': code, 'redirect_uri': redirect_uri, 'client_id': settings['client_id'],
        'client_secret': decrypt_text(row['client_secret_enc']), 'code_verifier': flow['verifier'],
    })
    id_token = tokens.get('id_token')
    if not id_token:
        raise SsoError('sso_token_failed', 'token response without id_token')
    try:
        claims = verify_id_token(id_token, jwks(document['jwks_uri']), issuer=document['issuer'], audience=settings['client_id'], nonce=flow['nonce'])
    except SsoError as exc:
        if exc.detail != 'no matching signing key':
            raise
        claims = verify_id_token(id_token, jwks(document['jwks_uri'], refresh=True), issuer=document['issuer'], audience=settings['client_id'], nonce=flow['nonce'])
    user, linked = _resolve_user(cursor, settings, claims)
    if user.get('status') == 'locked':
        log_login_attempt(user['username'], 'failed', 'Account locked', cursor=cursor)
        raise SsoError('sso_account_locked')
    if user.get('status') == 'inactive':
        log_login_attempt(user['username'], 'failed', 'Account inactive', cursor=cursor)
        raise SsoError('sso_account_inactive')
    if user.get('role') in ('Admin', 'Super Admin', 'HOD'):
        from services.security_policy import admin_ip_ok
        if not admin_ip_ok(cursor, ip_address):
            log_login_attempt(user['username'], 'failed', 'Network not allowed', cursor=cursor)
            raise SsoError('sso_network')
    from services.second_factor import remember, sso_prepare
    step = sso_prepare(cursor, user, claims)
    if step == 'failed':
        raise SsoError('sso_second_factor', 'enrollment could not be started')
    if step:
        remember(flask_session, user, user['username'], step, 'sso')
        return user
    _open_session(cursor, user, flask_session, ip_address, user_agent)
    log_login_attempt(user['username'], 'success', cursor=cursor)
    log_activity(
        user['id'], 'sso_login', f"User {user['username']} signed in with SSO ({settings.get('provider')})" + (' and was linked by email' if linked else ''),
        cursor=cursor,
    )
    return user


def landing_path(user):
    return '/admin' if user['role'] in ('Admin', 'Super Admin', 'HOD') else '/'


def log_failure(exc):
    if has_app_context():
        current_app.logger.warning('SSO sign-in stopped: %s%s', exc.code, f' ({exc.detail})' if exc.detail else '')
