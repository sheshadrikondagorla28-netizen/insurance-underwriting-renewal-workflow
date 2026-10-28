"""Build a SQLite database from the generated schema and SQL seed file."""
from __future__ import annotations
import argparse
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EXPECTED = {
    "applicants": 3000,
    "insured_assets": 3000,
    "products": 3,
    "coverage_options": 6,
    "risk_factors": 4,
    "quotes": 4000,
    "policies": 2000,
    "endorsements": 200,
    "renewals": 1200,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="data/insurance.db", help="SQLite database path (default: data/insurance.db)")
    parser.add_argument("--overwrite", action="store_true", help="Replace the output database if it already exists")
    args = parser.parse_args()
    output = Path(args.output)
    if not output.is_absolute():
        output = ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() and not args.overwrite:
        parser.error(f"{output} already exists. Choose another --output path or pass --overwrite.")

    schema = (ROOT / "data" / "schema.sql").read_text(encoding="utf-8")
    seed = (ROOT / "data" / "seed_data.sql").read_text(encoding="utf-8")
    if output.exists():
        output.unlink()
    try:
        with sqlite3.connect(output) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.executescript(schema)
            conn.executescript(seed)
            violations = conn.execute("PRAGMA foreign_key_check").fetchall()
            if violations:
                raise RuntimeError(f"Foreign-key validation failed; first violations: {violations[:10]}")
            counts = {table: conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0] for table in EXPECTED}
            mismatches = {table: (count, EXPECTED[table]) for table, count in counts.items() if count != EXPECTED[table]}
            if mismatches:
                raise RuntimeError(f"Unexpected row counts (actual, expected): {mismatches}")
    except Exception:
        if output.exists():
            output.unlink()
        raise

    print(f"Database created successfully: {output}")
    for table, count in counts.items():
        print(f"{table}: {count:,}")
    print("Foreign-key check: PASS")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
