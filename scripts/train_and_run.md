# Train & run (copy-paste)

All commands assume the **project root** is `smart-microgrid-manager` (adjust `cd` if yours differs).

## One-time setup

```bash
cd ~/Documents/smart-microgrid-manager
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
pip install -r backend/requirements.txt
# USB fallback bridge dependency (ESP32 Serial -> MQTT) if needed:
pip install pyserial
```

Optional — LSTM training & inference (PyTorch CPU):

```bash
pip install --extra-index-url https://download.pytorch.org/whl/cpu -r ai/requirements-torch-cpu.txt
```

Optional — align DB appliance IDs for ESP32 relay topics (`proto_led_a`, `proto_led_b`):

```bash
cd ~/Documents/smart-microgrid-manager/backend
source ../.venv/bin/activate
export PYTHONPATH=.
python scripts/align_esp32_appliance_ids.py
```

## Run backend + web UI

**Terminal 1 — API** (port **8001** matches the Vite proxy in `webui/vite.config.js`):

```bash
cd ~/Documents/smart-microgrid-manager/backend
source ../.venv/bin/activate
export PYTHONPATH=..
# Optional (recommended): create backend/.env from backend/.env.example
# cp backend/.env.example backend/.env
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

## Verify you're on MySQL

```bash
curl -s http://localhost:8001/system/settings | head
```

You should see a JSON response (settings loaded from MySQL). If the API fails to start, confirm MySQL is running and `MICROGRID_DATABASE_URL` is correct.

## Train LSTMs (web UI)

1. Install PyTorch once (see **One-time setup** above).
2. Let the simulator run until you have enough history (e.g. **200+** `battery_readings`). Faster ticks: `MICROGRID_SIMULATOR_INTERVAL_SECONDS=1` before `uvicorn`, or `backend/.env`.
3. In the UI open **Training** (`http://localhost:5173/training`), then **Start training**. Optional: turn on scheduled retraining on that page.

The same export / prepare / train steps can still be run from a terminal if you prefer; see README “Advanced users”.

## Optional

| Goal | Hint |
|------|------|
| MySQL connection | Set `MICROGRID_DATABASE_URL=mysql+aiomysql://user:pass@host:3306/dbname` before `uvicorn`. |
| Auto-train | **Training** page → enable scheduled retraining. Env `MICROGRID_AUTO_TRAIN_ENABLED` only seeds the first DB row; interval/history/min_samples stay in env or `backend/.env`. |
| MQTT / Pi emulator instead of simulator | `MICROGRID_USE_HARDWARE_SIMULATION=false`, run Mosquitto, then `python -m simulator.pi_emulator ...`. See README. |
| MQTT health | http://localhost:8001/health/mqtt (hardware ingest mode). |

More detail: **README.md** in the repo root.
