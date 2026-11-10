"""Coverage percentages and behind/ahead pace. No database."""

from decimal import Decimal

from services.syllabus import coverage_lines, pace_of, parse_hours, parse_planned


def _row(delivered, elapsed=4, total=10):
    units = [{'id': 1, 'unit_no': 1, 'title': 'Kinematics', 'planned_hours': Decimal('10')}]
    return coverage_lines(units, {1: delivered}, elapsed=elapsed, total=total)[0]


def test_hours_stay_on_the_half_hour_between_half_and_three():
    assert parse_hours('1.5') == Decimal('1.5')
    assert parse_hours(1) == Decimal('1.0')
    assert parse_hours(3) == Decimal('3.0')
    assert parse_hours('0.5') == Decimal('0.5')
    for rejected in (0, 0.3, 3.5, 4, -1, 'abc', True, None, ''):
        assert parse_hours(rejected) is None
    assert parse_planned('12.5') == Decimal('12.5')
    assert parse_planned('0.4') is None
    assert parse_planned(401) is None


def test_percent_is_delivered_over_planned_and_pace_uses_the_elapsed_weeks():
    behind = _row(Decimal('3'))
    assert behind['percent'] == Decimal('30.0')
    assert behind['expected_hours'] == Decimal('4.0')
    assert behind['pace'] == 'behind'

    assert _row(Decimal('4'))['pace'] == 'on_track'
    assert _row(Decimal('4.5'))['pace'] == 'on_track'
    assert _row(Decimal('3.5'))['pace'] == 'on_track'
    assert _row(Decimal('4.6'))['pace'] == 'ahead'

    idle = _row(Decimal('3'), elapsed=None, total=None)
    assert idle['pace'] == 'no_pace' and idle['expected_hours'] is None and idle['percent'] == Decimal('30.0')
    assert pace_of(Decimal('8'), Decimal('0'), 0, 8)[1] == 'on_track'
