from flask import session, redirect, url_for
from ui.pages import render_template
from .teacher import teacher_bp, teacher_required
from services.teacher_portal import load_my_classes

@teacher_bp.route('/my-classes')
@teacher_required
def my_classes():
    classes = load_my_classes(session.get('faculty_id'))
    if classes == 'missing':
        return redirect(url_for('auth.logout'))
    return render_template('teacher/my_classes.html', classes=classes)
