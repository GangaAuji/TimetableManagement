"""Academic lookups."""

from flask import Blueprint, request, redirect, url_for, flash, jsonify
from ui.pages import render_template
from security import has_permission
from services.academic_lookups import (
    batches_for_course,
    courses_for_department,
    faculty_for_department,
    semesters_for_year,
    subjects_for_course,
)

from routes.academic.blueprint import academic_bp

@academic_bp.route('/api/courses/by-department/<int:department_id>')
@has_permission('courses_view_course')
def api_courses_by_department(department_id):
    """Get courses for a department"""
    return jsonify(courses_for_department(department_id))


@academic_bp.route('/api/subjects/by-course/<int:course_id>')
@has_permission('subjects_view_subject')
def api_subjects_by_course(course_id):
    """Get subjects for a course"""
    return jsonify(subjects_for_course(course_id))


@academic_bp.route('/api/faculty/by-department/<int:department_id>')
@has_permission('faculty_view_faculty')
def api_faculty_by_department(department_id):
    """Get faculty for a department"""
    return jsonify(faculty_for_department(department_id))


@academic_bp.route('/api/semesters/by-year/<int:academic_year_id>')
@has_permission('semesters_view')
def api_semesters_by_year(academic_year_id):
    """Get semesters for an academic year"""
    return jsonify(semesters_for_year(academic_year_id))


@academic_bp.route('/api/batches/by-course/<int:course_id>')
@has_permission('batches_view')
def api_batches_by_course(course_id):
    """Get batches for a course"""
    return jsonify(batches_for_course(course_id))
