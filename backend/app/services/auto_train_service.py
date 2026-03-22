"""
Optional background auto-train loop for LSTM checkpoints.

This runs inside the backend process (env-var gated). It will:
- export readings from sqlite DB to CSV
- prepare sequence datasets (gen + load)
- train and overwrite ai/models/{gen_lstm,load_lstm}.pt

Notes:
- This is intentionally simple and uses subprocess calls to the existing ai/* scripts.
- Training can be CPU-heavy; keep it disabled by default.
"""

from __future__ import annotations

import asyncio
import os
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

from app.config import settings


def _project_root() -> Path:
    # backend/app/services -> backend -> project root (smart-microgrid-manager)
    return Path(__file__).resolve().parents[3]


def _db_path() -> Path:
    root = _project_root()
    return root / "backend" / "microgrid.db"


def _count_rows(db_path: Path) -> int:
    if not db_path.exists():
        return 0
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.execute("SELECT COUNT(*) FROM battery_readings")
        row = cur.fetchone()
        return int(row[0]) if row and row[0] is not None else 0
    except Exception:
        return 0
    finally:
        conn.close()


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


@dataclass
class AutoTrainResult:
    ok: bool
    message: str
    output: str = ""


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
                if settings.auto_train_enabled:
                    async with self._running:
                        res = await self._maybe_train_once()
                        # Keep this lightweight; shows in backend logs
                        ts = datetime.now(timezone.utc).isoformat()
                        print(f"[auto-train] {ts} ok={res.ok} {res.message}")
                        if res.output and not res.ok:
                            print(f"[auto-train] output:\n{res.output}")
            except Exception as e:  # noqa: BLE001
                ts = datetime.now(timezone.utc).isoformat()
                print(f"[auto-train] {ts} exception: {e!s}")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=interval)
            except asyncio.TimeoutError:
                continue

    async def _maybe_train_once(self) -> AutoTrainResult:
        root = _project_root()
        db_path = _db_path()
        n_rows = _count_rows(db_path)
        if n_rows < int(settings.auto_train_min_samples):
            return AutoTrainResult(
                ok=False,
                message=f"Not enough DB samples yet ({n_rows} < {settings.auto_train_min_samples}).",
            )

        # Quick torch import check (avoid spawning large jobs if missing)
        try:
            import torch  # type: ignore  # noqa: F401
        except Exception:
            return AutoTrainResult(ok=False, message="PyTorch not available in backend venv (install CPU torch).")

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
            [sys.executable, "-m", "ai.scripts.export_readings", "--hours", str(hours), "--output", str(csv_path)],
            cwd=root,
            timeout_s=120,
        )
        if code != 0:
            return AutoTrainResult(ok=False, message="Export failed.", output=out)

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
            return AutoTrainResult(ok=False, message="Dataset prep (load) failed.", output=out + "\n" + out2)

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
            return AutoTrainResult(ok=False, message="Dataset prep (gen) failed.", output=out + "\n" + out3)

        # Train models (keep epochs modest by default)
        code, out4 = await _run_cmd(
            [sys.executable, "-m", "ai.training.lstm_train", "--dataset", str(load_npz), "--out", str(load_pt), "--epochs", "10"],
            cwd=root,
            timeout_s=1800,
        )
        if code != 0:
            return AutoTrainResult(ok=False, message="Training (load) failed.", output=out + "\n" + out4)

        code, out5 = await _run_cmd(
            [sys.executable, "-m", "ai.training.lstm_train", "--dataset", str(gen_npz), "--out", str(gen_pt), "--epochs", "10"],
            cwd=root,
            timeout_s=1800,
        )
        if code != 0:
            return AutoTrainResult(ok=False, message="Training (gen) failed.", output=out + "\n" + out5)

        return AutoTrainResult(ok=True, message=f"Trained models: {load_pt.name}, {gen_pt.name}.", output=out4 + "\n" + out5)

    async def train_now(self) -> AutoTrainResult:
        """Run one training attempt immediately (serialized with background loop)."""
        async with self._running:
            return await self._maybe_train_once()


_GLOBAL_AUTO_TRAINER: Optional[AutoTrainLoop] = None


def set_global_auto_trainer(trainer: Optional[AutoTrainLoop]) -> None:
    global _GLOBAL_AUTO_TRAINER
    _GLOBAL_AUTO_TRAINER = trainer


def get_global_auto_trainer() -> Optional[AutoTrainLoop]:
    return _GLOBAL_AUTO_TRAINER

