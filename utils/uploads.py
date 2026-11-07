"""Save an allowed upload under static/. Callers keep their own error text."""

import os

from flask import current_app
from werkzeug.utils import secure_filename


def save_uploaded_file(file_storage, relative_dir: str, *, allowed_extensions: set[str], name_prefix: str, timestamp: str) -> str:
    """Save an allowed upload and return its path relative to static/."""
    original = file_storage.filename or ''
    if '.' not in original or original.rsplit('.', 1)[1].lower() not in allowed_extensions:
        raise ValueError('unsupported upload')
    filename = secure_filename(original)
    stored_name = f'{name_prefix}_{timestamp}_{filename}'
    directory = os.path.join(current_app.root_path, 'static', *relative_dir.strip('/\\').split('/'))
    os.makedirs(directory, exist_ok=True)
    file_storage.save(os.path.join(directory, stored_name))
    return f"{relative_dir.strip('/\\')}/{stored_name}"
