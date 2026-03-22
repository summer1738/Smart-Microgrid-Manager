#!/usr/bin/env python3
"""
Export PV, battery, and load readings from the microgrid DB to CSV for LSTM training.
Usage (from project root):
  python -m ai.scripts.export_readings [--hours 168] [--output data/readings.csv]
  Or with backend venv: cd backend && PYTHONPATH=.. python -m ai.scripts.export_readings
"""
import argparse
import csv
import os
import sqlite3
import sys
from pathlib import Path
from typing import Optional


def default_db_path() -> str:
    root = Path(__file__).resolve().parents[2]  # project root (smart-microgrid-manager)
    return str(root / "backend" / "microgrid.db")


def export(hours: int = 168, output_path: Optional[str] = None, db_path: Optional[str] = None) -> None:
    db_path = db_path or default_db_path()
    if not os.path.isfile(db_path):
        print(f"DB not found: {db_path}", file=sys.stderr)
        sys.exit(1)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    since = f"-{hours} hours" if hours > 0 else "0"
    # Aligned by timestamp: use battery as driver (one row per tick)
    rows = conn.execute(
        """
        SELECT
            b.timestamp,
            COALESCE(p.power_kw, 0) AS pv_kw,
            b.soc_percent,
            COALESCE(l.total_load_kw, 0) AS total_load_kw
        FROM battery_readings b
        LEFT JOIN (
            SELECT timestamp, power_kw FROM pv_readings
        ) p ON p.timestamp = b.timestamp
        LEFT JOIN (
            SELECT timestamp, SUM(power_kw) AS total_load_kw
            FROM load_readings GROUP BY timestamp
        ) l ON l.timestamp = b.timestamp
        WHERE b.timestamp >= datetime('now', ?)
        ORDER BY b.timestamp
        """,
        (since,),
    ).fetchall()
    conn.close()
    if not rows:
        print("No readings in range.", file=sys.stderr)
        return
    out = output_path or "readings.csv"
    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["timestamp", "pv_kw", "soc_percent", "total_load_kw"])
        for r in rows:
            w.writerow([r["timestamp"], r["pv_kw"], r["soc_percent"], r["total_load_kw"]])
    print(f"Exported {len(rows)} rows to {out_path}")


def main() -> None:
    p = argparse.ArgumentParser(description="Export microgrid readings to CSV for LSTM training")
    p.add_argument("--hours", type=int, default=168, help="Last N hours (default 168 = 1 week)")
    p.add_argument("--output", "-o", default="readings.csv", help="Output CSV path")
    p.add_argument("--db", default=None, help="Path to microgrid.db (default: backend/microgrid.db)")
    args = p.parse_args()
    export(hours=args.hours, output_path=args.output, db_path=args.db)


if __name__ == "__main__":
    main()
