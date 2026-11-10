"""Academic catalog routes."""

from api.web.catalog.assessment import register_assessment_routes
from api.web.catalog.exams import register_exam_routes
from api.web.catalog.allocations import register_allocation_routes
from api.web.catalog.batches import register_batch_routes
from api.web.catalog.holidays import register_holiday_routes
from api.web.catalog.hub import register_hub_routes
from api.web.catalog.lab_batches import register_lab_batch_routes
from api.web.catalog.semesters import register_semester_routes
from api.web.catalog.subjects import register_subject_routes
from api.web.catalog.syllabus import register_syllabus_routes
from api.web.catalog.terms import register_term_routes
from api.web.catalog.years import register_year_routes


def register_catalog_routes(blueprint):
    register_hub_routes(blueprint)
    register_year_routes(blueprint)
    register_term_routes(blueprint)
    register_semester_routes(blueprint)
    register_batch_routes(blueprint)
    register_lab_batch_routes(blueprint)
    register_subject_routes(blueprint)
    register_syllabus_routes(blueprint)
    register_assessment_routes(blueprint)
    register_exam_routes(blueprint)
    register_allocation_routes(blueprint)
    register_holiday_routes(blueprint)
