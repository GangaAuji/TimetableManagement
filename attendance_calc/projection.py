"""Classes needed, classes that can be missed, and whether a threshold is still reachable."""

from decimal import Decimal
from fractions import Fraction


def _fraction(value) -> Fraction:
    if isinstance(value, Fraction):
        return value
    if isinstance(value, Decimal):
        return Fraction(value)
    return Fraction(str(value))


def _check(attended, countable, threshold):
    if attended < 0 or countable < 0 or attended > countable:
        raise ValueError('attended must be between 0 and countable')
    threshold = _fraction(threshold)
    if not 0 < threshold <= 100:
        raise ValueError('threshold must be above 0 and at most 100')
    return threshold


def meets(attended: int, countable: int, threshold) -> bool:
    """Return whether attended / countable reaches the threshold. Nothing countable never meets it."""
    threshold = _check(attended, countable, threshold)
    if countable == 0:
        return False
    return Fraction(attended * 100, countable) >= threshold


def classes_needed(attended: int, countable: int, threshold) -> int | None:
    """Smallest n >= 0 with (attended + n) / (countable + n) >= threshold / 100.

    None when no number of attended classes can reach it (threshold 100 with an
    absence already recorded). For 75 %: max(0, 3 * countable - 4 * attended).
    """
    threshold = _check(attended, countable, threshold)
    if countable and Fraction(attended * 100, countable) >= threshold:
        return 0
    if threshold == 100:
        return 0 if attended == countable else None
    needed = (threshold * countable - 100 * attended) / (100 - threshold)
    return max(0, -(-needed.numerator // needed.denominator))


def classes_that_can_be_missed(attended: int, countable: int, threshold) -> int:
    """Largest n >= 0 with attended / (countable + n) >= threshold / 100: floor(100a/T - c)."""
    threshold = _check(attended, countable, threshold)
    if countable == 0 or Fraction(attended * 100, countable) < threshold:
        return 0
    spare = Fraction(attended * 100) / threshold - countable
    return max(0, spare.numerator // spare.denominator)


def can_still_reach(attended: int, countable: int, threshold, remaining: int | None) -> bool | None:
    """Whether attending every one of `remaining` future classes reaches the threshold. None when remaining is unknown."""
    threshold = _check(attended, countable, threshold)
    if remaining is None:
        return None
    if remaining < 0:
        raise ValueError('remaining must be 0 or more')
    total = countable + remaining
    if total == 0:
        return False
    return Fraction((attended + remaining) * 100, total) >= threshold
