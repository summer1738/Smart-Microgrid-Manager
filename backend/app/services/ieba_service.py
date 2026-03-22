"""
IEBA (Intelligent Energy Budgeting Algorithm).
MILP: maximize weighted critical load uptime subject to SOC >= soc_min and energy balance.
"""
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from pulp import LpBinary, LpMaximize, LpProblem, LpVariable, PULP_CBC_CMD, lpSum, value

# Efficiency for energy balance (same for charge/discharge). 1.0 keeps problems feasible with long nights.
EFF = 1.0


def run_ieba(
    forecast_generation_kw: List[float],
    forecast_consumption_kw: List[float],
    appliances: List[Dict[str, Any]],
    initial_soc_percent: float,
    capacity_kwh: float,
    soc_min_percent: float = 40.0,
    time_resolution_hours: float = 1.0,
    base_ts: Optional[datetime] = None,
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

    prob = LpProblem("IEBA", LpMaximize)
    # x[i,t] = 1 if appliance i is on in period t
    x = {}
    for i in range(n):
        for t in range(T):
            x[i, t] = LpVariable(f"x_{i}_{t}", cat=LpBinary)

    # Objective: max sum of weighted on-hours
    prob += lpSum(W[i] * x[i, t] for i in range(n) for t in range(T))

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
