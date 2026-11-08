"""services.attendance_calc helpers that need no database: threshold parsing, the policy, component mapping, row conversion."""

from datetime import date
from decimal import Decimal

from flask import Flask

from attendance_calc import PRACTICAL, THEORY
from services.attendance_calc import (
    DEFAULT_THRESHOLD,
    component_of,
    figures_dict,
    parse_threshold,
    percent_value,
    policy,
    threshold_setting,
    to_slot,
    to_student,
)
from attendance_calc.types import Figures


def test_parse_threshold_accepts_only_a_number_in_range():
    assert parse_threshold('75') == Decimal('75')
    assert parse_threshold(' 66.5 ') == Decimal('66.5')
    assert parse_threshold(100) == Decimal('100')
    for bad in (None, '', '0', '-5', '101', 'abc', True, 'NaN', 'Infinity'):
        assert parse_threshold(bad) is None, bad


def test_threshold_comes_from_the_app_config_with_a_default():
    assert threshold_setting() == DEFAULT_THRESHOLD   # no app context
    app = Flask('t')
    with app.app_context():
        assert threshold_setting() == DEFAULT_THRESHOLD
        app.config['ATTENDANCE_THRESHOLD_PERCENT'] = '80'
        assert threshold_setting() == Decimal('80') and policy().threshold == Decimal('80')
        assert policy('60').threshold == Decimal('60')      # a request parameter wins
        assert policy('bogus').threshold == Decimal('80')   # a bad one is ignored
        app.config['ATTENDANCE_THRESHOLD_PERCENT'] = '0'
        assert policy().threshold == DEFAULT_THRESHOLD      # a bad setting falls back


def test_component_from_theory_practical_then_course_type():
    assert component_of({'theory_practical': 'Theory', 'course_type': 'Core Practical'}) == THEORY
    assert component_of({'theory_practical': 'Practical', 'course_type': 'Core'}) == PRACTICAL
    assert component_of({'theory_practical': 'Both', 'course_type': 'Core Practical'}) == PRACTICAL
    assert component_of({'theory_practical': 'Both', 'course_type': 'Elective'}) == THEORY
    assert component_of({'theory_practical': None, 'course_type': None}) == THEORY


def test_rows_become_dataclasses():
    slot = to_slot({
        'id': 5, 'subject_id': 9, 'course_id': 1, 'class_id': 2, 'division_id': None, 'semester_id': None,
        'academic_year_id': None, 'faculty_user_id': 40, 'is_active': 0, 'is_elective': 1,
        'theory_practical': 'Practical', 'course_type': 'Elective Practical',
    })
    assert (slot.division_id, slot.is_active, slot.is_elective, slot.component) == (None, False, True, PRACTICAL)
    student = to_student(
        {'id': 3, 'course_id': 1, 'class_id': 2, 'division_id': 7, 'enrolled_from': date(2026, 3, 9), 'enrolled_to': None},
        [{'subject_id': 9, 'semester_id': 4, 'academic_year_id': 1}],
    )
    assert student.enrolled_from == date(2026, 3, 9) and (9, 4, 1) in student.chosen_subjects


def test_figures_dict_keeps_none_for_no_data():
    assert figures_dict(Figures())['percentage'] is None
    assert figures_dict(Figures(held=3, countable=3, attended=2, percentage=Decimal('66.67')))['percentage'] == 66.67
    assert percent_value(None) is None and percent_value(Decimal('75')) == 75.0
