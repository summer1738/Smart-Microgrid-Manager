"""Forecast API: model-based when available, otherwise simulated."""
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_min_role
from app.config import settings
from app.database import get_db
from app.models import BatteryReading
from app.schemas import ForecastInsightsOut, ForecastOut, ForecastSeries, ModelMonitorOut
from app.services.auto_train_service import get_last_train_result
from app.services.descriptive_insights_service import (
    build_descriptive_insights,
    compute_live_forecast_metrics,
)
from app.services.forecast_service import (
    generate_forecast_with_weather,
    generate_hybrid_forecast,
    generate_long_range_generation_forecast,
)
from app.services.ml_forecast_service import inspect_forecast_models, try_model_forecast
from app.services.system_settings_service import get_auto_train_enabled
from app.services.weather_insights_service import build_weather_pv_insights

router = APIRouter(
    prefix="/forecast",
    tags=["forecast"],
    dependencies=[Depends(require_min_role("viewer"))],
)


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


@router.get("/insights", response_model=ForecastInsightsOut)
async def get_forecast_insights(
    horizon_hours: int = Query(24, ge=6, le=48),
    db: AsyncSession = Depends(get_db),
) -> ForecastInsightsOut:
    """
    Human-readable explanation layer for forecast, weather, schedule, and battery behavior.
    """
    payload = await build_descriptive_insights(
        db,
        horizon_hours=horizon_hours,
        include_weather_context=True,
    )
    return ForecastInsightsOut(**payload)


@router.get("/generation-long-range")
async def get_generation_long_range(
    forecast_days: int = Query(16, ge=1, le=16, description="Maximum supported long-range generation horizon."),
) -> dict:
    """
    Return expected PV production for as long as the weather provider can support.
    Currently this is up to 16 days (Open-Meteo limit).
    """
    return await generate_long_range_generation_forecast(forecast_days=forecast_days)


@router.get("/training-status", dependencies=[Depends(require_min_role("admin"))])
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
    Return 24-48h forecast.
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


@router.get("/monitor", response_model=ModelMonitorOut, dependencies=[Depends(require_min_role("admin"))])
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
        forecast_message = model[3]
        lstm_active = True
    else:
        _ts_sim, _gen_s, _cons_s, wmsg = await generate_forecast_with_weather(
            horizon_hours=horizon_hours,
            resolution_hours=1.0,
            base_ts=now,
        )
        forecast_message = wmsg
        lstm_active = False

    model_series = None
    simulated_series = None
    if compare:
        ts_sim, gen_sim, cons_sim, _ = await generate_forecast_with_weather(
            horizon_hours=horizon_hours,
            resolution_hours=1.0,
            base_ts=now,
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

    live_metrics = await compute_live_forecast_metrics(db, now=now, hours=24)
    merged_errors = list(errs)
    if not payload["models_load_ok"] and lstm_active:
        merged_errors.append("Unexpected: LSTM forecast ran but checkpoint inspection reported not ready.")

    narrative_forecast = model
    if narrative_forecast is None and simulated_series is not None:
        narrative_forecast = (
            simulated_series.timestamps,
            simulated_series.generation_kw,
            simulated_series.consumption_kw,
            forecast_message,
        )

    descriptive = await build_descriptive_insights(
        db,
        horizon_hours=horizon_hours,
        now=now,
        forecast_bundle=narrative_forecast,
        live_metrics=live_metrics,
        include_weather_context=False,
        model_active=lstm_active,
    )

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
        ieba_uses_simulated_forecast=False,
        lstm_forecast_active=lstm_active,
        forecast_message=forecast_message,
        inference_ms=round(inference_ms, 2),
        model_series=model_series,
        simulated_series=simulated_series,
        live_smape_gen=live_metrics.get("live_smape_gen"),
        live_smape_load=live_metrics.get("live_smape_load"),
        live_mape_masked_gen=live_metrics.get("live_mape_masked_gen"),
        live_mape_masked_load=live_metrics.get("live_mape_masked_load"),
        live_mae_gen=live_metrics.get("live_mae_gen"),
        live_mae_load=live_metrics.get("live_mae_load"),
        live_metrics_hours=live_metrics.get("hours"),
        descriptive_summary=descriptive["summary"],
        descriptive_insights=descriptive["insights"],
    )


@router.post("/monitor/train-now", dependencies=[Depends(require_min_role("admin"))])
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


@router.post("/monitor/train-now-async", dependencies=[Depends(require_min_role("admin"))])
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


@router.get("/monitor/train-now-progress", dependencies=[Depends(require_min_role("admin"))])
async def train_models_now_progress(job_id: Optional[str] = None) -> dict:
    """
    Poll training progress for the active manual job.
    """
    from app.services.auto_train_service import get_manual_train_job

    job = get_manual_train_job(job_id=job_id)
    if job is None:
        return {"ok": False, "message": "No active training job."}
    return {"ok": True, **job}
