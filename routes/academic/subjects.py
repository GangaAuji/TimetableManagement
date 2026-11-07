"""Academic subjects."""

from flask import Blueprint, request, redirect, url_for, flash, jsonify
from ui.pages import render_template
from security import has_permission
from services.subjects import (
    change_subject,
    create_subject,
    list_subjects,
    remove_subject,
)

from routes.academic.blueprint import academic_bp

@academic_bp.route('/subjects')
@has_permission('subjects_view_subject')
def manage_subjects():
    """Display Subjects Management Page with class-based filtering"""
    filter_class_id = request.args.get('class_id', type=int)
    filter_course_id = request.args.get('course_id', type=int)
    subjects, courses, classes, semesters = list_subjects(filter_class_id, filter_course_id)
    return render_template('legacy/admin/manage_subjects.html',
                         subjects=subjects,
                         courses=courses,
                         classes=classes,
                         semesters=semesters,
                         filter_class_id=filter_class_id,
                         filter_course_id=filter_course_id)


@academic_bp.route('/subjects/add', methods=['POST'])
@has_permission('subjects_add_subject')
def add_subject():
    """Add new subject"""
    name = request.form.get('name')
    course_code = request.form.get('course_code')
    course_id = request.form.get('course_id')
    class_id = request.form.get('class_id') or None
    semester_id = request.form.get('semester_id') or None
    course_type = request.form.get('course_type', 'Core')
    theory_practical = request.form.get('theory_practical', 'Theory')
    credits = float(request.form.get('credits', 3.0))
    theory_credits = float(request.form.get('theory_credits', 0))
    practical_credits = float(request.form.get('practical_credits', 0))
    marks = int(request.form.get('marks', 100))
    theory_marks = int(request.form.get('theory_marks', 0))
    practical_marks = int(request.form.get('practical_marks', 0))
    lectures_per_week = int(request.form.get('lectures_per_week', 3))
    practical_hours_per_week = int(request.form.get('practical_hours_per_week', 0))
    is_elective = 1 if request.form.get('is_elective') else 0
    description = request.form.get('description', '')
    syllabus_url = request.form.get('syllabus_url', '')
    error = create_subject(
        name, course_code, course_id, class_id, semester_id, course_type, theory_practical,
        credits, theory_credits, practical_credits, marks, theory_marks, practical_marks,
        lectures_per_week, practical_hours_per_week, is_elective, description, syllabus_url,
    )
    if error:
        flash(f'Error adding subject: {error}', 'danger')
    else:
        flash(f'Subject {name} added successfully!', 'success')
    return redirect(url_for('academic.manage_subjects'))


@academic_bp.route('/subjects/edit/<int:id>', methods=['POST'])
@has_permission('subjects_change_subject')
def edit_subject(id):
    """Edit subject"""
    name = request.form.get('name')
    course_code = request.form.get('course_code')
    course_id = request.form.get('course_id')
    class_id = request.form.get('class_id') or None
    semester_id = request.form.get('semester_id') or None
    course_type = request.form.get('course_type')
    theory_practical = request.form.get('theory_practical')
    credits = float(request.form.get('credits'))
    theory_credits = float(request.form.get('theory_credits'))
    practical_credits = float(request.form.get('practical_credits'))
    marks = int(request.form.get('marks'))
    theory_marks = int(request.form.get('theory_marks'))
    practical_marks = int(request.form.get('practical_marks'))
    lectures_per_week = int(request.form.get('lectures_per_week'))
    practical_hours_per_week = int(request.form.get('practical_hours_per_week'))
    is_elective = 1 if request.form.get('is_elective') else 0
    description = request.form.get('description', '')
    syllabus_url = request.form.get('syllabus_url', '')
    error = change_subject(
        id, name, course_code, course_id, class_id, semester_id, course_type, theory_practical,
        credits, theory_credits, practical_credits, marks, theory_marks, practical_marks,
        lectures_per_week, practical_hours_per_week, is_elective, description, syllabus_url,
    )
    if error:
        flash(f'Error updating subject: {error}', 'danger')
    else:
        flash(f'Subject {name} updated successfully!', 'success')
    return redirect(url_for('academic.manage_subjects'))


@academic_bp.route('/subjects/delete/<int:id>', methods=['POST'])
@has_permission('subjects_delete_subject')
def delete_subject(id):
    """Delete subject"""
    error = remove_subject(id)
    if error:
        flash(f'Error deleting subject: {error}', 'danger')
    else:
        flash('Subject deleted successfully!', 'success')
    return redirect(url_for('academic.manage_subjects'))
