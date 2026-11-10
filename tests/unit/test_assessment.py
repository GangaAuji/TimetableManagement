"""CO/PO attainment against a worked example. No database."""

from decimal import Decimal

from services.assessment import attain, parse_import_csv, parse_mark, parse_max_marks, student_score
from services.assessment import AssessmentError


def _example():
    components = {
        1: {'max_marks': Decimal('20'), 'weight': Decimal('20')},
        2: {'max_marks': Decimal('10'), 'weight': Decimal('10')},
        3: {'max_marks': Decimal('20'), 'weight': Decimal('20')},
    }
    links = {10: [1, 2], 11: [2, 3]}
    po_links = {20: [(10, 3), (11, 1)]}
    marks = {
        (1, 1): Decimal('16'), (2, 1): Decimal('8'), (3, 1): Decimal('10'),
        (1, 2): Decimal('10'), (2, 2): Decimal('6'), (3, 2): Decimal('16'),
    }
    return attain(components, links, po_links, marks)


def test_worked_nba_example_sets_co_and_po_levels():
    result = _example()
    co1, co2 = result['outcomes'][10], result['outcomes'][11]
    assert co1['percent'] == Decimal('66.67')
    assert co1['level'] == 1 and co1['students'] == 2 and co1['above'] == 1
    assert co2['percent'] == Decimal('66.67')
    assert co2['level'] == 3 and co2['above'] == 2
    program = result['program_outcomes'][20]
    assert program['percent'] == Decimal('66.67') and program['level'] == 2 and program['outcomes'] == 2


def test_a_student_with_no_mark_is_left_out_and_zero_weights_count_equally():
    assert student_score([(None, Decimal('10'))]) is None
    assert student_score([(Decimal('80'), Decimal('0')), (Decimal('40'), Decimal('0'))]) == Decimal('60')
    result = attain(
        {1: {'max_marks': Decimal('10'), 'weight': Decimal('0')}},
        {7: [1]}, {}, {(1, 1): None, (1, 2): Decimal('8')},
    )
    assert result['outcomes'][7]['students'] == 1
    assert result['outcomes'][7]['percent'] == Decimal('80.00')
    assert result['outcomes'][7]['level'] == 3


def test_marks_stay_on_one_decimal_and_the_import_needs_both_columns():
    assert parse_max_marks('20') == Decimal('20.0')
    assert parse_max_marks('0.4') is None
    assert parse_mark('', Decimal('20')) is None
    assert parse_mark('16.5', Decimal('20')) == Decimal('16.5')
    try:
        parse_mark('16.25', Decimal('20'))
    except AssessmentError as exc:
        assert exc.code == 'assessment_marks_invalid'
    else:
        raise AssertionError('expected assessment_marks_invalid')
    rows = parse_import_csv('roll_number,marks\n12,16\n13,\n')
    assert rows == [{'roll_number': '12', 'marks': '16'}, {'roll_number': '13', 'marks': ''}]
    try:
        parse_import_csv('name,score\nA,1\n')
    except AssessmentError as exc:
        assert exc.code == 'assessment_import_invalid'
    else:
        raise AssertionError('expected assessment_import_invalid')
