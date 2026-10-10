"""Copy specific tables (or rows) from one SQLite file into another.

Used by long-running workflows (insiders.yml, setups.yml) when their push of
backend/data/congress_trades.db loses the race against another workflow: a
binary SQLite can't be rebased, so they reset to the remote DB and re-apply
only the tables they own.

Usage:
    python merge_tables.py SRC.db DEST.db TABLE[:WHERE] [TABLE[:WHERE] ...]
e.g.
    python merge_tables.py /tmp/ours.db data/congress_trades.db insider_trades "telegram_state:key LIKE 'insiders%'"
"""
import sqlite3
import sys


def main(src: str, dest: str, specs: list[str]) -> None:
    con = sqlite3.connect(dest)
    con.execute("ATTACH DATABASE ? AS src", (src,))
    for spec in specs:
        table, _, where = spec.partition(":")
        row = con.execute("SELECT sql FROM src.sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
        if row is None:
            continue
        if con.execute("SELECT 1 FROM main.sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is None:
            con.execute(row[0])
            for (idx_sql,) in con.execute(
                "SELECT sql FROM src.sqlite_master WHERE type='index' AND tbl_name=? AND sql IS NOT NULL", (table,)
            ).fetchall():
                con.execute(idx_sql)
        src_cols = con.execute(f'PRAGMA src.table_info("{table}")').fetchall()
        have = {c[1] for c in con.execute(f'PRAGMA main.table_info("{table}")')}
        for c in src_cols:  # a newer schema on our side (see database._ADDED_COLUMNS)
            if c[1] not in have:
                con.execute(f'ALTER TABLE main."{table}" ADD COLUMN "{c[1]}" {c[2]}')
        cols = ", ".join(f'"{c[1]}"' for c in src_cols)
        sql = f'INSERT OR REPLACE INTO main."{table}" ({cols}) SELECT {cols} FROM src."{table}"'
        n = con.execute(sql + (f" WHERE {where}" if where else "")).rowcount
        print(f"merge_tables: {table}: {n} row(s)")
    con.commit()
    con.close()


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3:])
