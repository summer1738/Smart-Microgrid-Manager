"""
Model-based forecast service.

If Torch models exist and torch is installed, this will produce a multi-step forecast
by autoregressive rollout. Otherwise the API falls back to simulated forecasts.

Models are trained using ai/training/* scripts and saved as .pt checkpoints.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np


@dataclass
class TorchLSTMCheckpoint:
    path: Path
    seq_len: int
    feat_dim: int
    hidden: int
    feature_names: List[str]
    x_mean: np.ndarray
    x_std: np.ndarray
    y_mean: float
    y_std: float
    model: object
    validation_smape: Optional[float] = None
    validation_mape_masked: Optional[float] = None
    validation_mae: Optional[float] = None
    validation_mape_legacy: Optional[float] = None  # old checkpoints: classic MAPE (often misleading for PV)


def _try_import_torch():
    try:
        import torch  # type: ignore
        import torch.nn as nn  # type: ignore
        return torch, nn
    except Exception:
        return None, None


def _default_model_dir() -> Path:
    # backend/app/services -> backend -> project root (smart-microgrid-manager)
    return Path(__file__).resolve().parents[3] / "ai" / "models"


def _load_checkpoint(path: Path) -> Optional[TorchLSTMCheckpoint]:
    torch, nn = _try_import_torch()
    if torch is None or nn is None:
        return None
    if not path.exists():
        return None
    ckpt = torch.load(path, map_location="cpu")

    class LSTMRegressor(nn.Module):
        def __init__(self, input_dim: int, hidden: int):
            super().__init__()
            self.lstm = nn.LSTM(input_size=input_dim, hidden_size=hidden, batch_first=True)
            self.head = nn.Sequential(
                nn.Linear(hidden, max(1, hidden // 2)),
                nn.ReLU(),
                nn.Linear(max(1, hidden // 2), 1),
            )

        def forward(self, x):
            out, _ = self.lstm(x)
            last = out[:, -1, :]
            return self.head(last).squeeze(-1)

    model = LSTMRegressor(int(ckpt["feat_dim"]), int(ckpt["hidden"]))
    model.load_state_dict(ckpt["model_state"])
    model.eval()

    return TorchLSTMCheckpoint(
        path=path,
        seq_len=int(ckpt["seq_len"]),
        feat_dim=int(ckpt["feat_dim"]),
        hidden=int(ckpt["hidden"]),
        feature_names=[str(x) for x in ckpt["feature_names"]],
        x_mean=np.array(ckpt["x_mean"], dtype=np.float32),
        x_std=np.array(ckpt["x_std"], dtype=np.float32),
        y_mean=float(np.array(ckpt["y_mean"]).reshape(-1)[0]),
        y_std=float(np.array(ckpt["y_std"]).reshape(-1)[0]),
        model=model,
        validation_smape=float(ckpt["validation_smape"]) if "validation_smape" in ckpt else None,
        validation_mape_masked=float(ckpt["validation_mape_masked"]) if "validation_mape_masked" in ckpt else None,
        validation_mae=float(ckpt["validation_mae"]) if "validation_mae" in ckpt else None,
        validation_mape_legacy=float(ckpt["validation_mape"])
        if "validation_mape" in ckpt and "validation_smape" not in ckpt
        else None,
    )


def _make_time_features(ts: datetime) -> Tuple[float, float]:
    hour = ts.hour + ts.minute / 60.0
    angle = 2.0 * np.pi * (hour / 24.0)
    return float(np.sin(angle)), float(np.cos(angle))


def _standardize(x: np.ndarray, mean: np.ndarray, std: np.ndarray) -> np.ndarray:
    return (x - mean) / (std + 1e-8)


def _inv_standardize(y: float, mean: float, std: float) -> float:
    return float(y * (std + 1e-8) + mean)


def autoregressive_forecast(
    model_ckpt: TorchLSTMCheckpoint,
    seed_window: np.ndarray,
    base_ts: datetime,
    horizon_steps: int,
    step_hours: float = 1.0,
) -> Tuple[List[str], List[float]]:
    """
    Roll out horizon_steps forecasts. seed_window shape: (seq_len, feat_dim).
    The output is a list of timestamps and predicted target values.

    Important: this uses a simple strategy: after predicting y_t, we overwrite the
    target feature in the next step's input if it exists (pv_kw or total_load_kw).
    """
    torch, _ = _try_import_torch()
    if torch is None:
        return [], []

    X = seed_window.astype(np.float32).copy()
    ts_list = []
    y_list = []

    # Identify which feature corresponds to the predicted target if present
    # (we trained on full feature window; target is one of the numeric columns)
    target_feature_idx = None
    for i, name in enumerate(model_ckpt.feature_names):
        if name in ("pv_kw", "total_load_kw"):
            # We can't know which target this model was trained for, so caller should seed appropriately.
            # We'll still allow overwriting by providing the desired idx explicitly later if needed.
            pass

    for k in range(horizon_steps):
        ts = base_ts + timedelta(hours=k * step_hours)
        sin_h, cos_h = _make_time_features(ts)

        # Update time features in the last row of the window
        # feature_names includes sin_hour/cos_hour
        try:
            sin_idx = model_ckpt.feature_names.index("sin_hour")
            cos_idx = model_ckpt.feature_names.index("cos_hour")
            X[-1, sin_idx] = sin_h
            X[-1, cos_idx] = cos_h
        except ValueError:
            pass

        Xs = _standardize(X, model_ckpt.x_mean, model_ckpt.x_std)
        xb = torch.from_numpy(Xs).unsqueeze(0)  # (1, seq, feat)
        with torch.no_grad():
            y_std = float(model_ckpt.model(xb).cpu().numpy().reshape(-1)[0])
        y = _inv_standardize(y_std, model_ckpt.y_mean, model_ckpt.y_std)

        ts_list.append(ts.isoformat())
        y_list.append(max(0.0, float(y)))

        # Shift window and append a new row copied from last row
        X = np.roll(X, shift=-1, axis=0)
        X[-1, :] = X[-2, :]
        # Caller can overwrite the correct feature in seed_window before calling,
        # and we also overwrite any matching numeric column if present.
        if "pv_kw" in model_ckpt.feature_names:
            idx = model_ckpt.feature_names.index("pv_kw")
            X[-1, idx] = y_list[-1]
        if "total_load_kw" in model_ckpt.feature_names:
            idx = model_ckpt.feature_names.index("total_load_kw")
            X[-1, idx] = y_list[-1]

    return ts_list, y_list


def try_model_forecast(
    horizon_hours: int = 24,
    resolution_hours: float = 1.0,
    base_ts: Optional[datetime] = None,
    load_model_path: Optional[str] = None,
    gen_model_path: Optional[str] = None,
) -> Optional[Tuple[List[str], List[float], List[float], str]]:
    """
    If models exist, return (timestamps, gen_kw, load_kw, message). Otherwise None.
    Seed window is currently synthetic; once you have real history, we will seed from DB.
    """
    base_ts = base_ts or datetime.now(timezone.utc)
    steps = max(1, int(horizon_hours / resolution_hours))

    model_dir = _default_model_dir()
    gen_path = Path(gen_model_path) if gen_model_path else (model_dir / "gen_lstm.pt")
    load_path = Path(load_model_path) if load_model_path else (model_dir / "load_lstm.pt")

    gen_ckpt = _load_checkpoint(gen_path)
    load_ckpt = _load_checkpoint(load_path)
    if gen_ckpt is None or load_ckpt is None:
        return None

    # Synthetic seed window (will be replaced with DB-derived window)
    def seed_window(ckpt: TorchLSTMCheckpoint, initial_pv: float, initial_soc: float, initial_load: float) -> np.ndarray:
        X = np.zeros((ckpt.seq_len, ckpt.feat_dim), dtype=np.float32)
        for t in range(ckpt.seq_len):
            ts = base_ts - timedelta(hours=(ckpt.seq_len - t) * resolution_hours)
            sin_h, cos_h = _make_time_features(ts)
            for j, name in enumerate(ckpt.feature_names):
                if name == "pv_kw":
                    X[t, j] = initial_pv
                elif name == "soc_percent":
                    X[t, j] = initial_soc
                elif name == "total_load_kw":
                    X[t, j] = initial_load
                elif name == "sin_hour":
                    X[t, j] = sin_h
                elif name == "cos_hour":
                    X[t, j] = cos_h
        return X

    gen_seed = seed_window(gen_ckpt, initial_pv=0.2, initial_soc=70.0, initial_load=0.2)
    load_seed = seed_window(load_ckpt, initial_pv=0.2, initial_soc=70.0, initial_load=0.2)

    ts_gen, gen_vals = autoregressive_forecast(gen_ckpt, gen_seed, base_ts, steps, step_hours=resolution_hours)
    ts_load, load_vals = autoregressive_forecast(load_ckpt, load_seed, base_ts, steps, step_hours=resolution_hours)

    # Use gen timestamps as canonical
    ts = ts_gen or ts_load
    if not ts:
        return None

    msg = f"Model forecast loaded (gen: {gen_ckpt.path.name}, load: {load_ckpt.path.name})."
    return ts, gen_vals[: len(ts)], load_vals[: len(ts)], msg


def inspect_forecast_models(
    gen_model_path: Optional[str] = None,
    load_model_path: Optional[str] = None,
) -> Tuple[dict, List[str]]:
    """
    Diagnostics for the Forecast UI monitor page.
    Returns (payload_dict, list_of_human_errors).
    """
    errors: List[str] = []
    model_dir = _default_model_dir()
    gen_path = Path(gen_model_path) if gen_model_path else (model_dir / "gen_lstm.pt")
    load_path = Path(load_model_path) if load_model_path else (model_dir / "load_lstm.pt")

    torch, _ = _try_import_torch()
    torch_available = torch is not None
    if not torch_available:
        errors.append("PyTorch is not installed or failed to import (install torch in the backend venv).")

    def meta_for(path: Path) -> Optional[dict]:
        if not path.exists():
            return None
        try:
            ckpt = _load_checkpoint(path)
            if ckpt is None:
                errors.append(f"{path.name}: could not load (torch missing or invalid checkpoint).")
                return None
            meta = {
                "path": str(path),
                "seq_len": ckpt.seq_len,
                "feat_dim": ckpt.feat_dim,
                "hidden": ckpt.hidden,
                "feature_names": ckpt.feature_names,
            }
            if ckpt.validation_smape is not None:
                meta["validation_smape"] = ckpt.validation_smape
            if ckpt.validation_mape_masked is not None:
                meta["validation_mape_masked"] = ckpt.validation_mape_masked
            if ckpt.validation_mae is not None:
                meta["validation_mae"] = ckpt.validation_mae
            if ckpt.validation_mape_legacy is not None:
                meta["validation_mape_legacy"] = ckpt.validation_mape_legacy
            return meta
        except Exception as e:  # noqa: BLE001
            errors.append(f"{path.name}: {e!s}")
            return None

    gen_meta = meta_for(gen_path) if torch_available else None
    load_meta = meta_for(load_path) if torch_available else None
    if torch_available and not gen_path.exists():
        errors.append(f"Generation model file not found: {gen_path}")
    if torch_available and not load_path.exists():
        errors.append(f"Load model file not found: {load_path}")

    models_load_ok = gen_meta is not None and load_meta is not None

    return {
        "torch_available": torch_available,
        "gen_path": str(gen_path.resolve()),
        "load_path": str(load_path.resolve()),
        "gen_file_exists": gen_path.exists(),
        "load_file_exists": load_path.exists(),
        "models_load_ok": models_load_ok,
        "gen": gen_meta,
        "load": load_meta,
        "seed_source": "synthetic",
    }, errors

