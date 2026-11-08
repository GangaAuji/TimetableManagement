"""Run full database migration from dump in one command.

Usage:
    python legacy/run_full_migration.py

This script:
1) Creates the target database if it does not exist.
2) Executes table DDL with dependency-aware retries.
3) Loads data inserts.
4) Creates views at the end.

It is designed as a safer alternative to phpMyAdmin import for this project dump.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import mysql.connector
from mysql.connector import Error

ROOT = Path(__file__).resolve().parent.parent


SQL_FILE = ROOT / "backups" / "college_timetable_db_2026_03_30.sql"


def load_dotenv_file(env_path: Path) -> None:
    """Load .env key-value pairs into process environment if not already set."""
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()

        if not key or key in os.environ:
            continue

        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            value = value[1:-1]

        os.environ[key] = value


def get_db_config() -> dict[str, str]:
    """Get DB settings from environment/.env without importing app config modules."""
    load_dotenv_file(ROOT / ".env")

    host = os.environ.get("MYSQL_HOST")
    user = os.environ.get("MYSQL_USER")
    password = os.environ.get("MYSQL_PASSWORD")
    database = os.environ.get("MYSQL_DB")

    if not host or not user or password is None or not database:
        raise RuntimeError(
            "Missing DB config. Set MYSQL_HOST, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DB in environment or .env"
        )

    return {
        "MYSQL_HOST": host,
        "MYSQL_USER": user,
        "MYSQL_PASSWORD": password,
        "MYSQL_DB": database,
    }


def preprocess_sql(sql_text: str) -> str:
    """Normalize dump syntax so mysql-connector can execute statements directly."""
    # Unwrap MySQL versioned comments: /*!50001 ... */;
    sql_text = re.sub(r"/\*![0-9]{5}\s(.*?)\*/;", r"\1;", sql_text, flags=re.DOTALL)

    # Re-enable final view statements if they were commented out previously.
    sql_text = re.sub(
        r"(?m)^\s*--\s*(CREATE\s+OR\s+REPLACE\s+ALGORITHM=UNDEFINED\s+SQL\s+SECURITY\s+INVOKER\s+VIEW\s+)",
        r"\1",
        sql_text,
    )

    # Older MySQL/MariaDB strict modes can reject TIMESTAMP NOT NULL without default.
    # Normalize `expires_at` so schema is portable across server modes.
    sql_text = re.sub(
        r"`expires_at`\s+timestamp\s+NOT\s+NULL(?!\s+DEFAULT)",
        "`expires_at` timestamp NULL DEFAULT NULL",
        sql_text,
        flags=re.IGNORECASE,
    )

    # MySQL 8 dumps may include collations not available in older MySQL/MariaDB.
    # Downgrade these to widely supported alternatives.
    collation_map = {
        "utf8mb4_0900_ai_ci": "utf8mb4_unicode_ci",
        "utf8mb4_0900_bin": "utf8mb4_bin",
    }
    for source_collation, target_collation in collation_map.items():
        sql_text = re.sub(
            rf"(?i)\b{re.escape(source_collation)}\b",
            target_collation,
            sql_text,
        )

    return sql_text


def strip_leading_dump_comments(statement: str) -> str:
    """Remove leading '--' comment lines that can prefix SQL in dump chunks."""
    lines = statement.splitlines()
    idx = 0
    while idx < len(lines):
        line = lines[idx].strip()
        if not line or line.startswith("--"):
            idx += 1
            continue
        break
    return "\n".join(lines[idx:]).strip()


def split_sql_statements(sql_text: str) -> list[str]:
    """Split SQL script into statements while respecting quoted strings."""
    statements: list[str] = []
    buffer: list[str] = []

    in_single = False
    in_double = False
    in_backtick = False
    escape = False

    for ch in sql_text:
        buffer.append(ch)

        if escape:
            escape = False
            continue

        if ch == "\\":
            escape = True
            continue

        if ch == "'" and not in_double and not in_backtick:
            in_single = not in_single
            continue

        if ch == '"' and not in_single and not in_backtick:
            in_double = not in_double
            continue

        if ch == "`" and not in_single and not in_double:
            in_backtick = not in_backtick
            continue

        if ch == ";" and not in_single and not in_double and not in_backtick:
            statement = "".join(buffer).strip()
            if statement:
                statements.append(statement)
            buffer = []

    trailing = "".join(buffer).strip()
    if trailing:
        statements.append(trailing)

    return statements


def is_fk_dependency_error(exc: Error) -> bool:
    message = str(exc).lower()
    return (
        "foreign key" in message
        or "failed to open the referenced table" in message
        or "errno: 150" in message
    )


def is_fk_insert_error(exc: Error) -> bool:
    """Detect FK-related insert/update failures caused by row-order dependencies."""
    message = str(exc).lower()
    errno = getattr(exc, "errno", None)
    return errno in {1451, 1452, 1216, 1217} or "foreign key constraint fails" in message


def classify(statements: list[str]) -> tuple[list[str], list[str], list[str], list[str], list[str]]:
    """Classify statements for ordered execution."""
    setup: list[str] = []
    drops: list[str] = []
    creates: list[str] = []
    inserts: list[str] = []
    views: list[str] = []

    for stmt in statements:
        s = strip_leading_dump_comments(stmt)
        u = s.upper()

        if not s:
            continue

        # Skip plain comments and mysql dump meta lines.
        if u.startswith("LOCK TABLES") or u.startswith("UNLOCK TABLES"):
            continue
        if "ALTER TABLE" in u and ("DISABLE KEYS" in u or "ENABLE KEYS" in u):
            continue

        if u.startswith("SET "):
            setup.append(s)
            continue

        if u.startswith("USE "):
            # Ignore dump-level USE statements; runner controls the active DB.
            continue

        if u.startswith("DROP VIEW") or " VIEW " in u and (
            u.startswith("CREATE VIEW") or u.startswith("CREATE OR REPLACE")
        ):
            views.append(s)
            continue

        if u.startswith("DROP TABLE"):
            drops.append(s)
            continue

        if u.startswith("CREATE TABLE"):
            creates.append(s)
            continue

        if u.startswith("INSERT INTO"):
            inserts.append(s)
            continue

        setup.append(s)

    return setup, drops, creates, inserts, views


def execute_batch(cursor, statements: list[str], label: str) -> None:
    for idx, stmt in enumerate(statements, start=1):
        cursor.execute(stmt)
        if idx % 100 == 0:
            print(f"[{label}] executed {idx} statements")


def execute_inserts_with_retry(cursor, insert_statements: list[str]) -> None:
    """Execute inserts with multiple passes to resolve FK row-order dependencies."""
    pending = list(insert_statements)
    round_no = 0

    while pending:
        round_no += 1
        progressed = 0
        next_pending: list[str] = []
        hard_errors: list[tuple[str, Exception]] = []

        for stmt in pending:
            try:
                cursor.execute(stmt)
                progressed += 1
            except Error as exc:
                if is_fk_insert_error(exc):
                    next_pending.append(stmt)
                else:
                    hard_errors.append((stmt, exc))

        if hard_errors:
            sample_stmt, sample_exc = hard_errors[0]
            raise RuntimeError(
                "Insert phase failed with non-retryable error:\n"
                f"Error: {sample_exc}\n"
                f"Statement: {sample_stmt[:500]}"
            )

        print(f"[inserts] round {round_no}: inserted {progressed}, pending {len(next_pending)}")

        if not next_pending:
            return

        if progressed == 0:
            # Final fallback for orphaned seed rows in legacy dumps.
            print(
                "[inserts] unresolved FK dependencies remain; "
                "retrying pending inserts with FOREIGN_KEY_CHECKS=0"
            )
            cursor.execute("SET FOREIGN_KEY_CHECKS=0")
            try:
                forced_ok = 0
                forced_failures: list[tuple[str, Exception]] = []
                for stmt in next_pending:
                    try:
                        cursor.execute(stmt)
                        forced_ok += 1
                    except Error as exc:
                        forced_failures.append((stmt, exc))
            finally:
                cursor.execute("SET FOREIGN_KEY_CHECKS=1")

            print(
                f"[inserts] forced mode: inserted {forced_ok}, "
                f"failed {len(forced_failures)}"
            )

            if forced_failures:
                sample_stmt, sample_exc = forced_failures[0]
                raise RuntimeError(
                    "Insert phase still has unresolved statements even with FOREIGN_KEY_CHECKS=0.\n"
                    f"Error: {sample_exc}\n"
                    f"Statement: {sample_stmt[:500]}"
                )

            return

        pending = next_pending


def execute_create_tables_with_retry(cursor, create_table_statements: list[str]) -> None:
    pending = list(create_table_statements)
    round_no = 0

    while pending:
        round_no += 1
        progressed = 0
        next_pending: list[str] = []
        hard_errors: list[tuple[str, Exception]] = []

        for stmt in pending:
            try:
                cursor.execute(stmt)
                progressed += 1
            except Error as exc:
                if is_fk_dependency_error(exc):
                    next_pending.append(stmt)
                else:
                    hard_errors.append((stmt, exc))

        if hard_errors:
            sample_stmt, sample_exc = hard_errors[0]
            raise RuntimeError(
                "Table creation failed with non-retryable error:\n"
                f"Error: {sample_exc}\n"
                f"Statement: {sample_stmt[:500]}"
            )

        print(f"[tables] round {round_no}: created {progressed}, pending {len(next_pending)}")

        if not next_pending:
            return

        if progressed == 0:
            sample = next_pending[0][:500]
            raise RuntimeError(
                "Could not resolve remaining table dependencies. "
                "Please check referenced tables/constraints in dump.\n"
                f"Sample pending statement: {sample}"
            )

        pending = next_pending


def main() -> None:
    if not SQL_FILE.exists():
        raise FileNotFoundError(f"SQL file not found: {SQL_FILE}")

    db_cfg = get_db_config()

    print(f"Reading SQL dump: {SQL_FILE}")
    raw_sql = SQL_FILE.read_text(encoding="utf-8")
    normalized_sql = preprocess_sql(raw_sql)
    statements = split_sql_statements(normalized_sql)
    setup, drops, creates, inserts, views = classify(statements)

    print(
        f"Parsed statements -> setup:{len(setup)} drops:{len(drops)} "
        f"creates:{len(creates)} inserts:{len(inserts)} views:{len(views)}"
    )

    conn = mysql.connector.connect(
        host=db_cfg["MYSQL_HOST"],
        user=db_cfg["MYSQL_USER"],
        password=db_cfg["MYSQL_PASSWORD"],
        autocommit=True,
    )

    try:
        cur = conn.cursor()

        db_name = db_cfg["MYSQL_DB"]
        print(f"Target database from environment: {db_name}")
        cur.execute(f"CREATE DATABASE IF NOT EXISTS `{db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        cur.execute(f"USE `{db_name}`")

        # Default to ON; we selectively disable during drop phase only.
        cur.execute("SET FOREIGN_KEY_CHECKS=1")

        # Execute non-DDL setup statements first where safe.
        for stmt in setup:
            u = stmt.upper()
            if u.startswith("SET OLD_"):
                continue
            try:
                cur.execute(stmt)
            except Error:
                # Session/state restoration statements can fail harmlessly in a fresh session.
                continue

        print("Running DROP TABLE statements...")
        cur.execute("SET FOREIGN_KEY_CHECKS=0")
        execute_batch(cur, drops, "drops")
        cur.execute("SET FOREIGN_KEY_CHECKS=1")

        print("Running CREATE TABLE statements with dependency retries...")
        execute_create_tables_with_retry(cur, creates)

        print("Running INSERT statements with dependency retries...")
        execute_inserts_with_retry(cur, inserts)

        print("Running VIEW statements...")
        execute_batch(cur, views, "views")

        print("Migration completed successfully.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
