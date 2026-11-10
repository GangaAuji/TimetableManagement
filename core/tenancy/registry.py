"""The tenant registry: one small table in its own database.

The registry database is named by TENANT_REGISTRY_DB and reached with the
same MYSQL_HOST, MYSQL_USER and MYSQL_PASSWORD as the tenant databases. Its
only table is created with `flask tenant init` (or the first `tenant create`).
Hostname lookups are cached in the process for TENANT_CACHE_SECONDS so a
request does not cost a registry round trip.
"""

import re
import threading
import time

from core.tenancy import STATUSES, Tenant

SLUG = re.compile(r'^[a-z0-9](?:[a-z0-9-]{0,38}[a-z0-9])?$')
_HOST_LABEL = re.compile(r'^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$')
DATABASE_NAME = re.compile(r'^[a-z0-9_]{1,64}$')
DEFAULT_CACHE_SECONDS = 30

SCHEMA = """
CREATE TABLE IF NOT EXISTS tenants (
    id INT(11) NOT NULL AUTO_INCREMENT,
    slug VARCHAR(40) NOT NULL,
    hostname VARCHAR(253) NOT NULL,
    db_name VARCHAR(64) NOT NULL,
    status ENUM('provisioning', 'active', 'suspended') NOT NULL DEFAULT 'provisioning',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_tenants_slug (slug),
    UNIQUE KEY uq_tenants_hostname (hostname),
    UNIQUE KEY uq_tenants_db_name (db_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""
_COLUMNS = 'id, slug, hostname, db_name, status'


def normalise_host(host):
    """Lower-case the Host header value and drop any port. Returns '' for nothing usable."""
    value = (host or '').strip().lower()
    if value.startswith('['):
        end = value.find(']')
        return value[1:end] if end > 0 else ''
    return value.rsplit(':', 1)[0] if value.count(':') == 1 else value


def valid_slug(slug):
    return isinstance(slug, str) and bool(SLUG.match(slug))


def valid_hostname(hostname):
    if not isinstance(hostname, str) or not 1 <= len(hostname) <= 253 or hostname != normalise_host(hostname):
        return False
    return all(_HOST_LABEL.match(label) for label in hostname.split('.'))


def valid_database_name(name):
    return isinstance(name, str) and bool(DATABASE_NAME.match(name))


def default_database_name(slug):
    return f'college_timetable_{slug.replace("-", "_")}'


def _row_to_tenant(row):
    if row is None:
        return None
    if isinstance(row, dict):
        return Tenant(slug=row['slug'], hostname=row['hostname'], db_name=row['db_name'], status=row['status'], id=row['id'])
    identifier, slug, hostname, db_name, status = row
    return Tenant(slug=slug, hostname=hostname, db_name=db_name, status=status, id=identifier)


class Registry:
    """Reads and writes the tenants table. Each method opens and closes its own connection."""

    def __init__(self, settings, cache_seconds=DEFAULT_CACHE_SECONDS):
        self.settings = settings
        self.cache_seconds = cache_seconds
        self._cache = {}
        self._lock = threading.Lock()

    @classmethod
    def settings_from_config(cls, config):
        from core.tenancy import registry_name

        name = registry_name(config)
        if name is None:
            raise RuntimeError('TENANT_REGISTRY_DB is not set; this installation serves one college.')
        settings = {
            'host': config.get('MYSQL_HOST'),
            'user': config.get('MYSQL_USER'),
            'password': config.get('MYSQL_PASSWORD'),
            'database': name,
        }
        if config.get('MYSQL_INIT_COMMAND'):
            settings['init_command'] = config.get('MYSQL_INIT_COMMAND')
        return settings

    @classmethod
    def from_config(cls, config):
        """The process-wide registry for this config. Cached on the config object so hostname lookups share a cache."""
        registry = config.get('_TENANT_REGISTRY')
        if registry is None:
            seconds = config.get('TENANT_CACHE_SECONDS', DEFAULT_CACHE_SECONDS)
            registry = cls(cls.settings_from_config(config), cache_seconds=int(seconds))
            config['_TENANT_REGISTRY'] = registry
        return registry

    def connect(self):
        import mysql.connector

        return mysql.connector.connect(**self.settings, autocommit=False)

    def _query(self, statement, params=(), one=False, write=False):
        connection = self.connect()
        try:
            cursor = connection.cursor()
            try:
                cursor.execute(statement, params)
                if write:
                    result = cursor.lastrowid
                    connection.commit()
                else:
                    result = cursor.fetchone() if one else cursor.fetchall()
                    connection.rollback()
            finally:
                cursor.close()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return result

    def ensure_schema(self):
        connection = self.connect()
        try:
            cursor = connection.cursor()
            try:
                cursor.execute(SCHEMA)
                connection.commit()
            finally:
                cursor.close()
        finally:
            connection.close()

    def all(self):
        rows = self._query(f'SELECT {_COLUMNS} FROM tenants ORDER BY slug')
        return [_row_to_tenant(row) for row in rows]

    def by_slug(self, slug):
        return _row_to_tenant(self._query(f'SELECT {_COLUMNS} FROM tenants WHERE slug = %s', (slug,), one=True))

    def by_hostname(self, hostname):
        return _row_to_tenant(
            self._query(f'SELECT {_COLUMNS} FROM tenants WHERE hostname = %s', (hostname,), one=True)
        )

    def by_database(self, db_name):
        return _row_to_tenant(
            self._query(f'SELECT {_COLUMNS} FROM tenants WHERE db_name = %s', (db_name,), one=True)
        )

    def insert(self, tenant):
        if tenant.status not in STATUSES:
            raise ValueError(f'Unknown tenant status {tenant.status!r}.')
        identifier = self._query(
            'INSERT INTO tenants (slug, hostname, db_name, status) VALUES (%s, %s, %s, %s)',
            (tenant.slug, tenant.hostname, tenant.db_name, tenant.status),
            write=True,
        )
        self.forget()
        return Tenant(slug=tenant.slug, hostname=tenant.hostname, db_name=tenant.db_name, status=tenant.status, id=identifier)

    def set_status(self, slug, status):
        if status not in STATUSES:
            raise ValueError(f'Unknown tenant status {status!r}.')
        self._query('UPDATE tenants SET status = %s WHERE slug = %s', (status, slug), write=True)
        self.forget()

    def delete(self, slug):
        """Remove the registry row only. The tenant database is never dropped by the app."""
        self._query('DELETE FROM tenants WHERE slug = %s', (slug,), write=True)
        self.forget()

    def forget(self):
        with self._lock:
            self._cache.clear()

    def resolve(self, host, now=None):
        """The tenant for a Host header value (or None), through the short-lived cache."""
        hostname = normalise_host(host)
        if not hostname:
            return None
        moment = time.monotonic() if now is None else now
        with self._lock:
            cached = self._cache.get(hostname)
            if cached is not None and moment - cached[0] < self.cache_seconds:
                return cached[1]
        tenant = self.by_hostname(hostname)
        with self._lock:
            self._cache[hostname] = (moment, tenant)
        return tenant
