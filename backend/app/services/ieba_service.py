"""
IEBA (Intelligent Energy Budgeting Algorithm).
MILP: maximize weighted critical load uptime subject to SOC >= soc_min and energy balance.
"""
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from pulp import LpBinary, LpMaximize, LpProblem, LpVariable, PULP_CBC_CMD, lpSum, value

# Efficiency for energy balance (same for charge/discharge). 1.0 keeps problems feasible with long nights.
EFF = 1.0


def _parse_schedule_prefs(raw: Any) -> dict:
    """
    schedule_prefs is stored as JSON string in Appliance.schedule_prefs.
    Supported shapes:
      - {"mode":"max_possible"}
      - {"mode":"preferred_times","hard":false,"bonus":20,"windows":[{"start":"07:00","end":"09:00"}]}
    """
    if raw is None:
        return {"mode": "max_possible"}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            return json.loads(raw)
        except Exception:
            return {"mode": "max_possible"}
    return {"mode": "max_possible"}


def _hhmm_to_hour(s: str) -> Optional[float]:
    try:
        parts = str(s).strip().split(":")
        if len(parts) != 2:
            return None
        hh = int(parts[0])
        mm = int(parts[1])
        if not (0 <= hh <= 23 and 0 <= mm <= 59):
            return None
        return float(hh) + float(mm) / 60.0
    except Exception:
        return None


def _in_window(hour: float, start: float, end: float) -> bool:
    # Supports wrap-around windows (e.g., 22:00-06:00).
    if start == end:
        return False
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end


def run_ieba(
    forecast_generation_kw: List[float],
    forecast_consumption_kw: List[float],
    appliances: List[Dict[str, Any]],
    initial_soc_percent: float,
    capacity_kwh: float,
    soc_min_percent: float = 40.0,
    time_resolution_hours: float = 1.0,
    base_ts: Optional[datetime] = None,
    inverter_capacity_kw: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """
    Solve MILP: max sum_t sum_a weight_a * x[a,t] s.t. SOC dynamics and SOC >= soc_min.
    appliances: list of {id, name, priority, rated_watts} (priority 1=critical, 2=essential, 3=non-essential).
    Returns list of {appliance_id, appliance_name, start_ts, end_ts, planned_state} for each (a,t).
    """
    T = len(forecast_generation_kw)
    if T == 0 or not appliances:
        return []

    base_ts = base_ts or datetime.now(timezone.utc)
    dt_h = time_resolution_hours
    # Index appliances by 0..n-1 for PuLP
    app_list = list(appliances)
    n = len(app_list)
    # Rated power in kW
    P = [(app["rated_watts"] / 1000.0) for app in app_list]
    # Weights: P1=100, P2=10, P3=1
    W = [100 if app.get("priority") == 1 else (10 if app.get("priority") == 2 else 1) for app in app_list]
    prefs = [_parse_schedule_prefs(app.get("schedule_prefs")) for app in app_list]

    prob = LpProblem("IEBA", LpMaximize)
    # x[i,t] = 1 if appliance i is on in period t
    x = {}
    for i in range(n):
        for t in range(T):
            x[i, t] = LpVariable(f"x_{i}_{t}", cat=LpBinary)

    # Preference bonus per (i,t): incentivize running inside preferred windows.
    bonus = {}
    hard_forbid = {}
    for i in range(n):
        pref = prefs[i] or {"mode": "max_possible"}
        mode = str(pref.get("mode") or "max_possible")
        if mode != "preferred_times":
            for t in range(T):
                bonus[i, t] = 0.0
                hard_forbid[i, t] = False
            continue
        windows = pref.get("windows") or []
        hard = bool(pref.get("hard", False))
        # Default bonus by priority if not provided.
        default_bonus = 40.0 if app_list[i].get("priority") == 1 else (15.0 if app_list[i].get("priority") == 2 else 5.0)
        b = float(pref.get("bonus", default_bonus))
        for t in range(T):
            ts = base_ts + timedelta(hours=t * dt_h)
            hour = ts.hour + ts.minute / 60.0
            preferred = False
            for w in windows:
                st = _hhmm_to_hour(w.get("start"))
                en = _hhmm_to_hour(w.get("end"))
                if st is None or en is None:
                    continue
                if _in_window(hour, st, en):
                    preferred = True
                    break
            bonus[i, t] = b if preferred else 0.0
            hard_forbid[i, t] = (hard and (not preferred))

    # Objective: max weighted on-hours + preference bonus
    prob += lpSum((W[i] + bonus[i, t]) * x[i, t] for i in range(n) for t in range(T))

    # SOC variables (continuous). Allow up to 150 so equality is feasible when PV > load (battery would be “capped” in reality).
    soc_min = soc_min_percent
    soc_max = 150.0
    soc = {}
    for t in range(T + 1):
        soc[t] = LpVariable(f"soc_{t}", lowBound=soc_min, upBound=soc_max)

    # Initial SOC
    prob += soc[0] == min(soc_max, max(soc_min, initial_soc_percent))

    # Energy balance: SOC(t+1) = SOC(t) + (PV(t) - load(t)) * dt / capacity * 100 * EFF
    # Use same EFF for charge/discharge (simplified; round-trip EFF^2).
    c = 100.0 * dt_h / capacity_kwh * EFF
    for t in range(T):
        pv_t = forecast_generation_kw[t]
        load_t = lpSum(P[i] * x[i, t] for i in range(n))
        prob += soc[t + 1] == soc[t] + (pv_t * c) - load_t * c

        # Inverter power limit (if configured): total appliance draw must not exceed inverter capacity.
        if inverter_capacity_kw is not None and float(inverter_capacity_kw) > 0:
            prob += load_t <= float(inverter_capacity_kw)

    # Hard preference: forbid running outside preferred windows (if configured)
    for i in range(n):
        for t in range(T):
            if hard_forbid.get((i, t)):
                prob += x[i, t] == 0

    # Manual override / fixed-state appliances: keep them locked for the optimization horizon.
    for i in range(n):
        fixed_state = app_list[i].get("fixed_state")
        if fixed_state is None:
            continue
        fixed_value = 1 if bool(fixed_state) else 0
        for t in range(T):
            prob += x[i, t] == fixed_value

    prob.solve(PULP_CBC_CMD(msg=False))
    # 1=Optimal, 0=Not Solved, -1=Infeasible, -2=Unbounded, -3=Undefined, -4=Unbounded
    if prob.status != 1:
        return []

    # Build schedule slots: one slot per (appliance, period) with planned_state on/off
    slots = []
    for t in range(T):
        start_ts = base_ts + timedelta(hours=t * dt_h)
        end_ts = base_ts + timedelta(hours=(t + 1) * dt_h)
        for i in range(n):
            app = app_list[i]
            on = value(x[i, t]) and value(x[i, t]) > 0.5
            slots.append({
                "appliance_id": app.get("id", i),
                "appliance_db_id": app.get("db_id"),
                "appliance_name": app.get("name", f"Appliance {i}"),
                "start_ts": start_ts,
                "end_ts": end_ts,
                "planned_state": "on" if on else "off",
                "status": "pending",
            })
    return slots
