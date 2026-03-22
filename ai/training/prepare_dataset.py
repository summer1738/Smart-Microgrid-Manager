#!/usr/bin/env python3
"""
Prepare a supervised sequence dataset from exported readings.csv.

Input CSV columns:
  timestamp, pv_kw, soc_percent, total_load_kw

Output:
  .npz file with arrays suitable for LSTM training:
    X: (N, seq_len, num_features)
    y: (N,) target next-step value
    feature_names: list[str]

Usage (from project root):
  python -m ai.training.prepare_dataset --input readings.csv --output ai/data/load_ds.npz --target total_load_kw
  python -m ai.training.prepare_dataset --input readings.csv --output ai/data/gen_ds.npz  --target pv_kw
"""

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

import numpy as np
import pandas as pd


def _time_features(ts: pd.Series) -> Tuple[np.ndarray, np.ndarray]:
    # hour-of-day cyclic encoding
    hour = ts.dt.hour.to_numpy() + ts.dt.minute.to_numpy() / 60.0
    angle = 2.0 * np.pi * (hour / 24.0)
    return np.sin(angle), np.cos(angle)


@dataclass
class DatasetOut:
    X: np.ndarray
    y: np.ndarray
    feature_names: List[str]


def build_sequence_dataset(
    df: pd.DataFrame,
    target_col: str,
    seq_len: int = 48,
) -> DatasetOut:
    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df = df.dropna(subset=["timestamp"]).sort_values("timestamp")

    # Basic numeric cleaning
    for c in ["pv_kw", "soc_percent", "total_load_kw"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)

    sin_h, cos_h = _time_features(df["timestamp"])
    df["sin_hour"] = sin_h
    df["cos_hour"] = cos_h

    # Features available from simulation/hardware
    feature_names = ["pv_kw", "soc_percent", "total_load_kw", "sin_hour", "cos_hour"]
    features = df[feature_names].to_numpy(dtype=np.float32)
    target = df[target_col].to_numpy(dtype=np.float32)

    X_list = []
    y_list = []
    for i in range(seq_len, len(df) - 1):
        X_list.append(features[i - seq_len : i])
        y_list.append(target[i])  # predict current step from previous window

    if not X_list:
        return DatasetOut(X=np.zeros((0, seq_len, len(feature_names)), dtype=np.float32), y=np.zeros((0,), dtype=np.float32), feature_names=feature_names)

    X = np.stack(X_list, axis=0)
    y = np.array(y_list, dtype=np.float32)
    return DatasetOut(X=X, y=y, feature_names=feature_names)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True, help="Input readings CSV (from export_readings.py)")
    p.add_argument("--output", required=True, help="Output .npz path")
    p.add_argument("--target", required=True, choices=["pv_kw", "total_load_kw"], help="Target column to predict")
    p.add_argument("--seq-len", type=int, default=48, help="Sequence length (default 48)")
    args = p.parse_args()

    inp = Path(args.input)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(inp)
    ds = build_sequence_dataset(df, target_col=args.target, seq_len=args.seq_len)
    np.savez_compressed(out, X=ds.X, y=ds.y, feature_names=np.array(ds.feature_names, dtype=object))
    print(f"Saved {ds.X.shape[0]} samples to {out}")


if __name__ == "__main__":
    main()

