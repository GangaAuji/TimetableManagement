"""Status pages hide the exception unless DEBUG is on. No database."""

from flask import Flask

from ui.errors import error_handlers_bp


def _client(debug):
    app = Flask(__name__)
    app.config['DEBUG'] = debug
    app.config['TESTING'] = True
    app.config['PROPAGATE_EXCEPTIONS'] = False
    app.register_blueprint(error_handlers_bp)

    @app.route('/boom')
    def boom():
        raise RuntimeError('db down')

    @app.route('/api/boom')
    def api_boom():
        raise RuntimeError('db down')

    return app.test_client()


def test_debug_off_hides_the_exception_on_the_page():
    page = _client(False).get('/boom')
    body = page.get_data(as_text=True)
    assert page.status_code == 500
    assert 'Something went wrong' in body
    assert 'db down' not in body
    assert '<pre>' not in body


def test_debug_on_shows_the_message_without_a_traceback():
    page = _client(True).get('/boom')
    body = page.get_data(as_text=True)
    assert page.status_code == 500
    assert 'RuntimeError: db down' in body
    assert 'Traceback' not in body


def test_debug_off_keeps_the_api_message_generic():
    response = _client(False).get('/api/boom')
    assert response.get_json()['error'] == {
        'code': 'unavailable',
        'message': 'The page could not be loaded.',
    }


def test_debug_on_puts_the_message_in_the_api_error():
    response = _client(True).get('/api/boom')
    assert response.status_code == 500
    assert response.get_json()['error']['code'] == 'unavailable'
    assert 'db down' in response.get_json()['error']['message']


def test_missing_page_is_a_404_without_a_framework_message():
    response = _client(False).get('/missing')
    body = response.get_data(as_text=True)
    assert response.status_code == 404
    assert 'Page not found' in body
    assert 'The requested URL' not in body
