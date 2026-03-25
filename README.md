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
- **Web UI**: Dashboard, Forecast, Schedule, Appliances, **Training** (`/training`: run full LSTM pipeline + scheduled retrain), **Model monitor** (checkpoint status, LSTM vs simulated overlay), Weather & PV, Settings.

### Optional: install PyTorch (CPU-only)

If you want the `/forecast` endpoint (and **Model monitor**) to use LSTM checkpoints, install CPU-only PyTorch into the backend venv:

- `pip install --extra-index-url https://download.pytorch.org/whl/cpu -r ai/requirements-torch-cpu.txt`

### Creating `load_lstm.pt` and `gen_lstm.pt`

The backend expects `ai/models/load_lstm.pt` and `ai/models/gen_lstm.pt`.

1. **One-time:** install PyTorch in the backend venv (see optional CPU torch install above).
2. **Let the simulator run** until you have enough `battery_readings` (see `MICROGRID_AUTO_TRAIN_MIN_SAMPLES`, default 200).
3. Open the web UI **Training** page (`/training`), check the status pills, then click **Start training**. That runs export → `prepare_dataset` → `lstm_train` for both models on the server. Enable **scheduled retraining** on the same page if you want.
4. **Model monitor** shows checkpoints and whether `/forecast` uses LSTMs.

Advanced users can still run the `python -m ai.scripts.export_readings` / `prepare_dataset` / `lstm_train` commands from the project root; the UI uses the same pipeline.

## Useful env vars

- `MICROGRID_CONTROLLER_LOOP_ENABLED=true|false`
- `MICROGRID_SIMULATOR_INTERVAL_SECONDS=60` (set to `1` to generate data faster)
- `MICROGRID_CONTROLLER_TICK_ON_STATUS_REQUEST=true|false` (legacy mode; tick on each `/status` call)
- `MICROGRID_AUTO_TRAIN_ENABLED=true|false` (default false; seeds the DB on first run — enable/disable scheduled training on the **Training** page in the web UI, stored in `system_settings`)
- `MICROGRID_AUTO_TRAIN_INTERVAL_MINUTES=360` (how often to retrain)
- `MICROGRID_AUTO_TRAIN_HISTORY_HOURS=168` (export window for training)
- `MICROGRID_AUTO_TRAIN_MIN_SAMPLES=200` (minimum `battery_readings` rows before training)
- `MICROGRID_MQTT_HOST=localhost`
- `MICROGRID_MQTT_PORT=1883`
- `MICROGRID_MQTT_TOPIC_PREFIX=microgrid`

### Weather → expected PV (Open-Meteo, no API key)

When LSTM checkpoints are **not** used, `/forecast` and IEBA (`POST /schedule/run`) use **hourly shortwave radiation** (W/m²) from [Open-Meteo](https://open-meteo.com/) to scale PV generation against your nominal array size. If the request fails or weather is disabled, the app falls back to the built-in clear-sky curve.

- `MICROGRID_WEATHER_FORECAST_ENABLED=true|false` (default `true`)
- `MICROGRID_WEATHER_LATITUDE` / `MICROGRID_WEATHER_LONGITUDE` (default: Harare-ish `-17.8`, `31.05`)
- `MICROGRID_WEATHER_PV_CAPACITY_KW` — nameplate kW for the forecast (default `1.0`)
- `MICROGRID_WEATHER_PANEL_DERATE` — multiply `shortwave/1000 × capacity` (default `0.85`, inverter + mismatch)

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
3. In backend config, set `MICROGRID_USE_HARDWARE_SIMULATION=false` and set MQTT host/port.
4. Backend MQTT ingest service will replace simulator data.

## Raspberry Pi emulator (MQTT contract)

You can emulate a Pi gateway today and keep the same MQTT contract when the real Pi arrives.

1. Start broker:
   - `mosquitto -p 1883`
2. Start backend in hardware-ingest mode:
   - `MICROGRID_USE_HARDWARE_SIMULATION=false MICROGRID_MQTT_HOST=localhost MICROGRID_MQTT_PORT=1883 PYTHONPATH=.. uvicorn app.main:app --reload --port 8000`
3. Start Pi emulator (from project root):
   - `python -m simulator.pi_emulator --host localhost --port 1883 --topic-prefix microgrid --interval-seconds 5`

Topics:
- Telemetry in:
  - `microgrid/sensors/pv`
  - `microgrid/sensors/battery`
  - `microgrid/sensors/load/<appliance_external_id>`
- Relay command out (backend -> Pi):
  - `microgrid/cmd/relay/<appliance_external_id>` with payload `{"is_on": true|false, ...}`
- Relay ack in (Pi -> backend, informational):
  - `microgrid/ack/relay/<appliance_external_id>`
