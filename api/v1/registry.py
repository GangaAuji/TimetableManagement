"""Operation registry for /api/v1: one decorator records the route and what the OpenAPI document says about it.

Every public route is declared with `operation(...)`, so the document at
/api/v1/openapi.json is generated from the routes that exist rather than
maintained by hand. Parameters are described once and reused.
"""

from dataclasses import dataclass, field

VERSION = '1.0.0'

PARAMS = {
    'course_id': {'name': 'course_id', 'in': 'query', 'schema': {'type': 'integer', 'minimum': 1}, 'description': 'Limit to one course.'},
    'class_id': {'name': 'class_id', 'in': 'query', 'schema': {'type': 'integer', 'minimum': 1}, 'description': 'Limit to one class (year of study).'},
    'division_id': {'name': 'division_id', 'in': 'query', 'schema': {'type': 'integer', 'minimum': 1}, 'description': 'Limit to one division.'},
    'department_id': {'name': 'department_id', 'in': 'query', 'schema': {'type': 'integer', 'minimum': 1}, 'description': 'Limit to one department.'},
    'subject_id': {'name': 'subject_id', 'in': 'query', 'schema': {'type': 'integer', 'minimum': 1}, 'description': 'Limit to one subject.'},
    'subject_id_path': {'name': 'subject_id', 'in': 'path', 'required': True, 'schema': {'type': 'integer', 'minimum': 1}, 'description': 'The subject id from /subjects.'},
    'day': {'name': 'day', 'in': 'query', 'schema': {'type': 'string', 'enum': ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']}, 'description': 'Limit to one weekday.'},
    'from': {'name': 'from', 'in': 'query', 'schema': {'type': 'string', 'format': 'date'}, 'description': 'First date (inclusive), YYYY-MM-DD.'},
    'to': {'name': 'to', 'in': 'query', 'schema': {'type': 'string', 'format': 'date'}, 'description': 'Last date (inclusive), YYYY-MM-DD.'},
    'status': {'name': 'status', 'in': 'query', 'schema': {'type': 'string', 'enum': ['held', 'cancelled', 'not_marked']}, 'description': 'Limit to one session status.'},
    'threshold': {'name': 'threshold', 'in': 'query', 'schema': {'type': 'number', 'minimum': 1, 'maximum': 100}, 'description': 'Percentage below which a student is a defaulter. Defaults to the institution setting.'},
    'limit': {'name': 'limit', 'in': 'query', 'schema': {'type': 'integer', 'minimum': 1, 'maximum': 500, 'default': 100}, 'description': 'Page size.'},
    'offset': {'name': 'offset', 'in': 'query', 'schema': {'type': 'integer', 'minimum': 0, 'default': 0}, 'description': 'Rows to skip.'},
    'student_id': {'name': 'student_id', 'in': 'path', 'required': True, 'schema': {'type': 'integer', 'minimum': 1}, 'description': 'The student id from /students.'},
    'session_id': {'name': 'session_id', 'in': 'path', 'required': True, 'schema': {'type': 'integer', 'minimum': 1}, 'description': 'The lecture session id from /attendance/sessions.'},
}


@dataclass(frozen=True)
class Operation:
    path: str
    method: str
    scope: str | None
    summary: str
    description: str = ''
    params: tuple = ()
    tag: str = 'General'
    response: dict = field(default_factory=dict)
    paginated: bool = False
    deprecated: bool = False


_OPERATIONS = []


def operation(path, *, scope, summary, description='', params=(), tag='General', response=None, paginated=False, method='GET'):
    """Register a view as a public operation. The view is unchanged; the metadata feeds the OpenAPI document."""
    unknown = [name for name in params if name not in PARAMS]
    if unknown:
        raise ValueError(f'unknown parameter(s) {unknown}')

    def wrap(view):
        _OPERATIONS.append(Operation(
            path=path, method=method, scope=scope, summary=summary, description=description,
            params=tuple(params), tag=tag, response=response or {}, paginated=paginated,
        ))
        view.__operation__ = _OPERATIONS[-1]
        return view
    return wrap


def operations():
    return tuple(_OPERATIONS)


def _flask_to_openapi(path):
    """`/students/<int:student_id>` to `/students/{student_id}`."""
    out = []
    for part in path.split('/'):
        if part.startswith('<') and part.endswith('>'):
            name = part[1:-1].split(':', 1)[-1]
            out.append('{' + name + '}')
        else:
            out.append(part)
    return '/'.join(out)


ERROR_SCHEMA = {
    'type': 'object',
    'properties': {
        'success': {'type': 'boolean', 'enum': [False]},
        'error': {
            'type': 'object',
            'properties': {'code': {'type': 'string'}, 'message': {'type': 'string'}},
            'required': ['code', 'message'],
        },
    },
    'required': ['success', 'error'],
}


def _envelope(schema, paginated):
    properties = {'success': {'type': 'boolean', 'enum': [True]}, 'data': schema}
    if paginated:
        properties['page'] = {
            'type': 'object',
            'properties': {
                'limit': {'type': 'integer'}, 'offset': {'type': 'integer'}, 'count': {'type': 'integer'},
                'has_more': {'type': 'boolean'},
            },
        }
    return {'type': 'object', 'properties': properties, 'required': ['success', 'data']}


def openapi_document(server_url, scopes):
    """The OpenAPI 3.1 document for the registered operations."""
    paths = {}
    tags = {}
    for op in _OPERATIONS:
        path = _flask_to_openapi(op.path)
        entry = {
            'summary': op.summary,
            'description': op.description,
            'tags': [op.tag],
            'operationId': f"{op.method.lower()}_{path.strip('/').replace('/', '_').replace('{', '').replace('}', '')}",
            'parameters': [PARAMS[name] for name in op.params],
            'responses': {
                '200': {'description': 'OK', 'content': {'application/json': {'schema': _envelope(op.response or {'type': 'object'}, op.paginated)}}},
                '400': {'description': 'A parameter is invalid.', 'content': {'application/json': {'schema': ERROR_SCHEMA}}},
                '401': {'description': 'The key is missing, malformed, expired or revoked.', 'content': {'application/json': {'schema': ERROR_SCHEMA}}},
                '403': {'description': 'The key lacks the scope.', 'content': {'application/json': {'schema': ERROR_SCHEMA}}},
                '404': {'description': 'No such record.', 'content': {'application/json': {'schema': ERROR_SCHEMA}}},
                '429': {'description': 'Too many requests for this key.', 'content': {'application/json': {'schema': ERROR_SCHEMA}}},
            },
        }
        if op.scope:
            entry['security'] = [{'ApiKey': [op.scope]}]
            entry['x-required-scope'] = op.scope
        else:
            entry['security'] = []
        if op.deprecated:
            entry['deprecated'] = True
        paths.setdefault(path, {})[op.method.lower()] = entry
        tags.setdefault(op.tag, {'name': op.tag})
    return {
        'openapi': '3.1.0',
        'info': {
            'title': 'Timetable Management public API',
            'version': VERSION,
            'description': (
                'Read access to catalog, timetable, people and attendance data for one institution. '
                'Send the API key as `Authorization: Bearer ttk_...`. Every key has the scopes it was created with; '
                'a call to an operation outside those scopes is refused with 403. Dates are ISO 8601, times are HH:MM, '
                'and every response is `{"success": true, "data": ...}` or `{"success": false, "error": {"code", "message"}}`.'
            ),
        },
        'servers': [{'url': server_url}],
        'tags': sorted(tags.values(), key=lambda tag: tag['name']),
        'paths': dict(sorted(paths.items())),
        'components': {
            'securitySchemes': {
                'ApiKey': {
                    'type': 'http', 'scheme': 'bearer', 'bearerFormat': 'ttk_<prefix>_<secret>',
                    'description': 'Scopes: ' + '; '.join(f'`{name}` — {text}' for name, text in scopes.items()),
                },
            },
            'schemas': {'Error': ERROR_SCHEMA},
        },
    }
