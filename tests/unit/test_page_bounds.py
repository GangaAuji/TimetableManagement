"""page_bounds matches the previous offset and page-count formulas."""

import math
from decimal import Decimal

from core.pagination import page_bounds


def test_page_bounds_matches_previous_formulas():
    for total, per_page, page in ((0, 10, 1), (1, 10, 1), (10, 10, 1), (11, 10, 2), (25, 50, 1)):
        offset, pages = page_bounds(page, per_page, total)
        assert offset == (page - 1) * per_page
        assert pages == (math.ceil(total / per_page) if total else 0)
        assert pages == ((total + per_page - 1) // per_page if total else 0)

    assert page_bounds(1, 20, 0, minimum_pages=1) == (0, 1)
    assert page_bounds(1, 20, Decimal('0'), minimum_pages=1) == (0, 1)
    assert page_bounds(2, 10, Decimal('25')) == (10, 3)
