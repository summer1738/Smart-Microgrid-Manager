"""
Run the hardware simulator in a loop (e.g. for testing or feeding an external MQTT/API).
When using the FastAPI backend with use_hardware_simulation=True, the backend runs
the simulator in-process; this script is optional for standalone testing.
"""
import time
from datetime import datetime, timezone
from simulator.simulator import HardwareSimulator


def main():
    sim = HardwareSimulator(
        pv_capacity_kw=1.0,
        battery_capacity_kwh=2.4,
        initial_soc_percent=70.0,
        cloud_factor=0.9,
    )
    interval = 60  # seconds
    print("Hardware simulator running (Ctrl+C to stop). Interval:", interval, "s")
    while True:
        reading = sim.tick(datetime.now(timezone.utc))
        ts = reading["timestamp"]
        pv = reading["pv"]["power_kw"]
        soc = reading["battery"]["soc_percent"]
        load = reading["total_load_kw"]
        print(f"{ts}  PV={pv:.2f} kW  SOC={soc:.1f}%  Load={load:.2f} kW")
        time.sleep(interval)


if __name__ == "__main__":
    main()
