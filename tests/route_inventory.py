"""Read the live Flask URL map. Used by the route inventory and the GET smoke test."""

import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
METHOD_ORDER = ('GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD')


def sample_values(rule):
    values = {}
    for name, converter in rule._converters.items():
        kind = type(converter).__name__
        if kind == 'IntegerConverter':
            values[name] = 1
        elif kind == 'FloatConverter':
            values[name] = 1.0
        elif kind == 'UUIDConverter':
            values[name] = '00000000-0000-0000-0000-000000000000'
        elif kind == 'AnyConverter':
            items = getattr(converter, 'items', None) or ()
            values[name] = next(iter(items), 'sample')
        else:
            values[name] = 'sample'
    return values


def sample_path(rule):
    built = rule.build(sample_values(rule), append_unknown=False)
    if not built:
        return rule.rule
    path = built[1]
    if not path.startswith('/'):
        path = '/' + path
    return path


def view_file(app, endpoint):
    view = app.view_functions.get(endpoint)
    if view is None:
        return ''
    func = getattr(view, '__wrapped__', view)
    code = getattr(func, '__code__', None)
    if code is None:
        return getattr(func, '__module__', '')
    return os.path.relpath(code.co_filename, ROOT).replace('\\', '/')


def blueprint_name(app, endpoint):
    if '.' not in endpoint:
        return ''
    name = endpoint.split('.', 1)[0]
    if name in app.blueprints:
        return name
    return ''


def declared_methods(rule):
    methods = set(rule.methods or ())
    if 'GET' in methods:
        methods.discard('HEAD')
    methods.discard('OPTIONS')
    return tuple(sorted(methods, key=lambda name: (METHOD_ORDER.index(name) if name in METHOD_ORDER else 99, name)))


def route_rows(app):
    rows = []
    for rule in app.url_map.iter_rules():
        if rule.endpoint == 'static':
            continue
        file_name = view_file(app, rule.endpoint)
        blueprint = blueprint_name(app, rule.endpoint)
        for method in declared_methods(rule):
            rows.append((method, rule.rule, blueprint, file_name, rule.endpoint))
    rows.sort(key=lambda row: (row[1], METHOD_ORDER.index(row[0]) if row[0] in METHOD_ORDER else 99, row[4]))
    return rows


def get_targets(app):
    targets = []
    for rule in app.url_map.iter_rules():
        if 'GET' not in (rule.methods or ()):
            continue
        if rule.endpoint == 'static':
            continue
        targets.append((sample_path(rule), rule.endpoint))
    targets.sort()
    return targets


def render_inventory(rows):
    lines = [
        '# Route inventory',
        '',
        'Baseline Flask URL map for this branch. Regenerate with `python -m tests.route_inventory`.',
        '',
        'The React app calls `/api`. Mobile sync calls `/mobile-sync/v1`. No `/api/v1` routes are registered.',
        '',
        '| Method | URL | Blueprint | File |',
        '| --- | --- | --- | --- |',
    ]
    for method, url, blueprint, file_name, _endpoint in rows:
        lines.append(f'| {method} | `{url}` | {blueprint or "—"} | `{file_name}` |')
    lines.append('')
    return '\n'.join(lines)


def write_inventory(path=None):
    from app import create_app

    app = create_app()
    destination = path or os.path.join(ROOT, 'docs', 'route_inventory.md')
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    rows = route_rows(app)
    with open(destination, 'w', encoding='utf-8', newline='\n') as handle:
        handle.write(render_inventory(rows))
    return app, rows


if __name__ == '__main__':
    _app, rows = write_inventory()
    print(f'routes {len(rows)}')
