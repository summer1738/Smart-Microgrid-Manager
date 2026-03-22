#!/usr/bin/env python3
"""
Train a simple LSTM regressor in PyTorch from a prepared .npz dataset.

Output: a Torch checkpoint (.pt) with:
  - model_state
  - feature_names
  - seq_len
  - scaler stats (mean/std) for features + target

Usage:
  python -m ai.training.lstm_train --dataset ai/data/load_ds.npz --out ai/models/load_lstm.pt
"""

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Tuple

import numpy as np


def _require_torch():
    import torch  # noqa
    return torch


@dataclass
class Standardizer:
    mean: np.ndarray
    std: np.ndarray

    def transform(self, x: np.ndarray) -> np.ndarray:
        return (x - self.mean) / (self.std + 1e-8)

    def inverse(self, x: np.ndarray) -> np.ndarray:
        return x * (self.std + 1e-8) + self.mean


def fit_standardizer(x: np.ndarray) -> Standardizer:
    mean = x.mean(axis=0)
    std = x.std(axis=0)
    return Standardizer(mean=mean, std=std)


def main() -> None:
    torch = _require_torch()
    import torch.nn as nn
    from torch.utils.data import DataLoader, TensorDataset

    p = argparse.ArgumentParser()
    p.add_argument("--dataset", required=True, help="Input .npz from prepare_dataset.py")
    p.add_argument("--out", required=True, help="Output .pt path")
    p.add_argument("--epochs", type=int, default=20)
    p.add_argument("--batch-size", type=int, default=128)
    p.add_argument("--hidden", type=int, default=64)
    p.add_argument("--lr", type=float, default=1e-3)
    args = p.parse_args()

    data = np.load(args.dataset, allow_pickle=True)
    X = data["X"].astype(np.float32)  # (N, seq, feat)
    y = data["y"].astype(np.float32)  # (N,)
    feature_names = [str(x) for x in data["feature_names"].tolist()]
    seq_len = X.shape[1]
    feat_dim = X.shape[2]

    if X.shape[0] < 100:
        raise SystemExit("Not enough samples. Generate more simulation data then re-export + prepare dataset.")

    # Standardize features and target
    X_flat = X.reshape(-1, feat_dim)
    x_scaler = fit_standardizer(X_flat)
    Xs = x_scaler.transform(X_flat).reshape(X.shape)
    y_scaler = fit_standardizer(y.reshape(-1, 1))
    ys = y_scaler.transform(y.reshape(-1, 1)).reshape(-1)

    # Train/val split
    n = Xs.shape[0]
    split = int(n * 0.8)
    X_train, X_val = Xs[:split], Xs[split:]
    y_train, y_val = ys[:split], ys[split:]

    train_ds = TensorDataset(torch.from_numpy(X_train), torch.from_numpy(y_train))
    val_ds = TensorDataset(torch.from_numpy(X_val), torch.from_numpy(y_val))
    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=args.batch_size, shuffle=False)

    class LSTMRegressor(nn.Module):
        def __init__(self, input_dim: int, hidden: int):
            super().__init__()
            self.lstm = nn.LSTM(input_size=input_dim, hidden_size=hidden, batch_first=True)
            self.head = nn.Sequential(
                nn.Linear(hidden, hidden // 2),
                nn.ReLU(),
                nn.Linear(hidden // 2, 1),
            )

        def forward(self, x):
            out, _ = self.lstm(x)
            last = out[:, -1, :]
            return self.head(last).squeeze(-1)

    device = torch.device("cpu")
    model = LSTMRegressor(feat_dim, args.hidden).to(device)
    opt = torch.optim.Adam(model.parameters(), lr=args.lr)
    loss_fn = nn.MSELoss()

    def eval_mse(loader):
        model.eval()
        total = 0.0
        count = 0
        with torch.no_grad():
            for xb, yb in loader:
                xb = xb.to(device)
                yb = yb.to(device)
                pred = model(xb)
                loss = loss_fn(pred, yb)
                total += float(loss) * xb.size(0)
                count += xb.size(0)
        return total / max(1, count)

    def eval_validation_metrics(loader):
        """
        Metrics in original target scale (kW).

        - sMAPE: symmetric MAPE — stable when actual is near zero (unlike classic MAPE).
        - mape_masked: classic MAPE only where |actual| >= min_y_kw (avoids night / zero-PV blowups).
        """
        model.eval()
        preds, actuals = [], []
        with torch.no_grad():
            for xb, yb in loader:
                xb = xb.to(device)
                pred_std = model(xb).cpu().numpy()
                preds.append(y_scaler.inverse(pred_std.reshape(-1, 1)).ravel())
                actuals.append(y_scaler.inverse(yb.cpu().numpy().reshape(-1, 1)).ravel())
        p = np.concatenate(preds)
        a = np.concatenate(actuals)
        eps = 1e-6
        # Symmetric MAPE (%), bounded ~0–200 for typical cases
        smape = float(np.mean(2.0 * np.abs(a - p) / (np.abs(a) + np.abs(p) + eps)) * 100.0)
        mae = float(np.mean(np.abs(a - p)))
        min_y_kw = 0.02
        mask = np.abs(a) >= min_y_kw
        if np.sum(mask) >= 5:
            mape_masked = float(
                np.mean(np.abs(a[mask] - p[mask]) / (np.abs(a[mask]) + eps)) * 100.0
            )
        else:
            mape_masked = None
        return smape, mae, mape_masked

    best_val = float("inf")
    for epoch in range(1, args.epochs + 1):
        model.train()
        for xb, yb in train_loader:
            xb = xb.to(device)
            yb = yb.to(device)
            opt.zero_grad()
            pred = model(xb)
            loss = loss_fn(pred, yb)
            loss.backward()
            opt.step()
        val_mse = eval_mse(val_loader)
        if val_mse < best_val:
            best_val = val_mse
        print(f"epoch {epoch}/{args.epochs} val_mse={val_mse:.5f}")

    val_smape, val_mae, val_mape_masked = eval_validation_metrics(val_loader)
    masked_str = f"{val_mape_masked:.2f}%" if val_mape_masked is not None else "n/a"
    print(f"Validation sMAPE={val_smape:.2f}%  MAPE(|y|≥0.02kW)={masked_str}  MAE={val_mae:.4f}")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "model_state": model.state_dict(),
            "seq_len": seq_len,
            "feat_dim": feat_dim,
            "hidden": args.hidden,
            "feature_names": feature_names,
            "x_mean": x_scaler.mean.astype(np.float32),
            "x_std": x_scaler.std.astype(np.float32),
            "y_mean": y_scaler.mean.astype(np.float32),
            "y_std": y_scaler.std.astype(np.float32),
            "validation_smape": float(val_smape),
            "validation_mae": float(val_mae),
            **({"validation_mape_masked": float(val_mape_masked)} if val_mape_masked is not None else {}),
        },
        out,
    )
    print(f"Saved model to {out}")


if __name__ == "__main__":
    main()

