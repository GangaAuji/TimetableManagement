"""Smoke test: every registered GET route answers without a server error."""

from app import create_app
from tests.route_inventory import sample_path


def test_get_routes_do_not_return_500():
    app = create_app()
    app.config['PROPAGATE_EXCEPTIONS'] = False
    client = app.test_client()
    failures = []
    api_gets = []
    mobile_gets = []

    for rule in app.url_map.iter_rules():
        if 'GET' not in (rule.methods or ()) or rule.endpoint == 'static':
            continue
        path = sample_path(rule)
        if path == '/api' or path.startswith('/api/'):
            api_gets.append(path)
        if path == '/mobile-sync/v1' or path.startswith('/mobile-sync/v1/'):
            mobile_gets.append(path)
        try:
            response = client.get(path, follow_redirects=False)
        except Exception as error:
            failures.append(f'{path} raised {type(error).__name__}')
            continue
        if response.status_code >= 500:
            failures.append(f'{path} {response.status_code}')

    assert api_gets, 'No /api GET routes are registered'
    assert mobile_gets, 'No /mobile-sync/v1 GET routes are registered'
    assert not failures, 'GET routes returned a server error:\n' + '\n'.join(failures)
