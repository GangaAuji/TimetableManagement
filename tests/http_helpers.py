"""Requests the way the browser makes them: same cookie jar, a CSRF token, and a same-origin header."""

SAME_ORIGIN = 'http://localhost'
ADMIN_FORM_ROLES = frozenset({'Admin', 'Super Admin'})


def csrf_token(client):
    """GET /api/csrf-token with this client's cookie jar and return the token."""
    response = client.get('/api/csrf-token')
    assert response.status_code == 200, response.get_data(as_text=True)[:200]
    return response.get_json()['data']['csrf_token']


def api(client, method, path, json=None, data=None, token=True):
    """Call a JSON API route with the CSRF header and a same-origin Origin header."""
    headers = {'Origin': SAME_ORIGIN}
    if token and method.upper() not in ('GET', 'HEAD'):
        headers['X-CSRFToken'] = csrf_token(client)
    return client.open(path, method=method.upper(), json=json, data=data, headers=headers)


def form_post(client, path, data):
    """POST a server-rendered form with its csrf_token field."""
    return client.post(path, data={**data, 'csrf_token': csrf_token(client)}, headers={'Origin': SAME_ORIGIN})


def login(client, user, path=None, password=None):
    """Sign in through the form the role normally uses. Returns the response."""
    if path is None:
        path = '/admin/login' if user['role'] in ADMIN_FORM_ROLES else '/login'
    return form_post(client, path, {'username': user['username'], 'password': password or user['password']})


def signed_in_as(client):
    """The account GET /api/session reports, or None."""
    payload = client.get('/api/session').get_json()['data']
    return payload if payload.get('authenticated') else None
