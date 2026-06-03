from __future__ import annotations

import argparse
import sqlite3

from sqlalchemy import Boolean, create_engine, inspect, text


def migrate(sqlite_path: str, database_url: str) -> None:
    sqlite = sqlite3.connect(sqlite_path)
    sqlite.row_factory = sqlite3.Row
    pg = create_engine(database_url, future=True)
    inspector = inspect(pg)
    pg_tables = set(inspector.get_table_names())

    tables = [
        row["name"]
        for row in sqlite.execute("select name from sqlite_master where type='table' order by name").fetchall()
        if row["name"] != "sqlite_sequence"
    ]

    with pg.begin() as conn:
        for table in tables:
            if table not in pg_tables:
                print(f"skip missing table: {table}")
                continue

            columns = [row["name"] for row in sqlite.execute(f"pragma table_info({table})").fetchall()]
            if not columns:
                continue

            target_column_info = {column["name"]: column for column in inspector.get_columns(table)}
            target_columns = set(target_column_info)
            copy_columns = [column for column in columns if column in target_columns]
            if not copy_columns:
                continue

            rows = sqlite.execute(f"select {', '.join(copy_columns)} from {table}").fetchall()
            if not rows:
                continue

            placeholders = ", ".join(f":{column}" for column in copy_columns)
            column_sql = ", ".join(copy_columns)
            conflict_sql = " ON CONFLICT DO NOTHING"
            stmt = text(f"insert into {table} ({column_sql}) values ({placeholders}){conflict_sql}")
            payload = []
            for row in rows:
                item = dict(row)
                for column in copy_columns:
                    if isinstance(target_column_info[column]["type"], Boolean) and item.get(column) is not None:
                        item[column] = bool(item[column])
                payload.append(item)

            conn.execute(stmt, payload)
            print(f"migrated {len(rows)} rows: {table}")

    sqlite.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sqlite", default="resume_ai.db")
    parser.add_argument("--database-url", required=True)
    args = parser.parse_args()
    migrate(args.sqlite, args.database_url)


if __name__ == "__main__":
    main()
