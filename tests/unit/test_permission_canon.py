"""The permission canon matches the names the code checks. No database."""

import ast
import os
import re
from pathlib import Path

from seeders.data.permissions import PERMISSIONS
from seeders.data.roles import ROLE_DEFAULTS, ROLES

ROOT = Path(__file__).resolve().parents[2]
_SKIP_DIRS = {
    '.git', '__pycache__', '_deprecated', 'docs', 'frontend', 'legacy', 'migrations', 'node_modules',
    'seeders', 'sql', 'tests', 'venv', '.venv',
}
_CHECKERS = {
    'allowed', 'check_user_permission', 'has_permission', 'has_user_permission', 'permission_denied',
    'user_has_all_perms', 'user_has_any_perm', 'user_has_perm',
}
_TEMPLATE_CHECK = re.compile(r"""(?:has_user_permission|user_has_perm)\(\s*['"]([a-z_]+)['"]""")
_TS_NAME = re.compile(r"""['"]([a-z]+(?:_[a-z]+)+)['"]""")
PAGE_ACCESS = ROOT / 'frontend' / 'src' / 'app' / 'page-access.ts'

# Rows that exist on installed databases but no code checks. A new unchecked
# permission fails the canon test until it is wired into a check or added here.
UNENFORCED = frozenset({
    'attendance_view_reports', 'courses_manage_subjects', 'courses_view_subjects',
    'faculty_add_absence', 'faculty_approve_absence', 'faculty_approve_proxy', 'faculty_change_availability',
    'faculty_delete_absence', 'faculty_export_data', 'faculty_view_absence', 'faculty_view_availability',
    'faculty_view_timetable', 'invitations_create', 'invitations_resend', 'invitations_revoke', 'invitations_view',
    'roles_clone_role', 'rooms_export_utilization', 'rooms_view_schedule', 'students_export_data',
    'timetable_delete', 'timetable_export', 'timetable_view', 'timetable_view_conflicts',
})


def _files(suffixes):
    for root, dirs, files in os.walk(ROOT):
        dirs[:] = [name for name in dirs if name not in _SKIP_DIRS]
        for name in files:
            if name.endswith(suffixes):
                yield Path(root) / name


def _parse(path):
    try:
        return ast.parse(path.read_text(encoding='utf-8'))
    except (SyntaxError, UnicodeDecodeError):
        return None


def _called(call):
    func = call.func
    return func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else None


def _wrappers(trees):
    """Functions that pass their first parameter straight to a permission check."""
    checkers = set(_CHECKERS)
    while True:
        found = set()
        for tree in trees:
            for function in ast.walk(tree):
                if not isinstance(function, ast.FunctionDef) or not function.args.args:
                    continue
                parameter = function.args.args[0].arg
                for call in ast.walk(function):
                    if (isinstance(call, ast.Call) and _called(call) in checkers and call.args
                            and isinstance(call.args[0], ast.Name) and call.args[0].id == parameter):
                        found.add(function.name)
        if found <= checkers:
            return checkers
        checkers |= found


def _strings(node, local, tables):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        yield node.value
    elif isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        for element in node.elts:
            yield from _strings(element, local, tables)
    elif isinstance(node, ast.Name):
        yield from local.get(node.id, ())
    elif isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
        yield from tables.get(node.value.id, ())


def _assigned_strings(scope):
    values = {}
    for node in ast.walk(scope):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    values.setdefault(target.id, set()).add(node.value.value)
    return values


def _string_tables(tree):
    tables = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict):
            values = [value.value for value in node.value.values if isinstance(value, ast.Constant)]
            if values and all(isinstance(value, str) for value in values):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        tables[target.id] = values
    return tables


def checked_names():
    trees = [tree for tree in map(_parse, _files(('.py',))) if tree is not None]
    checkers = _wrappers(trees)
    names = set()
    for tree in trees:
        tables = _string_tables(tree)
        for scope in [tree] + [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]:
            local = _assigned_strings(scope)
            for call in ast.walk(scope):
                if isinstance(call, ast.Call) and _called(call) in checkers and call.args:
                    names.update(_strings(call.args[0], local, tables))
    for path in _files(('.html', '.jinja', '.j2')):
        names.update(_TEMPLATE_CHECK.findall(path.read_text(encoding='utf-8', errors='replace')))
    names.update(_TS_NAME.findall(PAGE_ACCESS.read_text(encoding='utf-8')))
    return names


def test_canon_names_are_unique_and_complete():
    names = [permission.name for permission in PERMISSIONS]
    assert len(names) == len(set(names))
    assert all(name == name.lower() for name in names)
    assert all(permission.description and permission.group for permission in PERMISSIONS)
    assert all(isinstance(permission.since, int) and permission.since >= 1 for permission in PERMISSIONS)


def test_every_checked_name_is_in_the_canon_and_enforced():
    checked = checked_names()
    canon = {permission.name for permission in PERMISSIONS}
    assert checked - canon == set(), 'The code checks permissions the canon does not have.'
    enforced = {permission.name for permission in PERMISSIONS if permission.enforced}
    assert enforced - checked == set(), 'These permissions are marked enforced but no code checks them.'
    assert checked == enforced


def test_unenforced_permissions_are_exactly_the_allowlist():
    unenforced = {permission.name for permission in PERMISSIONS if not permission.enforced}
    assert unenforced == UNENFORCED
    assert UNENFORCED.isdisjoint(checked_names())


def test_role_defaults_use_canon_names_and_known_roles():
    canon = {permission.name for permission in PERMISSIONS}
    assert [role.name for role in ROLES] == ['Super Admin', 'Admin', 'HOD', 'Teacher', 'Student']
    assert [role.level for role in ROLES] == [1, 2, 3, 4, 5]
    assert set(ROLE_DEFAULTS) == {role.name for role in ROLES}
    for grants in ROLE_DEFAULTS.values():
        assert set(grants) <= canon
    counts = {role: len(grants) for role, grants in ROLE_DEFAULTS.items()}
    assert counts == {'Super Admin': len(PERMISSIONS), 'Admin': 79, 'HOD': 42, 'Teacher': 6, 'Student': 1}
    for role in ('Admin', 'HOD'):
        assert {'attendance_view_faculty'} <= set(ROLE_DEFAULTS[role])
    assert 'attendance_manage_faculty' in ROLE_DEFAULTS['Admin']
    assert {'students_delete_student', 'courses_delete_course', 'rooms_delete_room'}.isdisjoint(ROLE_DEFAULTS['Admin'])
