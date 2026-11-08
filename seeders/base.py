"""What every seeder returns, and the seed_history helpers."""

from dataclasses import dataclass, field


@dataclass
class SeedResult:
    table: str
    added: int = 0
    present: int = 0
    lines: list = field(default_factory=list)

    def summary(self):
        return f'{self.table}: {self.added} added, {self.present} already present.'


def recorded(cursor, seeder):
    """Return {item: version} for everything `seeder` has already handled."""
    cursor.execute('SELECT item, version FROM seed_history WHERE seeder = %s', (seeder,))
    return {item: version for item, version in cursor.fetchall()}


def record(cursor, seeder, item, version):
    cursor.execute(
        'INSERT INTO seed_history (seeder, item, version) VALUES (%s, %s, %s)',
        (seeder, item, str(version)),
    )


def ids_by_name(cursor, table):
    """Return {lower-case name: (id, name)}; names compare case-insensitively like the unicode_ci columns."""
    cursor.execute(f'SELECT id, name FROM {table}')
    return {name.lower(): (row_id, name) for row_id, name in cursor.fetchall()}
