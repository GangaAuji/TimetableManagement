"""Request-window checks. These do not open a database connection."""

from security.rate_limit import allow


def test_window_blocks_the_next_hit_after_the_limit():
    bucket = 'test-window-blocks'
    assert allow(bucket, 2, 60, now=100) is True
    assert allow(bucket, 2, 60, now=101) is True
    assert allow(bucket, 2, 60, now=102) is False


def test_window_forgets_hits_that_aged_out():
    bucket = 'test-window-ages'
    assert allow(bucket, 1, 10, now=0) is True
    assert allow(bucket, 1, 10, now=5) is False
    assert allow(bucket, 1, 10, now=11) is True
