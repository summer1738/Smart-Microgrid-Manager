"""Forecast API: model-based when available, otherwise simulated."""
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

import numpy as np
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import BatteryReading, LoadReading, PvReading
from app.schemas import ForecastOut, ForecastSeries, ModelMonitorOut
from app.services.forecast_service import (
    generate_forecast_with_weather,
    generate_hybrid_forecast,
    generate_long_range_generation_forecast,
)
from app.services.ml_forecast_service import inspect_forecast_models, try_model_forecast
from app.services.system_settings_service import get_auto_train_enabled
from app.services.auto_train_service import get_last_train_result
from app.services.weather_insights_service import build_weather_pv_insights

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


@router.get("/weather-insights")
async def get_weather_insights(
    forecast_days: int = Query(16, ge=7, le=16, description="Open-Meteo supports up to 16 days."),
    history_days: int = Query(30, ge=7, le=90),
    include_hourly: bool = Query(False, description="Include full hourly series (large JSON)."),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Extended weather summary (cloud, WMO code, irradiance) and expected PV energy by day
    from Open-Meteo, compared with actual daily PV energy from the database (past trends).
    """
    payload, summary = await build_weather_pv_insights(
        db,
        forecast_days=forecast_days,
        history_days=history_days,
        include_hourly=include_hourly,
    )
    payload["summary_message"] = summary
    return payload


@router.get("/generation-long-range")
async def get_generation_long_range(
    forecast_days: int = Query(16, ge=1, le=16, description="Maximum supported long-range generation horizon."),
) -> dict:
    """
    Return expected PV production for as long as the weather provider can support.
    Currently this is up to 16 days (Open-Meteo limit).
    """
    return await generate_long_range_generation_forecast(forecast_days=forecast_days)


@router.get("/training-status")
async def get_training_status(db: AsyncSession = Depends(get_db)) -> dict:
    """
    Preconditions for UI-driven LSTM training: DB sample count, PyTorch, scheduled auto-train flag.
    """
    r = await db.execute(select(func.count(BatteryReading.id)))
    n = int(r.scalar_one() or 0)
    torch_available = False
    try:
        import torch  # noqa: F401

        torch_available = True
    except Exception:
        pass
    auto_train = await get_auto_train_enabled()
    last_train = get_last_train_result()
    return {
        "battery_readings_count": n,
        "min_samples_required": int(settings.auto_train_min_samples),
        "enough_samples": n >= int(settings.auto_train_min_samples),
        "torch_available": torch_available,
        "auto_train_enabled": auto_train,
        "auto_train_interval_minutes": int(settings.auto_train_interval_minutes),
        "auto_train_history_hours": int(settings.auto_train_history_hours),
        "last_train": last_train,
        "pipeline_steps": [
            "Export readings from MySQL to CSV",
            "prepare_dataset (load + PV targets)",
            "lstm_train → ai/models/load_lstm.pt and gen_lstm.pt",
        ],
    }


@router.get("", response_model=ForecastOut)
async def get_forecast(horizon_hours: int = 24) -> ForecastOut:
    """
    Return 24–48h forecast.
    - If trained models exist in `ai/models/*.pt` and torch is installed, use them.
    - Otherwise, fall back to a simulated PV + demand curve.
    """
    now = datetime.now(timezone.utc)
    timestamps, generation_kw, consumption_kw, series_msg = await generate_hybrid_forecast(
        horizon_hours=horizon_hours,
        resolution_hours=1.0,
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
        message=series_msg,
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
    model = await try_model_forecast(horizon_hours=horizon_hours, resolution_hours=1.0, base_ts=now, db=db)
    inference_ms = (time.perf_counter() - t0) * 1000.0

    seed_from_db = False
    if model is not None:
        _ts, gen_kw, load_kw, msg, seed_from_db = model
        forecast_message = msg
        lstm_active = True
    else:
        _ts_sim, gen_s, cons_s, wmsg = await generate_forecast_with_weather(
            horizon_hours=horizon_hours, resolution_hours=1.0, base_ts=now
        )
        forecast_message = wmsg
        lstm_active = False

    model_series = None
    simulated_series = None
    if compare:
        ts_sim, gen_sim, cons_sim, _ = await generate_forecast_with_weather(
            horizon_hours=horizon_hours, resolution_hours=1.0, base_ts=now
        )
        simulated_series = ForecastSeries(
            timestamps=ts_sim,
            generation_kw=[round(x, 4) for x in gen_sim],
            consumption_kw=cons_sim,
        )
        if model is not None:
            ts_m, g_m, c_m, _, _ = model
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
            past_forecast = await try_model_forecast(
                horizon_hours=24, resolution_hours=1.0, base_ts=base_24h, db=db
            )
            if past_forecast is not None:
                _ts_p, pred_gen, pred_load, _, _ = past_forecast
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
    seed_src = "database" if (model is not None and seed_from_db) else "synthetic"
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
        seed_source=seed_src,
        ieba_uses_simulated_forecast=False,
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
    """
    from app.services.auto_train_service import get_global_auto_trainer

    trainer = get_global_auto_trainer()
    if trainer is None:
        return {
            "ok": False,
            "message": "Auto-trainer is not initialized.",
        }
    res = await trainer.train_now()
    out = res.output or ""
    tail = out[-16000:] if len(out) > 16000 else out
    return {"ok": bool(res.ok), "message": res.message, "output": tail}


@router.post("/monitor/train-now-async")
async def train_models_now_async() -> dict:
    """
    Start training in the background with step + streaming log tail progress.
    Returns the active job state.
    """
    from app.services.auto_train_service import get_global_auto_trainer

    trainer = get_global_auto_trainer()
    if trainer is None:
        return {
            "ok": False,
            "message": "Auto-trainer is not initialized.",
        }
    job = await trainer.start_manual_train_job()
    return {"ok": True, **job}


@router.get("/monitor/train-now-progress")
async def train_models_now_progress(job_id: Optional[str] = None) -> dict:
    """
    Poll training progress for the active manual job.
    """
    from app.services.auto_train_service import get_manual_train_job

    job = get_manual_train_job(job_id=job_id)
    if job is None:
        return {"ok": False, "message": "No active training job."}
    return {"ok": True, **job}
