"""People APIs: students and faculty."""

from api.web.people.faculty import register_faculty_routes
from api.web.people.students import register_student_routes


def register_people_routes(blueprint):
    register_student_routes(blueprint)
    register_faculty_routes(blueprint)
