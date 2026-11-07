"""Academic screens."""

from routes.academic.blueprint import academic_bp
from routes.academic import allocations, batches, courses, departments, home, lookups, semesters, subjects, years

__all__ = ['academic_bp']
