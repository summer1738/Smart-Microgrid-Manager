# Train & run (copy-paste)

All commands assume the **project root** is `smart-microgrid-manager` (adjust `cd` if yours differs).

## One-time setup

```bash
cd ~/Documents/smart-microgrid-manager
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
pip install -r backend/requirements.txt
```

Optional — LSTM training & inference (PyTorch CPU):

```bash
pip install --extra-index-url https://download.pytorch.org/whl/cpu -r ai/requirements-torch-cpu.txt
```

## Run backend + web UI

**Terminal 1 — API** (port **8001** matches the Vite proxy in `webui/vite.config.js`):

```bash
cd ~/Documents/smart-microgrid-manager/backend
source ../.venv/bin/activate
export PYTHONPATH=..
uvicorn app.main:app --reload --port 8001
```

**Terminal 2 — UI:**

```bash
cd ~/Documents/smart-microgrid-manager/webui
npm install   # first time only
npm run dev
```

- API: http://localhost:8001/docs  
- UI: http://localhost:5173  

Stop either with `Ctrl+C`.

## Train LSTMs (web UI)

1. Install PyTorch once (see **One-time setup** above).
2. Let the simulator run until you have enough history (e.g. **200+** `battery_readings`). Faster ticks: `MICROGRID_SIMULATOR_INTERVAL_SECONDS=1` before `uvicorn`, or `backend/.env`.
3. In the UI open **Training** (`http://localhost:5173/training`), then **Start training**. Optional: turn on scheduled retraining on that page.

The same export / prepare / train steps can still be run from a terminal if you prefer; see README “Advanced users”.

## Optional

| Goal | Hint |
|------|------|
| Auto-train | **Training** page → enable scheduled retraining (SQLite). Env `MICROGRID_AUTO_TRAIN_ENABLED` only seeds the first DB row; interval/history/min_samples stay in env or `backend/.env`. |
| MQTT / Pi emulator instead of simulator | `MICROGRID_USE_HARDWARE_SIMULATION=false`, run Mosquitto, then `python -m simulator.pi_emulator ...`. See README. |
| MQTT health | http://localhost:8001/health/mqtt (hardware ingest mode). |

More detail: **README.md** in the repo root.
