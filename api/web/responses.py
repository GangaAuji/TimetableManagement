"""JSON envelope used by every /api response."""

from flask import jsonify


def json_ok(data, status=200):
    return jsonify({'success': True, 'data': data}), status


def json_error(message, status, code):
    return jsonify({'success': False, 'error': {'code': code, 'message': message}}), status
