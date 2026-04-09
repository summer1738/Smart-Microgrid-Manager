#!/usr/bin/env python3
"""
Export PV, battery, load, and ambient (ESP32) readings from the MySQL database to CSV for LSTM training.
Ambient columns use the latest environment sample at or before each battery timestamp (as-of join).

Usage (from project root):
  python -m ai.scripts.export_readings --database-url mysql+aiomysql://... [--hours 168] [--output data/readings.csv]
"""
import argparse
import os
import sys
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
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

    df_b = pd.DataFrame(rows)
    df_b["timestamp"] = pd.to_datetime(df_b["timestamp"], utc=True)

    q_env = text(
        f"""
        SELECT timestamp, temperature_c, humidity_percent, light_digital
        FROM environment_readings
        WHERE timestamp >= DATE_SUB(UTC_TIMESTAMP(), INTERVAL {interval} HOUR)
        ORDER BY timestamp
        """
    )
    with engine.connect() as conn:
        env_rows = conn.execute(q_env).mappings().all()

    if env_rows:
        df_e = pd.DataFrame(env_rows)
        df_e["timestamp"] = pd.to_datetime(df_e["timestamp"], utc=True)
        df_e["light_digital"] = df_e["light_digital"].map(
            lambda x: 1.0 if x is True else (0.0 if x is False else np.nan)
        )
        df_e = df_e.sort_values("timestamp")
        df_b = df_b.sort_values("timestamp")
        df = pd.merge_asof(df_b, df_e, on="timestamp", direction="backward")
    else:
        df = df_b.sort_values("timestamp")
        df["temperature_c"] = np.nan
        df["humidity_percent"] = np.nan
        df["light_digital"] = np.nan

    out = output_path or "readings.csv"
    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cols = [
        "timestamp",
        "pv_kw",
        "soc_percent",
        "total_load_kw",
        "temperature_c",
        "humidity_percent",
        "light_digital",
    ]
    df.to_csv(out_path, index=False, columns=cols)
    print(f"Exported {len(df)} rows to {out_path}")


def main() -> None:
    p = argparse.ArgumentParser(description="Export microgrid readings to CSV for LSTM training")
    p.add_argument("--hours", type=int, default=168, help="Last N hours (default 168 = 1 week)")
    p.add_argument("--output", "-o", default="readings.csv", help="Output CSV path")
    p.add_argument("--database-url", default=None, help="MySQL SQLAlchemy database URL")
    args = p.parse_args()
    export(hours=args.hours, output_path=args.output, database_url=args.database_url)


if __name__ == "__main__":
    main()
