"""Global errors keep today's JSON shape. Pages still go to the React app."""

from urllib.parse import urlparse

import pytest
from flask import abort

from app_factory import create_app
from core.exceptions import AppError, ForbiddenError, NotFoundError, UnavailableError

pytestmark = pytest.mark.live_db


@pytest.fixture(scope='module')
def client():
    app = create_app()
    app.config['PROPAGATE_EXCEPTIONS'] = False

    @app.route('/api/__phase5_forbidden')
    def forbidden_probe():
        abort(403)

    @app.route('/api/__phase5_unavailable')
    def unavailable_probe():
        abort(500)

    @app.route('/api/__phase5_unauthorized')
    def unauthorized_probe():
        abort(401)

    @app.route('/api/__phase5_not_found')
    def not_found_probe():
        raise NotFoundError()

    @app.route('/api/__phase5_custom')
    def custom_probe():
        raise UnavailableError('The room list could not be loaded.')

    @app.route('/api/__phase5_blocked')
    def blocked_probe():
        raise AppError('The request was blocked.', 403, 'forbidden')

    @app.route('/pages/__phase5_forbidden')
    def page_probe():
        raise ForbiddenError()

    @app.route('/api/__phase5_runtime')
    def runtime_probe():
        raise RuntimeError('db down')

    return app.test_client()


def test_unknown_api_path_keeps_the_json_shape(client):
    response = client.get('/api/this-page-is-not-registered')
    assert response.status_code == 404
    assert response.get_json() == {
        'success': False,
        'error': {'code': 'not_found', 'message': 'The page could not be loaded.'},
    }


def test_unknown_admin_api_path_keeps_the_json_shape(client):
    response = client.get('/admin/api/this-page-is-not-registered')
    assert response.status_code == 404
    assert response.get_json()['error']['code'] == 'not_found'


def test_unknown_mobile_path_keeps_the_api_json_shape(client):
    response = client.get('/mobile-sync/this-page-is-not-registered')
    assert response.status_code == 404
    assert response.get_json() == {
        'success': False,
        'error': {'code': 'not_found', 'message': 'The page could not be loaded.'},
    }


def test_unknown_page_still_redirects_to_the_react_app(client):
    response = client.get('/this-page-is-not-registered', follow_redirects=False)
    assert response.status_code == 302
    assert urlparse(response.headers['Location']).path == '/'


def test_forbidden_and_unavailable_keep_their_codes(client):
    forbidden = client.get('/api/__phase5_forbidden')
    unavailable = client.get('/api/__phase5_unavailable')
    assert forbidden.status_code == 403
    assert forbidden.get_json()['error'] == {
        'code': 'forbidden',
        'message': 'The page could not be loaded.',
    }
    assert unavailable.status_code == 500
    assert unavailable.get_json()['error']['code'] == 'unavailable'


def test_other_http_errors_stay_on_the_framework_response(client):
    response = client.get('/api/__phase5_unauthorized')
    assert response.status_code == 401
    assert response.get_json(silent=True) is None


def test_application_errors_use_the_same_json_shape(client):
    missing = client.get('/api/__phase5_not_found')
    custom = client.get('/api/__phase5_custom')
    blocked = client.get('/api/__phase5_blocked')
    assert missing.get_json()['error']['code'] == 'not_found'
    assert custom.status_code == 500
    assert custom.get_json() == {
        'success': False,
        'error': {'code': 'unavailable', 'message': 'The room list could not be loaded.'},
    }
    assert blocked.status_code == 403
    assert blocked.get_json()['error'] == {
        'code': 'forbidden',
        'message': 'The request was blocked.',
    }


def test_unexpected_exception_stays_unavailable(client):
    response = client.get('/api/__phase5_runtime')
    assert response.status_code == 500
    assert response.get_json() == {
        'success': False,
        'error': {'code': 'unavailable', 'message': 'The page could not be loaded.'},
    }
    assert 'db down' not in response.get_data(as_text=True)


def test_application_error_on_a_page_still_opens_the_react_app(client):
    response = client.get('/pages/__phase5_forbidden', follow_redirects=False)
    assert response.status_code == 302
    assert urlparse(response.headers['Location']).path == '/'
