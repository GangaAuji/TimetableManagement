"""Academic home."""

from flask import Blueprint, request, redirect, url_for, flash, jsonify
from ui.pages import render_template
from routes.admin_utils import admin_required
from services.academic_home import academic_home

from routes.academic.blueprint import academic_bp

@academic_bp.route('/manage_academics')
@admin_required
def manage_academics():
    """Academic Management Dashboard"""
    (
        academic_years_count,
        semesters_count,
        courses_count,
        subjects_count,
        batches_count,
        allocations_count,
        departments_count,
        current_year,
        current_semester,
    ) = academic_home()
    return render_template('legacy/admin/academic.html',
                         academic_years_count=academic_years_count,
                         semesters_count=semesters_count,
                         courses_count=courses_count,
                         subjects_count=subjects_count,
                         batches_count=batches_count,
                         allocations_count=allocations_count,
                         departments_count=departments_count,
                         current_year=current_year,
                         current_semester=current_semester)
