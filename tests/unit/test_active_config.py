"""Application code reads the active app's config, not the module-level Config.

create_app(config) selects settings per app; a module that imports Config
directly would ignore that choice (for example, a test database).
"""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP_DIRS = ('api', 'services', 'routes', 'security', 'core', 'data_access', 'utils', 'academic_rules', 'models',
            'ml_models', 'seeders')
ALLOWED = {
    'models/db.py',  # fallback outside an app context
}


def _imports_global_config(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in ('config', 'config.base'):
            if any(alias.name == 'Config' for alias in node.names):
                return node.lineno
    return None


def test_no_application_module_imports_the_global_config():
    offenders = []
    for top in APP_DIRS:
        for path in (ROOT / top).rglob('*.py'):
            relative = path.relative_to(ROOT).as_posix()
            if '__pycache__' in relative or relative in ALLOWED:
                continue
            line = _imports_global_config(ast.parse(path.read_text(encoding='utf-8')))
            if line:
                offenders.append(f'{relative}:{line}')
    assert not offenders, 'Read current_app.config instead of Config:\n' + '\n'.join(offenders)
