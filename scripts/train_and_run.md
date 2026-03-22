# Smart Microgrid Manager — terminal commands

Setup → train LSTM → run backend & web UI. Run everything from the **project root** (`smart-microgrid-manager/`).

---

### 1. Go to the project folder

```bash
cd ~/Documents/smart-microgrid-manager
```

**What it does:** Makes the rest of the paths and `python -m ai...` commands work.

---

### 2. Create a Python virtual environment (first time only)

```bash
python3 -m venv .venv
```

**What it does:** Isolates Python packages for this project.

---

### 3. Activate the virtual environment

```bash
source .venv/bin/activate
```

**What it does:** Uses `.venv` for `pip` and `python`. Repeat this in every new terminal before backend/training commands.

---

### 4. Install backend dependencies

```bash
python -m pip install -U pip
pip install -r backend/requirements.txt
```

**What it does:** Installs FastAPI, uvicorn, SQLAlchemy, PuLP, numpy/pandas, etc.

---

### 5. (Optional) Install CPU-only PyTorch for LSTM training & inference

```bash
pip install --extra-index-url https://download.pytorch.org/whl/cpu -r ai/requirements-torch-cpu.txt
```

**What it does:** Lets you train `.pt` models and use `/forecast` + Model monitor with LSTMs. Skip if you only want simulated forecast.

---

### 6. Let the simulator fill the database (before training)

Start the backend once (see step 9 below) and leave it running for a while, **or** use a fast tick:

- `MICROGRID_SIMULATOR_INTERVAL_SECONDS=1` makes rows accumulate quickly.

You need enough rows in `battery_readings` for export/training (often **200+** if you use auto-train defaults).

---

### 7. Export readings → build datasets → train both models

**Only after** `backend/microgrid.db` has data:

```bash
python -m ai.scripts.export_readings --hours 168 --output data/readings.csv
```

```bash
python -m ai.training.prepare_dataset --input data/readings.csv --output ai/data/load_ds.npz --target total_load_kw
python -m ai.training.prepare_dataset --input data/readings.csv --output ai/data/gen_ds.npz  --target pv_kw
```

```bash
python -m ai.training.lstm_train --dataset ai/data/load_ds.npz --out ai/models/load_lstm.pt --epochs 10
python -m ai.training.lstm_train --dataset ai/data/gen_ds.npz  --out ai/models/gen_lstm.pt --epochs 10
```

**What it does:** Writes `data/readings.csv`, then `ai/data/*.npz`, then `ai/models/load_lstm.pt` and `ai/models/gen_lstm.pt`.

---

### 8. (Alternative) Auto-train + “Train now” in the UI

If you start the backend with auto-train enabled, the server can retrain on a schedule and Model monitor’s **Train now** works:

```bash
export MICROGRID_AUTO_TRAIN_ENABLED=true
export MICROGRID_AUTO_TRAIN_INTERVAL_MINUTES=360
export MICROGRID_AUTO_TRAIN_HISTORY_HOURS=168
export MICROGRID_AUTO_TRAIN_MIN_SAMPLES=200
```

(Use these together with step 9 in the same shell **before** `uvicorn`, or put them in `backend/.env`.)

---

### 9. Run the API server (terminal 1)

From project root, with venv activated:

```bash
cd ~/Documents/smart-microgrid-manager/backend
export PYTHONPATH=..
export MICROGRID_SIMULATOR_INTERVAL_SECONDS=1
export MICROGRID_AUTO_TRAIN_ENABLED=true
../.venv/bin/uvicorn app.main:app --reload --port 8001
```

**What it does:** Starts FastAPI on **http://localhost:8001** (OpenAPI: `/docs`). The simulator/controller loop runs in the background when simulation mode is on.

Adjust or drop `MICROGRID_*` exports if you don’t want auto-train or fast ticks.

---

### 10. Run the web UI (terminal 2)

Open a **second** terminal, activate venv if you need it only for installs; for Vite you usually just need Node:

```bash
cd ~/Documents/smart-microgrid-manager/webui
npm install
npm run dev
```

**What it does:** Starts Vite (often **http://localhost:5173**). The UI proxies `/api` to port **8001** — keep the backend on 8001 or change `webui/vite.config.js` to match.

---

### Stop

- **Frontend:** `Ctrl+C` in the Vite terminal.
- **Backend:** `Ctrl+C` in the uvicorn terminal.

---

### Quick check

- API: http://localhost:8001/docs  
- UI: http://localhost:5173/model-monitor  
