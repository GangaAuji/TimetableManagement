"""One database per college.

Without TENANT_REGISTRY_DB the app serves the single database in MYSQL_DB, as
before. With it, a registry database holds a `tenants` table (slug, hostname,
db_name, status); every request is resolved by its Host header to one tenant,
`g.tenant` is set, and `models.db.connection_settings()` opens that tenant's
database. CLI commands take `--tenant SLUG`; background workers run once per
active tenant; uploads and report files live under a per-tenant folder.

Nothing here touches a tenant database directly: `bind()` only records which
one the rest of the request or command should open.
"""

import contextlib
from dataclasses import dataclass

from flask import current_app, g, has_app_context

STATUSES = ('provisioning', 'active', 'suspended')
_G_KEY = 'tenant'


@dataclass(frozen=True)
class Tenant:
    slug: str
    hostname: str
    db_name: str
    status: str = 'active'
    id: int | None = None

    @property
    def active(self):
        return self.status == 'active'


def registry_name(config=None):
    """The registry database name, or None when this installation has one college."""
    if config is None:
        if not has_app_context():
            return None
        config = current_app.config
    name = config.get('TENANT_REGISTRY_DB')
    return name.strip() if isinstance(name, str) and name.strip() else None


def registry_enabled(config=None):
    return registry_name(config) is not None


def current_tenant():
    """The tenant bound to this app context, or None."""
    if not has_app_context():
        return None
    return getattr(g, _G_KEY, None)


def bind(tenant):
    """Make `tenant` the one this app context opens. Testing apps refuse a non-test database name."""
    if tenant is not None and current_app.config.get('TESTING'):
        from config.testing import test_database_problem

        problem = test_database_problem(tenant.db_name)
        if problem:
            raise RuntimeError(f'Refusing to bind tenant {tenant.slug!r} in a testing app: {problem}')
    setattr(g, _G_KEY, tenant)


@contextlib.contextmanager
def tenant_context(app, tenant):
    """A fresh app context with `tenant` bound (None binds nothing: the single configured database)."""
    with app.app_context():
        bind(tenant)
        yield tenant


def slug_for_paths():
    """The folder segment for per-tenant files: the slug, or None in single-college mode."""
    tenant = current_tenant()
    return tenant.slug if tenant is not None else None


def scoped_relative_dir(relative_dir):
    """`uploads/profiles` -> `uploads/<slug>/profiles` when a tenant is bound (paths relative to static/)."""
    slug = slug_for_paths()
    if slug is None:
        return relative_dir.strip('/\\')
    head, _, tail = relative_dir.strip('/\\').partition('/')
    return f'{head}/{slug}/{tail}' if tail else f'{head}/{slug}'


def scoped_storage_dir(base_dir):
    """`UPLOAD_FOLDER` -> `UPLOAD_FOLDER/<slug>` when a tenant is bound."""
    import os

    slug = slug_for_paths()
    return os.path.join(base_dir, slug) if slug else base_dir


def scoped_model_path(path):
    """`dir/model.json` -> `dir/<slug>/model.json` when a tenant is bound (one learned model per college)."""
    import os

    slug = slug_for_paths()
    if not slug or not path:
        return path
    head, tail = os.path.split(path)
    return os.path.join(head, slug, tail)


def tenants_to_serve(app):
    """Active tenants for a worker to loop over, or [None] in single-college mode."""
    if not registry_enabled(app.config):
        return [None]
    from core.tenancy.registry import Registry

    return [tenant for tenant in Registry.from_config(app.config).all() if tenant.active]
