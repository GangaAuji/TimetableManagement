"""How the current process is using the app."""

import click


def loaded_for_cli_command():
    """True when a `flask` command other than `run` is loading the app.

    Flask loads the app inside the click context of the command being run, or
    of the `flask` group while it looks up a command the app registers. `flask
    run` serves requests, and its reloader child loads the app outside any
    click context, so both count as serving. `python app.py` and WSGI servers
    have no click context at all.
    """
    ctx = click.get_current_context(silent=True)
    if ctx is None:
        return False
    names = set()
    while ctx is not None:
        names.add(ctx.info_name)
        ctx = ctx.parent
    return 'run' not in names
