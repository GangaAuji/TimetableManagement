from seeders.base import SeedResult
from services.branding import DEFAULT_SETTINGS, seed_branding_defaults


class BrandingSeeder:
    """Insert missing branding settings. Values a college has changed are never overwritten."""

    name = 'branding_settings'

    def run(self, cursor):
        added = seed_branding_defaults(cursor)
        return SeedResult('branding_settings', added, len(DEFAULT_SETTINGS) - added)
