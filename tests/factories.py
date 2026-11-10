"""Rows for live_db tests: users of each role with their linked rows, and a small academic setup.

The app gives a faculty or student row the same id as its user, so the
factories do too. Every row is removed after the test by the isolation
fixture in tests/conftest.py.
"""

import itertools
from datetime import date, time

from security.passwords import hash_password

PASSWORD = 'Harness-Pass-1'
ROLES = ('Super Admin', 'Admin', 'HOD', 'Teacher', 'Student')
# 9 Nov 2026 is a Monday. Timetable days run Monday to Saturday only.
LECTURE_DAY = 'Monday'
LECTURE_DATE = date(2026, 11, 9)
_HASH = hash_password(PASSWORD)


class LectureDay(date):
    """A date whose today() is LECTURE_DATE, for code that only accepts marks on the lecture day."""

    @classmethod
    def today(cls):
        return LECTURE_DATE


class Factory:
    def __init__(self, connection):
        self.connection = connection
        self._numbers = itertools.count(1)

    def _next(self):
        return next(self._numbers)

    def insert(self, table, **values):
        cursor = self.connection.cursor()
        try:
            names = ', '.join(f'`{name}`' for name in values)
            marks = ', '.join(['%s'] * len(values))
            cursor.execute(f'INSERT INTO `{table}` ({names}) VALUES ({marks})', tuple(values.values()))
            self.connection.commit()
            return values.get('id') or cursor.lastrowid
        finally:
            cursor.close()

    def query(self, statement, params=()):
        cursor = self.connection.cursor(dictionary=True)
        try:
            cursor.execute(statement, params)
            rows = cursor.fetchall()
            self.connection.commit()
            return rows
        finally:
            cursor.close()

    def execute(self, statement, params=()):
        cursor = self.connection.cursor()
        try:
            cursor.execute(statement, params)
            self.connection.commit()
        finally:
            cursor.close()

    def department(self, name=None, *, institution_id=None):
        values = {'name': name or f'Department {self._next()}'}
        if institution_id is not None:
            values['institution_id'] = institution_id
        return self.insert('departments', **values)

    def institution(self, name=None, *, code=None, active=True):
        """A second (or third) institution in the tenant. Institution 1 exists from revision 0014."""
        n = self._next()
        return self.insert(
            'institutions', organization_id=1, name=name or f'College {n}', code=code or f'COL{n}',
            is_active=1 if active else 0, sort_order=n,
        )

    def membership(self, user, institution_id, *, primary=True, department_id=None):
        return self.insert(
            'institution_memberships', user_id=user['id'], institution_id=institution_id, role=user['role'],
            department_id=department_id, is_primary=1 if primary else 0,
        )

    def share(self, resource_type, resource_id, institution_id, *, created_by=None):
        """List a room or faculty member to one more institution (sets sharing='listed' on the row)."""
        table = 'rooms' if resource_type == 'room' else 'faculty'
        self.execute(f"UPDATE {table} SET sharing = 'listed' WHERE id = %s", (resource_id,))
        return self.insert(
            'resource_shares', resource_type=resource_type, resource_id=resource_id,
            institution_id=institution_id, created_by=created_by,
        )

    def capability(self, name, enabled=True, settings=None):
        """Switch an optional feature on or off for the tenant (core/capabilities.py)."""
        import json

        self.execute(
            'INSERT INTO capabilities (capability, enabled, settings_json) VALUES (%s, %s, %s) '
            'ON DUPLICATE KEY UPDATE enabled = VALUES(enabled), settings_json = VALUES(settings_json)',
            (name, 1 if enabled else 0, json.dumps(settings or {})),
        )

    def academic(self, *, institution_id=None):
        """Department, course, class, division, subject, room, one teacher, and one Monday lecture.

        With `institution_id` the department and room belong to that institution
        (and so does everything that hangs off the department)."""
        n = self._next()
        department = self.department(f'Science {n}', institution_id=institution_id)
        course = self.insert('courses', name=f'B.Sc. {n}', code=f'BSC{n}', program='UG', department_id=department)
        class_id = self.insert('classes', name=f'FY {n}')
        division = self.insert('divisions', name=f'A{n}')
        subject = self.insert(
            'subjects', name=f'Physics {n}', course_code=f'PHY{n}', course_id=course, class_id=class_id,
            credits=3, theory_credits=3, practical_credits=0, marks=100, theory_marks=100, practical_marks=0,
        )
        room_values = {'room_number': f'R{n}', 'department_id': department}
        if institution_id is not None:
            room_values['institution_id'] = institution_id
        room = self.insert('rooms', **room_values)
        setup = {
            'department_id': department, 'course_id': course, 'class_id': class_id,
            'division_id': division, 'subject_id': subject, 'room_id': room,
            'institution_id': institution_id or 1,
        }
        setup['teacher'] = self.user('Teacher', setup=setup)
        setup['timetable_id'] = self.lecture(setup, setup['teacher'])
        return setup

    def lecture(self, setup, teacher, day=LECTURE_DAY, start=time(9, 0), end=time(10, 0)):
        return self.insert(
            'timetable',
            course_id=setup['course_id'], class_id=setup['class_id'], division_id=setup['division_id'],
            day_of_week=day, start_time=start, end_time=end, subject_id=setup['subject_id'],
            faculty_id=teacher['faculty_id'], room_id=setup['room_id'],
        )

    def lab_batches(self, setup, names=('A1', 'A2'), *, division=True, year_id=None, capacity=None):
        """Lab batch groups for the setup's cohort in one academic year. Returns {name: group id}; `setup['year_id']` is set."""
        if year_id is None:
            year_id = setup.get('year_id') or self.insert(
                'academic_years', name=f'LY{self._next()}', start_date='2026-01-01', end_date='2026-12-31',
            )
        setup['year_id'] = year_id
        return {
            name: self.insert(
                'lab_batch_groups', course_id=setup['course_id'], class_id=setup['class_id'],
                division_id=setup['division_id'] if division else None, academic_year_id=year_id, name=name, capacity=capacity,
            )
            for name in names
        }

    def enrol_in_batch(self, group_id, student, added_at='2026-01-01', ended_at=None):
        return self.insert('lab_batch_members', lab_batch_group_id=group_id, student_id=student['student_id'], added_at=added_at, ended_at=ended_at)

    def user(self, role, *, setup=None, status='active', link=True, department_id=None, password=None):
        """Create a user. Teacher and Student get their linked faculty or student row unless link=False."""
        if role not in ROLES:
            raise ValueError(role)
        n = self._next()
        username = f'{role.lower().replace(" ", "_")}_{n}'
        if role in ('Teacher', 'HOD') and department_id is None:
            department_id = (setup or {}).get('department_id') or self.department()
        user_id = self.insert(
            'users', username=username, password=hash_password(password) if password else _HASH, role=role,
            status=status, email=f'{username}@example.org', department_id=department_id,
            is_hod=1 if role == 'HOD' else 0,
        )
        user = {
            'id': user_id, 'username': username, 'password': password or PASSWORD, 'role': role,
            'department_id': department_id, 'faculty_id': None, 'student_id': None,
        }
        if link and role == 'Teacher':
            user['faculty_id'] = self.insert(
                'faculty', id=user_id, user_id=user_id, name=f'Teacher {n}', email=f'{username}@example.org',
                department_id=department_id, employee_id=f'EMP{n}',
            )
        if link and role == 'Student':
            setup = setup or self.academic()
            user['student_id'] = self.insert(
                'students', id=user_id, user_id=user_id, name=f'Student {n}', email=f'{username}@example.org',
                course_id=setup['course_id'], class_id=setup['class_id'], division_id=setup['division_id'],
                admission_id=f'ADM{n}', roll_number=str(n),
            )
        return user

    def users(self, setup=None):
        """One user of each role. Teacher and Student are linked to `setup`."""
        setup = setup or self.academic()
        return {role: self.user(role, setup=setup) for role in ROLES}

    def grant(self, user, permission_name):
        """Give one user a permission directly, the way the users screen does."""
        [permission] = self.query('SELECT id FROM permissions WHERE name = %s', (permission_name,))
        self.insert('user_permissions', user_id=user['id'], permission_id=permission['id'], granted_by=user['id'])

    def role_permissions(self, role):
        rows = self.query(
            'SELECT p.name FROM role_permissions rp JOIN roles r ON r.id = rp.role_id '
            'JOIN permissions p ON p.id = rp.permission_id WHERE r.name = %s', (role,),
        )
        return {row['name'] for row in rows}
