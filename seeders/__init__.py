"""Reference rows the app expects, inserted by `flask seed run`.

Seeders only add missing rows; they never update or delete. They run in
order inside the caller's transaction.
"""

from seeders.branding import BrandingSeeder
from seeders.permissions import PermissionsSeeder
from seeders.role_permissions import RolePermissionsSeeder
from seeders.roles import RolesSeeder


def default_seeders(apply_role_defaults=False):
    return (
        RolesSeeder(),
        PermissionsSeeder(),
        RolePermissionsSeeder(apply_defaults=apply_role_defaults),
        BrandingSeeder(),
    )


def run_seeders(cursor, apply_role_defaults=False):
    """Run every seeder on `cursor` and return their results. The caller commits."""
    return [seeder.run(cursor) for seeder in default_seeders(apply_role_defaults)]
