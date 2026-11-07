from flask_wtf import FlaskForm
from wtforms import (
    StringField, PasswordField, SelectField, TextAreaField, 
    SelectMultipleField, BooleanField, widgets
)
from wtforms.validators import DataRequired, Length, Email, Optional, ValidationError

# Custom field to render checkboxes for multi-selects
class MultiCheckboxField(SelectMultipleField):
    widget = widgets.ListWidget(prefix_label=False)
    option_widget = widgets.CheckboxInput()

# Login form
class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])

    def validate(self):
        """Custom validation that logs validation errors"""
        from flask import current_app
        initial_validation = super().validate()
        if not initial_validation:
            current_app.logger.warning(f'Form validation failed: {self.errors}')
            return False
        return True

# User creation/edit form
class UserForm(FlaskForm):
    username = StringField('Username', validators=[
        DataRequired(), 
        Length(min=3, max=50)
    ])
    password = PasswordField('Password', validators=[
        Optional(),
        Length(min=8, message="Password must be at least 8 characters long")
    ])
    role = SelectField('Role', validators=[DataRequired()], coerce=str)
    status = SelectField('Status', choices=[
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('locked', 'Locked')
    ], default='active', coerce=str)
    email = StringField('Email', validators=[Optional(), Email()])

# Role creation/edit form
class RoleForm(FlaskForm):
    name = StringField('Role Name', validators=[
        DataRequired(),
        Length(min=3, max=50)
    ])
    description = TextAreaField('Description', validators=[Optional()])
    permissions = MultiCheckboxField('Permissions', coerce=int)

# Permission creation/edit form
class PermissionForm(FlaskForm):
    name = StringField('Permission Name', validators=[
        DataRequired(),
        Length(min=3, max=50)
    ])
    description = TextAreaField('Description', validators=[Optional()])
    module = SelectField('Module', validators=[DataRequired()], choices=[
        ('user_management', 'User Management'),
        ('academic', 'Academic'),
        ('timetable', 'Timetable'),
        ('faculty', 'Faculty')
    ], coerce=str)

# Empty form (e.g. for CSRF only submissions)
class EmptyForm(FlaskForm):
    pass

# Form to filter users by role, status, and search term
class UserFilterForm(FlaskForm):
    role = SelectField('Role', choices=[], validators=[Optional()], coerce=str)
    status = SelectField('Status', choices=[
        ('', 'All'),
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('locked', 'Locked')
    ], validators=[Optional()], coerce=str)
    search = StringField('Search', validators=[Optional()])

# Simple form for CSRF protection on invitation creation
class InvitationForm(FlaskForm):
    pass

# Registration form for invitation-based signup
class RegistrationForm(FlaskForm):
    username = StringField('Username', validators=[
        DataRequired(),
        Length(min=3, max=50)
    ])
    password = PasswordField('Password', validators=[
        DataRequired(),
        Length(min=6, message="Password must be at least 6 characters long")
    ])
    confirm_password = PasswordField('Confirm Password', validators=[
        DataRequired()
    ])
    
    def validate_confirm_password(self, field):
        if field.data != self.password.data:
            raise ValidationError('Passwords do not match.')
