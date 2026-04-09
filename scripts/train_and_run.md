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
# Optional (recommended): create backend/.env from backend/.env.example
# cp backend/.env.example backend/.env
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

## Mosquitto + ESP32 on the LAN

The backend (`MICROGRID_USE_HARDWARE_SIMULATION=false`) connects to **`localhost:1883`**. An **ESP32 on Wi‑Fi** must use this computer’s **LAN IP** in `secrets.h` (`MQTT_HOST`), and Mosquitto must **listen beyond loopback**.

Check:

```bash
ss -tlnp | grep 1883
```

If you only see **`127.0.0.1:1883`**, remote clients cannot connect. Install a dev listener:

```bash
sudo cp scripts/mosquitto-listener-dev.conf.example /etc/mosquitto/conf.d/99-local-dev.conf
sudo systemctl restart mosquitto
ss -tlnp | grep 1883
```

You should see **`0.0.0.0:1883`** (or similar). If `mosquitto` fails to start, see `journalctl -u mosquitto -e` — you may need to remove another `listener` line that binds only `127.0.0.1`.

**Test without the ESP32** (with `uvicorn` in hardware ingest mode and Mosquitto running):

```bash
bash scripts/test_mqtt_environment_publish.sh
curl -s http://localhost:8001/status | python3 -m json.tool | head -40
```

You should see `ambient_temperature_c` / `esp32_gateway` populate. If this works but the ESP32 does not, fix **Wi‑Fi IP**, **topic prefix**, or **firewall** (`sudo ufw allow 1883/tcp`).

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
| Live ESP32 sensors (DHT / light) | In `backend/.env` set `MICROGRID_USE_HARDWARE_SIMULATION=false`, start **Mosquitto**, restart `uvicorn`. ESP32 `MQTT_HOST` = this PC’s LAN IP (not `localhost`). Ensure Mosquitto listens on **`0.0.0.0:1883`** for Wi‑Fi devices (see **Mosquitto + ESP32 on the LAN** above). Check `http://localhost:8001/health/mqtt`. |
| Mosquitto not running (`Connection refused` on 1883) | Debian/Ubuntu: `sudo apt install mosquitto mosquitto-clients` then `sudo systemctl start mosquitto`. Check that something listens on port 1883. The API retries MQTT every 15s — you can start Mosquitto after uvicorn. |
| `dpkg was interrupted` / `mosquitto.service not found` after `apt install` | Repair package manager first: `sudo dpkg --configure -a`, then `sudo apt --fix-broken install` if needed, then install Mosquitto again. |
| MySQL `ERROR 1819` (password does not satisfy policy) during install | The password you chose for `root` is too weak. Use **Retry** in the dialog and pick a longer password with mixed case, digits, and a special character. URL‑encode it in `MICROGRID_DATABASE_URL`. For local dev only, after install you can lower `validate_password` in `mysql` (see MySQL 8 docs). |
| MQTT health | http://localhost:8001/health/mqtt (hardware ingest mode). |

More detail: **README.md** in the repo root.
