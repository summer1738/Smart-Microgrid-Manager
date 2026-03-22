"""Forecast API: model-based when available, otherwise simulated."""
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

import numpy as np
from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import BatteryReading, LoadReading, PvReading
from app.schemas import ForecastOut, ForecastSeries, ModelMonitorOut
from app.services.forecast_service import generate_simulated_forecast
from app.services.ml_forecast_service import inspect_forecast_models, try_model_forecast

router = APIRouter(prefix="/forecast", tags=["forecast"])


def _compute_live_metrics(
    actual: list, pred: list, eps: float = 1e-6, min_y_kw: float = 0.02
) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """
    sMAPE (%), classic MAPE (%) on |actual|>=min_y_kw only, MAE (kW).
    Uses pairs where both actual and pred are non-None.
    """
    a, p = [], []
    for i in range(min(len(actual), len(pred))):
        av = actual[i] if i < len(actual) else None
        pv = pred[i] if i < len(pred) else None
        if av is not None and pv is not None:
            a.append(float(av))
            p.append(float(pv))
    if not a:
        return None, None, None
    a_arr = np.array(a)
    p_arr = np.array(p)
    smape = float(np.mean(2.0 * np.abs(a_arr - p_arr) / (np.abs(a_arr) + np.abs(p_arr) + eps)) * 100.0)
    mae = float(np.mean(np.abs(a_arr - p_arr)))
    mask = np.abs(a_arr) >= min_y_kw
    if np.sum(mask) >= 3:
        mape_masked = float(np.mean(np.abs(a_arr[mask] - p_arr[mask]) / (np.abs(a_arr[mask]) + eps)) * 100.0)
    else:
        mape_masked = None
    return smape, mape_masked, mae


@router.get("", response_model=ForecastOut)
async def get_forecast(horizon_hours: int = 24) -> ForecastOut:
    """
    Return 24–48h forecast.
    - If trained models exist in `ai/models/*.pt` and torch is installed, use them.
    - Otherwise, fall back to a simulated PV + demand curve.
    """
    now = datetime.now(timezone.utc)
    model = try_model_forecast(horizon_hours=horizon_hours, resolution_hours=1.0, base_ts=now)
    if model is not None:
        timestamps, gen_kw, load_kw, msg = model
        return ForecastOut(
            generated_at=now,
            horizon_hours=horizon_hours,
            series=ForecastSeries(
                timestamps=timestamps,
                generation_kw=[round(x, 4) for x in gen_kw],
                consumption_kw=[round(x, 4) for x in load_kw],
            ),
            message=msg,
        )
    timestamps, generation_kw, consumption_kw = generate_simulated_forecast(
        horizon_hours=horizon_hours,
        resolution_hours=1.0,
        pv_capacity_kw=1.0,
        cloud_factor=0.9,
        base_ts=now,
    )
    return ForecastOut(
        generated_at=now,
        horizon_hours=horizon_hours,
        series=ForecastSeries(
            timestamps=timestamps,
            generation_kw=[round(x, 4) for x in generation_kw],
            consumption_kw=consumption_kw,
        ),
        message="Simulated forecast (no trained LSTM models found).",
    )


@router.get("/monitor", response_model=ModelMonitorOut)
async def get_model_monitor(
    horizon_hours: int = 24,
    compare: bool = False,
    db: AsyncSession = Depends(get_db),
) -> ModelMonitorOut:
    """
    Inspect LSTM checkpoints, PyTorch, and whether /forecast uses the model.
    Set compare=true to include model vs simulated series (for overlay charts).
    When LSTM is active, computes live MAPE/MAE vs actual DB history for the last 24h.
    """
    payload, errs = inspect_forecast_models()
    now = datetime.now(timezone.utc)

    t0 = time.perf_counter()
    model = try_model_forecast(horizon_hours=horizon_hours, resolution_hours=1.0, base_ts=now)
    inference_ms = (time.perf_counter() - t0) * 1000.0

    if model is not None:
        _ts, gen_kw, load_kw, msg = model
        forecast_message = msg
        lstm_active = True
    else:
        _ts_sim, gen_s, cons_s = generate_simulated_forecast(
            horizon_hours=horizon_hours, resolution_hours=1.0, base_ts=now
        )
        forecast_message = "Simulated forecast (LSTM not used)."
        lstm_active = False

    model_series = None
    simulated_series = None
    if compare:
        ts_sim, gen_sim, cons_sim = generate_simulated_forecast(
            horizon_hours=horizon_hours, resolution_hours=1.0, base_ts=now
        )
        simulated_series = ForecastSeries(
            timestamps=ts_sim,
            generation_kw=[round(x, 4) for x in gen_sim],
            consumption_kw=cons_sim,
        )
        if model is not None:
            ts_m, g_m, c_m, _ = model
            model_series = ForecastSeries(
                timestamps=ts_m,
                generation_kw=[round(x, 4) for x in g_m],
                consumption_kw=[round(x, 4) for x in c_m],
            )

    # Live metrics: model forecast for past 24h vs actual history (hourly buckets)
    live_smape_gen, live_smape_load = None, None
    live_mape_masked_gen, live_mape_masked_load = None, None
    live_mae_gen, live_mae_load = None, None
    live_metrics_hours = None
    if lstm_active and model is not None:
        since = now - timedelta(hours=24)
        bat = await db.execute(
            select(BatteryReading.timestamp, BatteryReading.soc_percent)
            .where(BatteryReading.timestamp >= since)
            .order_by(BatteryReading.timestamp)
        )
        battery_rows = bat.all()
        if battery_rows:
            timestamps = [r[0] for r in battery_rows]
            pv_by_ts = {}
            pv_readings = await db.execute(
                select(PvReading.timestamp, PvReading.power_kw).where(PvReading.timestamp >= since)
            )
            for ts, kw in pv_readings.all():
                pv_by_ts[ts] = kw
            load_by_ts = {}
            load_agg = await db.execute(
                select(LoadReading.timestamp, func.sum(LoadReading.power_kw))
                .where(LoadReading.timestamp >= since)
                .group_by(LoadReading.timestamp)
            )
            for ts, kw in load_agg.all():
                load_by_ts[ts] = float(kw) if kw is not None else 0.0
            # Bucket by hour (UTC)
            bucket_pv: dict = defaultdict(list)
            bucket_load: dict = defaultdict(list)
            for ts in timestamps:
                bucket = ts.replace(minute=0, second=0, microsecond=0)
                pv = pv_by_ts.get(ts)
                if pv is not None:
                    bucket_pv[bucket].append(pv)
                ld = load_by_ts.get(ts)
                if ld is not None:
                    bucket_load[bucket].append(ld)
            base_24h = (now - timedelta(hours=24)).replace(minute=0, second=0, microsecond=0)
            actual_gen = []
            actual_load = []
            for h in range(24):
                b = base_24h + timedelta(hours=h)
                actual_gen.append(np.mean(bucket_pv[b]) if bucket_pv[b] else None)
                actual_load.append(np.mean(bucket_load[b]) if bucket_load[b] else None)
            past_forecast = try_model_forecast(horizon_hours=24, resolution_hours=1.0, base_ts=base_24h)
            if past_forecast is not None:
                _ts_p, pred_gen, pred_load, _ = past_forecast
                live_smape_gen, live_mape_masked_gen, live_mae_gen = _compute_live_metrics(actual_gen, pred_gen)
                live_smape_load, live_mape_masked_load, live_mae_load = _compute_live_metrics(actual_load, pred_load)
                live_metrics_hours = 24
                if live_smape_gen is not None:
                    live_smape_gen = round(live_smape_gen, 2)
                if live_smape_load is not None:
                    live_smape_load = round(live_smape_load, 2)
                if live_mape_masked_gen is not None:
                    live_mape_masked_gen = round(live_mape_masked_gen, 2)
                if live_mape_masked_load is not None:
                    live_mape_masked_load = round(live_mape_masked_load, 2)
                if live_mae_gen is not None:
                    live_mae_gen = round(live_mae_gen, 4)
                if live_mae_load is not None:
                    live_mae_load = round(live_mae_load, 4)

    merged_errors = list(errs)
    if not payload["models_load_ok"] and lstm_active:
        merged_errors.append("Unexpected: LSTM forecast ran but checkpoint inspection reported not ready.")

    gen_info = payload.get("gen")
    load_info = payload.get("load")
    return ModelMonitorOut(
        torch_available=payload["torch_available"],
        gen_path=payload["gen_path"],
        load_path=payload["load_path"],
        gen_file_exists=payload["gen_file_exists"],
        load_file_exists=payload["load_file_exists"],
        models_load_ok=payload["models_load_ok"],
        gen=gen_info,
        load=load_info,
        errors=merged_errors,
        seed_source=str(payload.get("seed_source", "synthetic")),
        ieba_uses_simulated_forecast=True,
        lstm_forecast_active=lstm_active,
        forecast_message=forecast_message,
        inference_ms=round(inference_ms, 2),
        model_series=model_series,
        simulated_series=simulated_series,
        live_smape_gen=live_smape_gen,
        live_smape_load=live_smape_load,
        live_mape_masked_gen=live_mape_masked_gen,
        live_mape_masked_load=live_mape_masked_load,
        live_mae_gen=live_mae_gen,
        live_mae_load=live_mae_load,
        live_metrics_hours=live_metrics_hours,
    )


@router.post("/monitor/train-now")
async def train_models_now() -> dict:
    """
    Trigger one immediate training attempt (same logic as auto-train loop).
    Requires MICROGRID_AUTO_TRAIN_ENABLED=true so the trainer is running.
    """
    from app.services.auto_train_service import get_global_auto_trainer

    trainer = get_global_auto_trainer()
    if trainer is None:
        return {
            "ok": False,
            "message": "Auto-trainer is not running. Start backend with MICROGRID_AUTO_TRAIN_ENABLED=true.",
        }
    res = await trainer.train_now()
    return {"ok": bool(res.ok), "message": res.message, "output": res.output[-4000:]}
