#!/usr/bin/env python3
"""
Export PV, battery, and load readings from the MySQL database to CSV for LSTM training.
Usage (from project root):
  python -m ai.scripts.export_readings --database-url mysql+aiomysql://... [--hours 168] [--output data/readings.csv]
"""
import argparse
import csv
import os
import sys
from pathlib import Path
from typing import Optional

from sqlalchemy import create_engine, text


def default_database_url() -> str:
    return os.environ.get(
        "MICROGRID_DATABASE_URL",
        "mysql+aiomysql://root:Virus1738%25@localhost:3306/smart_microgrid",
    )


def to_sync_database_url(url: str) -> str:
    if url.startswith("mysql+aiomysql://"):
        return url.replace("mysql+aiomysql://", "mysql+pymysql://", 1)
    return url


def export(hours: int = 168, output_path: Optional[str] = None, database_url: Optional[str] = None) -> None:
    database_url = to_sync_database_url(database_url or default_database_url())
    engine = create_engine(database_url)
    # Aligned by timestamp: use battery as driver (one row per tick)
    query = text(
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
        WHERE b.timestamp >= :since_ts
        ORDER BY b.timestamp
        """
    )
    interval = max(0, int(hours))
    query = text(
        query.text.replace("b.timestamp >= :since_ts", f"b.timestamp >= DATE_SUB(UTC_TIMESTAMP(), INTERVAL {interval} HOUR)")
    )
    bind = {}
    with engine.connect() as conn:
        rows = conn.execute(query, bind).mappings().all()
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
    p.add_argument("--database-url", default=None, help="MySQL SQLAlchemy database URL")
    args = p.parse_args()
    export(hours=args.hours, output_path=args.output, database_url=args.database_url)


if __name__ == "__main__":
    main()
