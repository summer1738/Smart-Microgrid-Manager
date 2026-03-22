# Smart Microgrid Manager

Off-grid solar microgrid management with forecasting, user behaviour learning, and intelligent load prioritization (IEBA). **Hardware simulation mode** for development without physical IoT devices.

Recommended **project folder name** on disk: `smart-microgrid-manager` (e.g. `~/Documents/smart-microgrid-manager`). If you still have `microgrid_manager`, rename it:

```bash
mv ~/Documents/microgrid_manager ~/Documents/smart-microgrid-manager
```

Then **reopen the project** in your editor from the new path. Recreate Python venvs so shebangs match the new location: `rm -rf .venv .venv-ai` and run `python3 -m venv .venv` again, then `pip install -r backend/requirements.txt` (and optional torch).

## Quick start (simulation only)

```bash
# From project root (smart-microgrid-manager/)

# 1. Python venv and backend
python3 -m venv .venv
source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -r backend/requirements.txt
cd backend && PYTHONPATH=.. uvicorn app.main:app --reload

# 2. Web UI (separate terminal, from project root)
cd webui && npm install && npm run dev
```

Backend: http://localhost:8000  
API docs: http://localhost:8000/docs  
Web UI: http://localhost:5173 (or port shown by Vite)

By default, the backend starts a **background controller loop** (simulation mode) that:
- applies the IEBA schedule for “now”
- advances the simulator every `MICROGRID_SIMULATOR_INTERVAL_SECONDS` (default 60s)
- persists readings to SQLite

So `/status` **reads the latest DB state** (it does not need to “tick”).

- **Forecast** (`GET /forecast`) returns a simulated 24h PV and demand series (LSTM-ready later).
- **IEBA** (`POST /schedule/run`) runs the MILP optimizer: maximizes critical/essential load uptime subject to SOC ≥ 40%, then persists the 24h schedule. `GET /schedule` returns the current schedule.
- **Schedule executor**: Each `GET /status` applies the IEBA schedule for "now" (sets `Appliance.is_on`); the simulator then uses these states so shedded loads draw 0 W. `POST /schedule/apply` applies the schedule on demand.
- **History** (`GET /status/history?hours=24`) returns time-series of PV, SOC, and total load for charts and export.
- **Export** (for LSTM): `python -m ai.scripts.export_readings --hours 168 --output data/readings.csv` dumps aligned readings from `backend/microgrid.db`.
- **Web UI**: Dashboard (SOC donut, line charts, load bars), Forecast (curves + bars), Schedule (24h heatmap), Appliances (priority / rated-power charts), **Model monitor** (`/model-monitor`: PyTorch + checkpoint status, LSTM vs simulated overlay).

### Optional: install PyTorch (CPU-only)

If you want the `/forecast` endpoint (and **Model monitor**) to use LSTM checkpoints, install CPU-only PyTorch into the backend venv:

- `pip install --extra-index-url https://download.pytorch.org/whl/cpu -r ai/requirements-torch-cpu.txt`

### Creating `load_lstm.pt` and `gen_lstm.pt`

The backend expects `ai/models/load_lstm.pt` and `ai/models/gen_lstm.pt`. To create them:

1. **Let the simulator run** so the DB has readings (e.g. a few hours with `MICROGRID_SIMULATOR_INTERVAL_SECONDS=1` or 60).

2. **Export readings** (from project root, with venv activated):
   ```bash
   python -m ai.scripts.export_readings --hours 168 --output data/readings.csv
   ```
   If you see "No readings in range", run the backend/simulator longer then retry.

3. **Prepare datasets** (load and PV):
   ```bash
   python -m ai.training.prepare_dataset --input data/readings.csv --output ai/data/load_ds.npz --target total_load_kw
   python -m ai.training.prepare_dataset --input data/readings.csv --output ai/data/gen_ds.npz  --target pv_kw
   ```

4. **Train and save models** (needs PyTorch in venv):
   ```bash
   python -m ai.training.lstm_train --dataset ai/data/load_ds.npz --out ai/models/load_lstm.pt
   python -m ai.training.lstm_train --dataset ai/data/gen_ds.npz  --out ai/models/gen_lstm.pt
   ```
   You need at least ~100 samples in the CSV (about 2 days at 1‑minute resolution, or more at 1‑hour). Restart the backend after saving the `.pt` files; **Model monitor** will then show both checkpoints and LSTM-driven forecast.

## Useful env vars

- `MICROGRID_CONTROLLER_LOOP_ENABLED=true|false`
- `MICROGRID_SIMULATOR_INTERVAL_SECONDS=60` (set to `1` to generate data faster)
- `MICROGRID_CONTROLLER_TICK_ON_STATUS_REQUEST=true|false` (legacy mode; tick on each `/status` call)
- `MICROGRID_AUTO_TRAIN_ENABLED=true|false` (default false)
- `MICROGRID_AUTO_TRAIN_INTERVAL_MINUTES=360` (how often to retrain)
- `MICROGRID_AUTO_TRAIN_HISTORY_HOURS=168` (export window for training)
- `MICROGRID_AUTO_TRAIN_MIN_SAMPLES=200` (minimum `battery_readings` rows before training)

## End-to-end commands (copy-paste)

Ordered steps with descriptions: **`scripts/train_and_run.md`**

## AI dependencies note (important)

- `ai/requirements.txt` is **lightweight** (numpy/pandas/sklearn) and is enough for dataset prep.
- PyTorch is **optional** and large; install CPU-only with:
  - `pip install --extra-index-url https://download.pytorch.org/whl/cpu -r ai/requirements-torch-cpu.txt`

## Project layout

- `backend/` — FastAPI app, DB, simulator integration, forecast & IEBA services
- `simulator/` — Hardware simulation (PV, battery, loads) when real hardware is unavailable
- `ai/` — LSTM training scripts and model artifacts (forecast)
- `webui/` — UCLPI (User Control and Load Prioritization Interface)

## Switching to real hardware

1. Run Mosquitto (MQTT broker) on the Pi.
2. Flash ESP32 firmware; point it at the broker.
3. In backend config, set `USE_HARDWARE_SIMULATION=false` and set MQTT host/port.
4. Backend MQTT ingest service will replace simulator data.
