"""
Optional background auto-train loop for LSTM checkpoints.

This runs inside the backend process (env-var gated). It will:
- export readings from the MySQL database to CSV
- prepare sequence datasets (gen + load)
- train and overwrite ai/models/{gen_lstm,load_lstm}.pt

Notes:
- This is intentionally simple and uses subprocess calls to the existing ai/* scripts.
- Training can be CPU-heavy; keep it disabled by default.
"""

from __future__ import annotations

import asyncio
import os
import sys
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional, Tuple
from sqlalchemy import create_engine, text

from app.config import settings
from app.db_url import to_sync_database_url
from app.services.system_settings_service import get_auto_train_enabled, set_auto_train_enabled

import logging

log = logging.getLogger("app.auto_train")

def _project_root() -> Path:
    # backend/app/services -> backend -> project root (smart-microgrid-manager)
    return Path(__file__).resolve().parents[3]


def _count_rows() -> int:
    try:
        engine = create_engine(to_sync_database_url(str(settings.database_url)))
        with engine.connect() as conn:
            row = conn.execute(text("SELECT COUNT(*) FROM battery_readings")).scalar()
            return int(row or 0)
    except Exception:
        return 0


async def _run_cmd(args: list[str], cwd: Path, timeout_s: int) -> Tuple[int, str]:
    """
    Run a subprocess and capture combined output.
    Returns (exit_code, output).
    """
    proc = await asyncio.create_subprocess_exec(
        *args,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env={**os.environ, "PYTHONPATH": os.environ.get("PYTHONPATH", "")},
    )
    try:
        out_b, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
    except asyncio.TimeoutError:
        proc.kill()
        try:
            await proc.wait()
        except Exception:
            pass
        return 124, "Timed out"
    out = (out_b or b"").decode("utf-8", errors="replace")
    return int(proc.returncode or 0), out


async def _run_cmd_stream(
    args: list[str],
    cwd: Path,
    timeout_s: int,
    on_line: Optional[Callable[[str], Any]] = None,
    max_output_chars: int = 500000,
) -> Tuple[int, str]:
    """
    Run a subprocess and stream combined stdout/stderr line-by-line.
    Returns (exit_code, full_output_truncated).
    """
    proc = await asyncio.create_subprocess_exec(
        *args,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env={**os.environ, "PYTHONPATH": os.environ.get("PYTHONPATH", "")},
    )

    # Keep only a rolling tail; avoid blocking the child process due to backpressure.
    tail = ""

    async def _read_stdout() -> None:
        nonlocal tail
        assert proc.stdout is not None
        while True:
            line_b = await proc.stdout.readline()
            if not line_b:
                break
            line = line_b.decode("utf-8", errors="replace")
            if on_line is not None:
                try:
                    on_line(line)
                except Exception:
                    # on_line is best-effort; never kill training because of UI callback.
                    pass
            if max_output_chars and max_output_chars > 0:
                tail = (tail + line)[-max_output_chars:]
            else:
                # Unbounded tail (not recommended); keep appending.
                tail += line

    reader_task = asyncio.create_task(_read_stdout())
    try:
        await asyncio.wait_for(proc.wait(), timeout=timeout_s)
    except asyncio.TimeoutError:
        proc.kill()
        try:
            await proc.wait()
        except Exception:
            pass
        await reader_task
        if on_line is not None:
            try:
                on_line("\n[training] Timed out\n")
            except Exception:
                pass
        return 124, tail[-max_output_chars:] if max_output_chars else tail

    await reader_task
    return int(proc.returncode or 0), tail


@dataclass
class AutoTrainResult:
    ok: bool
    message: str
    output: str = ""


@dataclass
class ManualTrainJob:
    id: str
    state: str = "queued"  # queued / running / done / failed
    current_step: int = 0
    current_label: str = ""
    progress: float = 0.0  # 0..100
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    ok: Optional[bool] = None
    message: Optional[str] = None
    log_tail: str = ""


class AutoTrainLoop:
    def __init__(self) -> None:
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()
        self._running = asyncio.Lock()

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stop.set()
        await self._task
        self._task = None

    async def _run(self) -> None:
        interval = max(5, int(settings.auto_train_interval_minutes)) * 60
        while not self._stop.is_set():
            try:
                if await get_auto_train_enabled():
                    async with self._running:
                        res = await self._maybe_train_once()
                        log.info("auto-train run done ok=%s message=%s", res.ok, res.message)
                        if res.output and not res.ok:
                            log.warning("auto-train output tail:\n%s", res.output[-8000:])
                        if res.ok:
                            await _maybe_stop_auto_train_on_mape(res.output or "")
            except Exception as e:  # noqa: BLE001
                log.exception("auto-train loop exception: %s", e)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=interval)
            except asyncio.TimeoutError:
                continue

    async def _maybe_train_once(self) -> AutoTrainResult:
        root = _project_root()
        n_rows = _count_rows()
        if n_rows < int(settings.auto_train_min_samples):
            res = AutoTrainResult(
                ok=False,
                message=f"Not enough DB samples yet ({n_rows} < {settings.auto_train_min_samples}).",
            )
            _set_last_train_result(res)
            return res

        # Quick torch import check (avoid spawning large jobs if missing)
        try:
            import torch  # type: ignore  # noqa: F401
        except Exception:
            res = AutoTrainResult(ok=False, message="PyTorch not available in backend venv (install CPU torch).")
            _set_last_train_result(res)
            return res

        out_dir = root / "data"
        csv_path = out_dir / "readings.csv"
        load_npz = root / "ai" / "data" / "load_ds.npz"
        gen_npz = root / "ai" / "data" / "gen_ds.npz"
        load_pt = root / "ai" / "models" / "load_lstm.pt"
        gen_pt = root / "ai" / "models" / "gen_lstm.pt"
        out_dir.mkdir(parents=True, exist_ok=True)

        hours = int(settings.auto_train_history_hours)

        # Export
        code, out = await _run_cmd(
            [
                sys.executable,
                "-m",
                "ai.scripts.export_readings",
                "--hours",
                str(hours),
                "--output",
                str(csv_path),
                "--database-url",
                str(settings.database_url),
            ],
            cwd=root,
            timeout_s=120,
        )
        if code != 0:
            res = AutoTrainResult(ok=False, message="Export failed.", output=out)
            _set_last_train_result(res)
            return res

        # Prepare datasets
        code, out2 = await _run_cmd(
            [
                sys.executable,
                "-m",
                "ai.training.prepare_dataset",
                "--input",
                str(csv_path),
                "--output",
                str(load_npz),
                "--target",
                "total_load_kw",
            ],
            cwd=root,
            timeout_s=120,
        )
        if code != 0:
            res = AutoTrainResult(ok=False, message="Dataset prep (load) failed.", output=out + "\n" + out2)
            _set_last_train_result(res)
            return res

        code, out3 = await _run_cmd(
            [
                sys.executable,
                "-m",
                "ai.training.prepare_dataset",
                "--input",
                str(csv_path),
                "--output",
                str(gen_npz),
                "--target",
                "pv_kw",
            ],
            cwd=root,
            timeout_s=120,
        )
        if code != 0:
            res = AutoTrainResult(ok=False, message="Dataset prep (gen) failed.", output=out + "\n" + out3)
            _set_last_train_result(res)
            return res

        # Train models (keep epochs modest by default)
        code, out4 = await _run_cmd(
            [sys.executable, "-m", "ai.training.lstm_train", "--dataset", str(load_npz), "--out", str(load_pt), "--epochs", "10"],
            cwd=root,
            timeout_s=1800,
        )
        if code != 0:
            res = AutoTrainResult(ok=False, message="Training (load) failed.", output=out + "\n" + out4)
            _set_last_train_result(res)
            return res

        code, out5 = await _run_cmd(
            [sys.executable, "-m", "ai.training.lstm_train", "--dataset", str(gen_npz), "--out", str(gen_pt), "--epochs", "10"],
            cwd=root,
            timeout_s=1800,
        )
        if code != 0:
            res = AutoTrainResult(ok=False, message="Training (gen) failed.", output=out + "\n" + out5)
            _set_last_train_result(res)
            return res

        res = AutoTrainResult(ok=True, message=f"Trained models: {load_pt.name}, {gen_pt.name}.", output=out4 + "\n" + out5)
        _set_last_train_result(res)
        return res

    async def train_now(self) -> AutoTrainResult:
        """Run one training attempt immediately (serialized with background loop)."""
        async with self._running:
            return await self._maybe_train_once()

    async def start_manual_train_job(self) -> dict:
        """
        Start a training job in the background with step + log-tail progress.
        Only one job is allowed at a time; if a job is already running, return it.
        """
        job = _get_or_create_manual_job()
        if job is None:
            raise RuntimeError("manual training job storage is not initialized")
        if job.state == "running":
            return _manual_job_dict(job)

        # Reset job state for a new run.
        job.state = "queued"
        job.current_step = 0
        job.current_label = "Waiting"
        job.progress = 0.0
        job.started_at = None
        job.finished_at = None
        job.ok = None
        job.message = None
        job.log_tail = ""
        job_id = job.id

        asyncio.create_task(self._run_manual_train_job(job))
        return _manual_job_dict(job)

    async def _run_manual_train_job(self, job: ManualTrainJob) -> None:
        async with self._running:
            job.state = "running"
            job.started_at = datetime.now(timezone.utc).isoformat()
            _update_job_tail(job, "[training] Starting training pipeline...\n")

            root = _project_root()
            db_path = _db_path()
            n_rows = _count_rows(db_path)
            min_samples = int(settings.auto_train_min_samples)

            if n_rows < min_samples:
                job.state = "failed"
                job.ok = False
                job.progress = 0.0
                job.message = f"Not enough DB samples yet ({n_rows} < {min_samples})."
                job.finished_at = datetime.now(timezone.utc).isoformat()
                res = AutoTrainResult(ok=False, message=job.message)
                _set_last_train_result(res)
                return

            # Quick torch import check (avoid spawning large jobs if missing)
            try:
                import torch  # type: ignore  # noqa: F401
            except Exception:
                job.state = "failed"
                job.ok = False
                job.progress = 0.0
                job.message = "PyTorch not available in backend venv (install CPU torch)."
                job.finished_at = datetime.now(timezone.utc).isoformat()
                res = AutoTrainResult(ok=False, message=job.message)
                _set_last_train_result(res)
                return

            out_dir = root / "data"
            csv_path = out_dir / "readings.csv"
            load_npz = root / "ai" / "data" / "load_ds.npz"
            gen_npz = root / "ai" / "data" / "gen_ds.npz"
            load_pt = root / "ai" / "models" / "load_lstm.pt"
            gen_pt = root / "ai" / "models" / "gen_lstm.pt"
            out_dir.mkdir(parents=True, exist_ok=True)

            hours = int(settings.auto_train_history_hours)
            epochs = 10  # keep modest for interactive runs
            steps = [
                (0, "Export readings", [sys.executable, "-m", "ai.scripts.export_readings", "--hours", str(hours), "--output", str(csv_path)], 10),
                (
                    1,
                    "Prepare load dataset",
                    [
                        sys.executable,
                        "-m",
                        "ai.training.prepare_dataset",
                        "--input",
                        str(csv_path),
                        "--output",
                        str(load_npz),
                        "--target",
                        "total_load_kw",
                    ],
                    35,
                ),
                (
                    2,
                    "Prepare PV generation dataset",
                    [
                        sys.executable,
                        "-m",
                        "ai.training.prepare_dataset",
                        "--input",
                        str(csv_path),
                        "--output",
                        str(gen_npz),
                        "--target",
                        "pv_kw",
                    ],
                    55,
                ),
                (
                    3,
                    "Train load LSTM",
                    [sys.executable, "-m", "ai.training.lstm_train", "--dataset", str(load_npz), "--out", str(load_pt), "--epochs", str(epochs)],
                    75,
                ),
                (
                    4,
                    "Train PV generation LSTM",
                    [sys.executable, "-m", "ai.training.lstm_train", "--dataset", str(gen_npz), "--out", str(gen_pt), "--epochs", str(epochs)],
                    92,
                ),
            ]

            full_out_parts: list[str] = []
            full_out = ""

            for _step_i, label, cmd, progress_at in steps:
                job.current_step = _step_i
                job.current_label = label
                job.progress = float(progress_at)
                _update_job_tail(job, f"\n[training] Step {_step_i + 1}/{len(steps)}: {label}\n")

                # Stream logs to UI
                buf_tail_chars = 12000
                stage_lines: list[str] = []

                def on_line(line: str) -> None:
                    stage_lines.append(line)
                    # Keep only recent tail in memory for API responses.
                    _update_job_tail(job, line, keep_chars=buf_tail_chars)

                timeout_s = 1200 if "train" in label.lower() else 180
                code, out = await _run_cmd_stream(cmd, cwd=root, timeout_s=timeout_s, on_line=on_line)
                stage_tail = out[-40000:] if out else ""
                full_out_parts.append(stage_tail)
                full_out = "\n".join(full_out_parts)

                if code != 0:
                    job.state = "failed"
                    job.ok = False
                    job.progress = float(progress_at)
                    job.message = f"Step failed: {label} (exit code {code})."
                    job.finished_at = datetime.now(timezone.utc).isoformat()
                    res = AutoTrainResult(ok=False, message=job.message, output=full_out)
                    _set_last_train_result(res)
                    return

            job.state = "done"
            job.ok = True
            job.progress = 100.0
            job.message = f"Trained models: {load_pt.name}, {gen_pt.name}."
            job.finished_at = datetime.now(timezone.utc).isoformat()
            res = AutoTrainResult(ok=True, message=job.message, output=full_out)
            _set_last_train_result(res)
            await _maybe_stop_auto_train_on_mape(full_out)
            _update_job_tail(job, "\n[training] Done.\n")


# Manual job state storage (simple single-job model).
_MANUAL_JOB: Optional[ManualTrainJob] = None


def _get_or_create_manual_job() -> Optional[ManualTrainJob]:
    global _MANUAL_JOB
    if _MANUAL_JOB is None:
        # Local import to avoid threading issues with UUID generation during reload.
        import uuid

        _MANUAL_JOB = ManualTrainJob(id=str(uuid.uuid4()))
    return _MANUAL_JOB


def _manual_job_dict(job: ManualTrainJob) -> dict:
    return {
        "job_id": job.id,
        "state": job.state,
        "current_step": job.current_step,
        "current_label": job.current_label,
        "progress": job.progress,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "result_ok": job.ok,
        "message": job.message,
        "log_tail": job.log_tail,
    }


def get_manual_train_job(job_id: Optional[str] = None) -> Optional[dict]:
    """
    Return the current manual job state.
    If job_id is provided, it must match the active job_id.
    """
    global _MANUAL_JOB
    if _MANUAL_JOB is None:
        return None
    if job_id is not None and _MANUAL_JOB.id != job_id:
        return None
    return _manual_job_dict(_MANUAL_JOB)


def _update_job_tail(job: ManualTrainJob, text: str, keep_chars: int = 12000) -> None:
    if not text:
        return
    if job.log_tail is None:
        job.log_tail = ""
    job.log_tail += text
    if keep_chars and len(job.log_tail) > keep_chars:
        job.log_tail = job.log_tail[-keep_chars:]


_GLOBAL_AUTO_TRAINER: Optional[AutoTrainLoop] = None


_LAST_TRAIN_RESULT: Optional[AutoTrainResult] = None
_LAST_TRAIN_AT: Optional[str] = None


def _last_train_path() -> Path:
    root = _project_root()
    out_dir = root / "data"
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / "last_train_result.json"


def _load_last_train_from_disk() -> Optional[dict]:
    path = _last_train_path()
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _set_last_train_result(res: AutoTrainResult) -> None:
    global _LAST_TRAIN_RESULT, _LAST_TRAIN_AT
    # Keep memory bounded for UI/logging.
    tail = res.output[-20000:] if res.output and len(res.output) > 20000 else res.output
    _LAST_TRAIN_RESULT = AutoTrainResult(ok=res.ok, message=res.message, output=tail or "")
    _LAST_TRAIN_AT = datetime.now(timezone.utc).isoformat()
    try:
        payload = {
            "ok": bool(_LAST_TRAIN_RESULT.ok),
            "message": _LAST_TRAIN_RESULT.message,
            "output": _LAST_TRAIN_RESULT.output or "",
            "finished_at": _LAST_TRAIN_AT,
        }
        _last_train_path().write_text(json.dumps(payload), encoding="utf-8")
    except Exception:
        # best-effort persistence only
        pass


def get_last_train_result() -> Optional[dict]:
    if _LAST_TRAIN_RESULT is None:
        from_disk = _load_last_train_from_disk()
        if from_disk is None:
            return None
        return from_disk
    return {
        "ok": bool(_LAST_TRAIN_RESULT.ok),
        "message": _LAST_TRAIN_RESULT.message,
        "output": _LAST_TRAIN_RESULT.output,
        "finished_at": _LAST_TRAIN_AT,
    }


MAPE_STOP_THRESHOLD_PCT = 15.0


def _extract_masked_mape_values(output: str) -> list[float]:
    """
    Extract MAPE(|y|>=0.02kW)=XX.XX% values emitted by ai.training.lstm_train.
    Returns list of floats (percent).
    """
    if not output:
        return []
    vals: list[float] = []
    for m in re.finditer(r"MAPE\\(\\|y\\|\\s*≥\\s*0\\.02kW\\)=\\s*([0-9]+(?:\\.[0-9]+)?)%", output):
        try:
            vals.append(float(m.group(1)))
        except Exception:
            continue
    # Also accept ASCII >= variant if terminal replaced ≥
    for m in re.finditer(r"MAPE\\(\\|y\\|\\s*>=\\s*0\\.02kW\\)=\\s*([0-9]+(?:\\.[0-9]+)?)%", output):
        try:
            vals.append(float(m.group(1)))
        except Exception:
            continue
    return vals


async def _maybe_stop_auto_train_on_mape(output: str) -> None:
    """
    If the training MAPE reaches threshold, automatically disable scheduled auto-train.
    Uses the worst-case MAPE among extracted values (conservative).
    """
    vals = _extract_masked_mape_values(output)
    if not vals:
        return
    worst = max(vals)
    if worst <= MAPE_STOP_THRESHOLD_PCT:
        # stop scheduled retraining; manual training remains available in UI
        await set_auto_train_enabled(False)


def set_global_auto_trainer(trainer: Optional[AutoTrainLoop]) -> None:
    global _GLOBAL_AUTO_TRAINER
    _GLOBAL_AUTO_TRAINER = trainer


def get_global_auto_trainer() -> Optional[AutoTrainLoop]:
    return _GLOBAL_AUTO_TRAINER

