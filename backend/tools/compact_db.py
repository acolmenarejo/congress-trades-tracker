"""Keep the committed SQLite well under GitHub's 100 MB hard limit per file
(it was 50 MB in Oct 2026, growing ~10 MB/month; past 100 MB every push —
and so every cron — would be rejected).

- price_cache becomes a WITHOUT ROWID table: its (ticker, date) primary key
  then IS the table, instead of a table plus a same-sized separate index
  (~-13 MB). One-off, skipped once done.
- VACUUM when more than 10% of pages are free (deleted rows leave holes).
- Warns in the job log past WARN_MB so it's noticed long before the limit.

Run from rankings.yml (daily) before its commit step:
    python tools/compact_db.py [path]
"""
import os
import sqlite3
import sys

DEFAULT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "congress_trades.db")
WARN_MB = 80


def main(path: str) -> None:
    before = os.path.getsize(path) / 1e6
    con = sqlite3.connect(path)
    sql = (con.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='price_cache'").fetchone() or [""])[0]
    if sql and "WITHOUT ROWID" not in sql.upper():
        con.executescript("""
            BEGIN;
            CREATE TABLE price_cache_new (
                ticker VARCHAR NOT NULL, date DATE NOT NULL,
                open FLOAT, high FLOAT, low FLOAT, close FLOAT, volume FLOAT,
                PRIMARY KEY (ticker, date)
            ) WITHOUT ROWID;
            INSERT INTO price_cache_new SELECT ticker, date, open, high, low, close, volume FROM price_cache;
            DROP TABLE price_cache;
            ALTER TABLE price_cache_new RENAME TO price_cache;
            COMMIT;
        """)
        print("compact_db: price_cache converted to WITHOUT ROWID")
    pages = con.execute("PRAGMA page_count").fetchone()[0]
    free = con.execute("PRAGMA freelist_count").fetchone()[0]
    if pages and free / pages > 0.10:
        con.execute("VACUUM")
        print(f"compact_db: vacuumed ({free}/{pages} pages were free)")
    con.close()
    after = os.path.getsize(path) / 1e6
    print(f"compact_db: {before:.1f} MB -> {after:.1f} MB")
    if after > WARN_MB:
        print(f"::warning::congress_trades.db is {after:.0f} MB; GitHub rejects files over 100 MB. Trim price_cache or move it out.")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else DEFAULT)
