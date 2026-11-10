"""Save an allowed upload under static/. Callers keep their own error text."""

import os

from flask import current_app
from werkzeug.utils import secure_filename

from core.tenancy import scoped_relative_dir


def save_uploaded_file(file_storage, relative_dir: str, *, allowed_extensions: set[str], name_prefix: str, timestamp: str) -> str:
    """Save an allowed upload and return its path relative to static/."""
    original = file_storage.filename or ''
    if '.' not in original or original.rsplit('.', 1)[1].lower() not in allowed_extensions:
        raise ValueError('unsupported upload')
    filename = secure_filename(original)
    stored_name = f'{name_prefix}_{timestamp}_{filename}'
    relative_dir = scoped_relative_dir(relative_dir)
    directory = static_directory(relative_dir)
    os.makedirs(directory, exist_ok=True)
    file_storage.save(os.path.join(directory, stored_name))
    return f'{relative_dir}/{stored_name}'


def static_directory(relative_dir: str) -> str:
    """Absolute folder under static/ for a (possibly tenant-scoped) relative dir."""
    return os.path.join(current_app.root_path, 'static', *relative_dir.strip('/\\').split('/'))
