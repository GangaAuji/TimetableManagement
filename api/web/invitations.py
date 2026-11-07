"""Invitation list. Tokens stay out of this response."""

import re
from datetime import datetime

from flask import current_app, request, session

from api.web.access import InputError, allowed, body, optional_id, page_window, permission_denied, reject_input, required_text
from api.web.responses import json_error, json_ok
from api.web.security import safe_count, safe_stamp, safe_text
from services.invitations import (
    create_registration_invitation,
    invitation_token,
    list_invitations,
    resend_registration_invitation,
    revoke_registration_invitation,
)
from services.registration import describe_invitation

_MESSAGES = {'invitations_unavailable': 'The page could not be loaded.'}
_STATUSES = frozenset(('', 'pending', 'used', 'expired'))
_TOKEN = re.compile(r'^[A-Za-z0-9_-]{16,200}$')


def register_invitation_routes(blueprint):
    blueprint.add_url_rule('/register/<token>', 'register_preview', _preview, methods=['GET'])
    blueprint.add_url_rule('/invitations', 'invitations_list', _list, methods=['GET'])
    blueprint.add_url_rule('/invitations', 'invitations_create', _create, methods=['POST'])
    blueprint.add_url_rule('/invitations/<int:invitation_id>/revoke', 'invitations_revoke', _revoke, methods=['POST'])
    blueprint.add_url_rule('/invitations/<int:invitation_id>/resend', 'invitations_resend', _resend, methods=['POST'])
    blueprint.add_url_rule('/invitations/<int:invitation_id>/link', 'invitations_link', _link, methods=['GET'])


def _page_query():
    page, per_page = page_window()
    search = safe_text(request.args.get('search') or '', 80)
    status = request.args.get('status') or ''
    if status not in _STATUSES:
        status = ''
    return page, per_page, search, status


def _invitation_columns():
    columns = {}
    for arg, key, limit in (
        ('name', 'name', 100),
        ('email', 'email', 160),
        ('role', 'role', 50),
        ('place', 'place', 100),
        ('status_text', 'status', 20),
        ('expires', 'expires_at', 19),
    ):
        text = safe_text(request.args.get(arg) or '', limit).replace('%', '').replace('_', '').strip()
        if text:
            columns[key] = text
    return columns or None


def _catalog(rows):
    return [
        {'id': safe_count(row.get('id')), 'name': safe_text(row.get('name'), 100)}
        for row in rows or []
        if safe_count(row.get('id')) > 0 and safe_text(row.get('name'), 100)
    ]


def _lapsed(expires):
    moment = expires
    if isinstance(expires, str):
        text = expires.strip()[:19]
        try:
            moment = datetime.strptime(text, '%Y-%m-%d %H:%M:%S')
        except ValueError:
            try:
                moment = datetime.strptime(text[:16], '%Y-%m-%d %H:%M')
            except ValueError:
                return False
    if not isinstance(moment, datetime):
        return False
    try:
        return moment <= datetime.now()
    except TypeError:
        return False


def _shown_status(row):
    status = safe_text(row.get('status'), 20)
    if status == 'pending' and _lapsed(row.get('expires_at')):
        return 'expired'
    return status


def _preview(token):
    if not _TOKEN.match(token or ''):
        return json_ok({'state': 'invalid'})
    try:
        state, invitation = describe_invitation(token)
        if state != 'open' or not invitation:
            return json_ok({'state': state if state in ('used', 'expired') else 'invalid'})
        return json_ok({
            'state': 'open',
            'name': safe_text(invitation.get('name'), 100),
            'role': safe_text(invitation.get('role'), 50),
        })
    except Exception:
        current_app.logger.exception('Registration preview failed')
        return json_error(_MESSAGES['invitations_unavailable'], 500, 'invitations_unavailable')


def _registration_link(token):
    if not isinstance(token, str) or not token or len(token) > 80 or any(char in token for char in ' \r\n\\'):
        return ''
    return '/register/' + token


def _list():
    denied = permission_denied('users_change_user', 'invitations_unavailable', _MESSAGES['invitations_unavailable'])
    if denied:
        return denied
    try:
        page, per_page, search, status = _page_query()
        page_data = list_invitations(page, search, status, per_page, _invitation_columns())
        invitations = [
            {
                'id': safe_count(row.get('id')),
                'email': safe_text(row.get('email'), 160),
                'name': safe_text(row.get('name'), 100),
                'role': safe_text(row.get('role'), 50),
                'status': _shown_status(row),
                'course_name': safe_text(row.get('course_name') or '', 100),
                'department_name': safe_text(row.get('dept_name') or '', 100),
                'created_by': safe_text(row.get('created_by_username') or '', 50),
                'created_at': safe_stamp(row.get('created_at')),
                'expires_at': safe_stamp(row.get('expires_at')),
                'used_at': safe_stamp(row.get('used_at')),
            }
            for row in page_data['invitations']
            if safe_count(row.get('id')) > 0
        ]
        stats = page_data['stats'] or {}
        return json_ok({
            'invitations': invitations,
            'courses': _catalog(page_data['courses']),
            'classes': _catalog(page_data['classes']),
            'divisions': _catalog(page_data['divisions']),
            'departments': _catalog(page_data['departments']),
            'stats': {
                'pending': safe_count(stats.get('pending')),
                'used': safe_count(stats.get('used')),
                'expired': safe_count(stats.get('expired')),
                'total': safe_count(stats.get('total')),
            },
            'page': page,
            'per_page': per_page,
            'total': safe_count(page_data.get('total')),
            'total_pages': max(safe_count(page_data['total_pages']), 1),
            'can_invite': allowed('users_add_user'),
            'can_change': allowed('users_change_user'),
        })
    except Exception:
        current_app.logger.exception('Invitation list failed')
        return json_error(_MESSAGES['invitations_unavailable'], 500, 'invitations_unavailable')


_INVITE_ROLES = frozenset(('Teacher', 'Student'))
_INVITE_MESSAGES = {
    'invalid_body': 'The request could not be accepted.',
    'invitations_unavailable': 'The invitation could not be created.',
    'invite_name_invalid': 'Enter a name up to 100 characters.',
    'invite_email_invalid': 'Enter a valid email address.',
    'invite_role_invalid': 'Choose Teacher or Student.',
    'invite_duplicate': 'A pending invitation already exists for this email.',
    'invite_registered': 'This email is already registered.',
    'invite_not_found': 'That invitation was not found.',
    'invite_used': 'A used invitation cannot be sent again.',
}


def _create():
    denied = permission_denied('users_add_user', 'invitations_unavailable', _INVITE_MESSAGES['invitations_unavailable'])
    if denied:
        return denied
    try:
        payload = body(frozenset(('name', 'email', 'role', 'days_valid', 'course_id', 'class_id', 'division_id', 'department_id')))
        name = required_text(payload.get('name'), 100, 'invite_name_invalid')
        email = required_text(payload.get('email'), 160, 'invite_email_invalid')
        if '@' not in email or email.startswith('@') or email.endswith('@'):
            raise InputError('invite_email_invalid')
        role = payload.get('role')
        if role not in _INVITE_ROLES:
            raise InputError('invite_role_invalid')
        days_valid = payload.get('days_valid', 7)
        days = safe_count(days_valid)
        if isinstance(days_valid, bool) or days < 1 or days > 90 or safe_text(days_valid, 2) != str(days):
            raise InputError('invalid_body')
        course_id = class_id = division_id = department_id = None
        if role == 'Student':
            course_id = optional_id(payload.get('course_id'), 'invalid_body')
            class_id = optional_id(payload.get('class_id'), 'invalid_body')
            division_id = optional_id(payload.get('division_id'), 'invalid_body')
        elif role == 'Teacher':
            department_id = optional_id(payload.get('department_id'), 'invalid_body')
        result = create_registration_invitation(
            email, name, role, days, course_id, class_id, division_id, department_id, session,
        )
        if result == 'duplicate':
            return json_error(_INVITE_MESSAGES['invite_duplicate'], 400, 'invite_duplicate')
        if result == 'registered':
            return json_error(_INVITE_MESSAGES['invite_registered'], 400, 'invite_registered')
        link = _registration_link(result)
        if result == 'error' or not link:
            return json_error(_INVITE_MESSAGES['invitations_unavailable'], 500, 'invitations_unavailable')
        return json_ok({'created': True, 'link': link}, 201)
    except InputError as exc:
        return reject_input(_INVITE_MESSAGES, exc.code)
    except Exception:
        current_app.logger.exception('Invitation create failed')
        return json_error(_INVITE_MESSAGES['invitations_unavailable'], 500, 'invitations_unavailable')


def _change_denied():
    return permission_denied('users_change_user', 'invitations_unavailable', _MESSAGES['invitations_unavailable'])


def _revoke(invitation_id):
    denied = _change_denied()
    if denied:
        return denied
    try:
        revoke_registration_invitation(invitation_id)
        return json_ok({'revoked': True})
    except Exception:
        current_app.logger.exception('Invitation revoke failed')
        return json_error(_MESSAGES['invitations_unavailable'], 500, 'invitations_unavailable')


def _resend(invitation_id):
    denied = _change_denied()
    if denied:
        return denied
    try:
        result = resend_registration_invitation(invitation_id)
        if result == 'missing':
            return json_error(_INVITE_MESSAGES['invite_not_found'], 404, 'invite_not_found')
        if result == 'used':
            return json_error(_INVITE_MESSAGES['invite_used'], 400, 'invite_used')
        link = _registration_link(result)
        if not link:
            return json_error(_MESSAGES['invitations_unavailable'], 500, 'invitations_unavailable')
        return json_ok({'link': link})
    except Exception:
        current_app.logger.exception('Invitation resend failed')
        return json_error(_MESSAGES['invitations_unavailable'], 500, 'invitations_unavailable')


def _link(invitation_id):
    denied = _change_denied()
    if denied:
        return denied
    try:
        link = _registration_link(invitation_token(invitation_id))
        if not link:
            return json_error(_INVITE_MESSAGES['invite_not_found'], 404, 'invite_not_found')
        return json_ok({'link': link})
    except Exception:
        current_app.logger.exception('Invitation link failed')
        return json_error(_MESSAGES['invitations_unavailable'], 500, 'invitations_unavailable')
