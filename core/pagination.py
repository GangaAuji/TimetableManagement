"""Page offset and page count. Callers keep their own queries and page size."""


def bounded_page_size(raw, default=25, low=10, high=100) -> int:
    """Keep a requested page size inside the range the tables use."""
    text = '' if raw is None else str(raw).strip()
    if text.isdigit():
        return min(high, max(low, int(text)))
    return default


def page_bounds(page: int, per_page: int, total: int, *, minimum_pages: int = 0) -> tuple[int, int]:
    """Return the SQL offset and page count for a 1-based page."""
    count = int(total or 0)
    total_pages = (count + per_page - 1) // per_page if count else 0
    if total_pages < minimum_pages:
        total_pages = minimum_pages
    return (page - 1) * per_page, total_pages
