"""Per-test isolation for the shared *_test database.

The app opens a new connection for each query and commits, so a test cannot
be wrapped in one transaction and rolled back. Instead every table's rows and
CHECKSUM are captured once after migrate and seed. After each test, only the
tables whose checksum changed are emptied and refilled from that capture.
DELETE is used, not TRUNCATE: TRUNCATE recreates the InnoDB file and takes
about a second per table. Auto-increment counters therefore keep counting.
"""

_SKIP = frozenset({'alembic_version'})


def _tables(cursor):
    cursor.execute(
        "SELECT TABLE_NAME FROM information_schema.TABLES "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_TYPE = 'BASE TABLE' ORDER BY TABLE_NAME"
    )
    return [row[0] for row in cursor.fetchall() if row[0] not in _SKIP]


def _checksums(cursor, tables):
    cursor.execute('CHECKSUM TABLE ' + ', '.join(f'`{name}`' for name in tables))
    return {row[0].split('.', 1)[1]: row[1] for row in cursor.fetchall()}


class Baseline:
    def __init__(self, tables, rows, checksums):
        self.tables = tables
        self.rows = rows
        self.checksums = checksums

    @classmethod
    def capture(cls, connection):
        cursor = connection.cursor()
        try:
            tables = _tables(cursor)
            rows = {}
            for name in tables:
                cursor.execute(f'SELECT * FROM `{name}`')
                rows[name] = ([column[0] for column in cursor.description], cursor.fetchall())
            return cls(tables, rows, _checksums(cursor, tables))
        finally:
            cursor.close()

    def changed(self, connection):
        cursor = connection.cursor()
        try:
            current = _checksums(cursor, self.tables)
        finally:
            cursor.close()
        return [name for name in self.tables if current.get(name) != self.checksums.get(name)]

    def restore(self, connection):
        """Put every changed table back to its captured rows. Returns the restored table names."""
        changed = self.changed(connection)
        if not changed:
            return changed
        cursor = connection.cursor()
        try:
            cursor.execute('SET FOREIGN_KEY_CHECKS = 0')
            for name in changed:
                cursor.execute(f'DELETE FROM `{name}`')
                columns, rows = self.rows[name]
                if rows:
                    names = ', '.join(f'`{column}`' for column in columns)
                    marks = ', '.join(['%s'] * len(columns))
                    cursor.executemany(f'INSERT INTO `{name}` ({names}) VALUES ({marks})', rows)
            cursor.execute('SET FOREIGN_KEY_CHECKS = 1')
            connection.commit()
        finally:
            cursor.close()
        return changed
