"""Academic catalog routes."""

from api.web.catalog.allocations import register_allocation_routes
from api.web.catalog.batches import register_batch_routes
from api.web.catalog.holidays import register_holiday_routes
from api.web.catalog.hub import register_hub_routes
from api.web.catalog.semesters import register_semester_routes
from api.web.catalog.subjects import register_subject_routes
from api.web.catalog.years import register_year_routes


def register_catalog_routes(blueprint):
    register_hub_routes(blueprint)
    register_year_routes(blueprint)
    register_semester_routes(blueprint)
    register_batch_routes(blueprint)
    register_subject_routes(blueprint)
    register_allocation_routes(blueprint)
    register_holiday_routes(blueprint)
