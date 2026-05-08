"""
adapter.py — QCentroid platform schema -> internal canonical schema.

QCentroid input (per Technical Details tab of use case 743):
    data:
        jobs                 array — job orders (id, qty, due_date, priority, routing, required_operations)
        machines             array — machine list (id, capabilities, speeds, allowed_ops, tooling)
        processing_times     object — per (job, op, machine) processing times (and setup/changeover)
        setup_matrix         object — sequence-dependent setups
        planning_horizon     object — total horizon and time-slot granularity
        maintenance_schedules array — planned maintenance windows
        materials            object — BOM, lead times, inventory
        labor                object — shift rosters, operator skill matrices
        business_constraints object — SLAs, energy tariffs, permitted policies
        baseline_kpis        object — current makespan, idle time, etc.
        metadata             object — MES/ERP API endpoints, data quality
        num_jobs / num_machines / planning_horizon_hours — root benchmarking params
"""
from __future__ import annotations

from typing import Any, Dict, List

DEFAULT_SLOT_MINUTES = 60


def to_internal(raw: Dict[str, Any], extended: bool = True) -> Dict[str, Any]:
    horizon_hours = int(
        raw.get("planning_horizon_hours")
        or raw.get("planning_horizon", {}).get("hours")
        or _max_due_date(raw)
        or 24
    )
    slot_minutes = int(raw.get("planning_horizon", {}).get("slot_minutes", DEFAULT_SLOT_MINUTES))
    horizon = int(horizon_hours * 60 / slot_minutes)

    obj_w_raw = raw.get("business_constraints", {}).get("objective_weights", {}) or {}
    obj = {
        "alpha": float(obj_w_raw.get("alpha", 1.0)),
        "beta":  float(obj_w_raw.get("beta", 1.0)),
        "gamma": float(obj_w_raw.get("gamma", 0.1)),
        "delta": float(obj_w_raw.get("delta", 0.5)),
    }

    machines = _adapt_machines(raw, horizon)
    machine_ids = {m["id"] for m in machines}

    for ms in raw.get("maintenance_schedules", []) or []:
        m_id = ms.get("machine_id")
        if m_id not in machine_ids:
            continue
        s = int(ms.get("start_slot", _hours_to_slot(ms.get("start_hour", 0), slot_minutes)))
        e = int(ms.get("end_slot", _hours_to_slot(ms.get("end_hour", 0), slot_minutes)))
        for m in machines:
            if m["id"] == m_id:
                for t in range(max(0, s), min(horizon, e)):
                    m["availability"][t] = 0

    jobs = _adapt_jobs(raw, machines, horizon, slot_minutes, extended=extended)
    setup_matrix = raw.get("setup_matrix") if extended else None
    energy_tou = _adapt_energy_tou(raw, machines, horizon) if extended else None

    out_of_scope = []
    if raw.get("labor"):
        out_of_scope.append("labor:rosters_and_skills_not_modeled_in_v1")
    if raw.get("materials"):
        out_of_scope.append("materials:bom_and_lead_times_not_modeled_in_v1")

    return {
        "horizon": horizon,
        "slot_minutes": slot_minutes,
        "objective_weights": obj,
        "jobs": jobs,
        "machines": machines,
        "setup_matrix": setup_matrix,
        "energy_tou": energy_tou,
        "policy": {
            "labor_present": bool(raw.get("labor")),
            "materials_present": bool(raw.get("materials")),
            "out_of_scope_v1": out_of_scope,
        },
    }


def _adapt_machines(raw, horizon: int) -> List[Dict[str, Any]]:
    raw_machines = raw.get("machines") or []
    if not raw_machines:
        n = int(raw.get("num_machines", 1))
        raw_machines = [{"id": f"M{i+1}"} for i in range(n)]
    machines: List[Dict[str, Any]] = []
    for m in raw_machines:
        machines.append({
            "id": str(m.get("id") or f"M{len(machines)+1}"),
            "availability": [1] * horizon,
            "capabilities": m.get("capabilities") or m.get("permitted_operations") or [],
        })
    return machines


def _adapt_jobs(raw, machines, horizon, slot_minutes, extended: bool) -> List[Dict[str, Any]]:
    raw_jobs = raw.get("jobs") or []
    if not raw_jobs:
        n = int(raw.get("num_jobs", 1))
        raw_jobs = [{"id": f"J{i+1}"} for i in range(n)]
    pt = raw.get("processing_times") or {}
    jobs: List[Dict[str, Any]] = []
    for j in raw_jobs:
        jid = str(j.get("id") or f"J{len(jobs)+1}")
        release = _hours_to_slot(j.get("release_hour", 0), slot_minutes)
        due = _hours_to_slot(j.get("due_hour", horizon), slot_minutes)
        weight = float(j.get("priority", j.get("weight", 1.0)))
        frozen = bool(j.get("frozen", False))
        ops = _adapt_ops(j, jid, machines, pt, slot_minutes, extended=extended)
        jobs.append({
            "id": jid, "release": int(release), "due_date": int(due),
            "weight": weight, "frozen": frozen,
            "frozen_plan": j.get("frozen_plan"), "ops": ops,
        })
    return jobs


def _adapt_ops(j, jid, machines, pt, slot_minutes, extended: bool):
    routing = j.get("routing") or j.get("required_operations")
    if not routing or not extended:
        alts = []
        for m in machines:
            p_min = _lookup_p(pt, jid, op_id=0, machine_id=m["id"], default=None)
            if p_min is None:
                p_min = int(j.get("default_processing_minutes", 60))
            alts.append({
                "machine": m["id"],
                "p": max(1, int(round(p_min / slot_minutes))),
                "energy_kwh": float(_lookup_energy(pt, jid, 0, m["id"], default=0.0)),
                "setup_default": 0,
            })
        return [{"id": 0, "alternatives": alts}]
    ops = []
    for o_idx, op in enumerate(routing):
        op_id = op.get("id", o_idx)
        eligible = op.get("eligible_machines") or [m["id"] for m in machines if _capable(m, op)]
        alts = []
        for m_id in eligible:
            p_min = _lookup_p(pt, jid, op_id, m_id, default=None)
            if p_min is None:
                p_min = int(op.get("default_processing_minutes", 60))
            alts.append({
                "machine": m_id,
                "p": max(1, int(round(p_min / slot_minutes))),
                "energy_kwh": float(_lookup_energy(pt, jid, op_id, m_id, default=0.0)),
                "setup_default": int(op.get("default_setup_minutes", 0) / slot_minutes),
            })
        if alts:
            ops.append({"id": op_id, "alternatives": alts})
    return ops


def _capable(m: dict, op: dict) -> bool:
    caps = m.get("capabilities") or []
    op_type = op.get("type") or op.get("operation_type")
    return (not caps) or (op_type is None) or (op_type in caps)


def _lookup_p(pt: dict, jid, op_id, machine_id, default):
    by_job = pt.get(str(jid)) or pt.get(jid) or {}
    if isinstance(by_job, dict):
        by_op = by_job.get(str(op_id)) or by_job.get(op_id) or {}
        if isinstance(by_op, dict):
            v = by_op.get(str(machine_id)) or by_op.get(machine_id)
            if v is not None:
                return int(v.get("minutes", v) if isinstance(v, dict) else v)
        v = by_job.get(str(machine_id)) or by_job.get(machine_id)
        if v is not None:
            return int(v.get("minutes", v) if isinstance(v, dict) else v)
    return default


def _lookup_energy(pt: dict, jid, op_id, machine_id, default):
    by_job = pt.get(str(jid)) or pt.get(jid) or {}
    if isinstance(by_job, dict):
        by_op = by_job.get(str(op_id)) or by_job.get(op_id) or {}
        if isinstance(by_op, dict):
            v = by_op.get(str(machine_id)) or by_op.get(machine_id)
            if isinstance(v, dict) and "energy_kwh" in v:
                return float(v["energy_kwh"])
    return default


def _adapt_energy_tou(raw, machines, horizon):
    bc = raw.get("business_constraints") or {}
    tou = bc.get("energy_tariff") or bc.get("energy_tou") or {}
    if not tou:
        return None
    out = {}
    for m in machines:
        series = tou.get(m["id"]) or tou.get("default") or [0.10] * horizon
        if len(series) < horizon:
            series = list(series) + [series[-1]] * (horizon - len(series))
        out[m["id"]] = list(map(float, series[:horizon]))
    return out


def _hours_to_slot(hours, slot_minutes):
    return int(round(float(hours) * 60.0 / slot_minutes))


def _max_due_date(raw):
    jobs = raw.get("jobs") or []
    if not jobs:
        return None
    return max((float(j.get("due_hour", 24)) for j in jobs), default=24)


def validate_internal(internal: Dict[str, Any]) -> None:
    if internal["horizon"] <= 0:
        raise ValueError(f"Non-positive horizon: {internal['horizon']}")
    if not internal["jobs"]:
        raise ValueError("No jobs in internal schema")
    if not internal["machines"]:
        raise ValueError("No machines in internal schema")
    machine_ids = {m["id"] for m in internal["machines"]}
    for j in internal["jobs"]:
        if not j["ops"]:
            raise ValueError(f"Job {j['id']} has no operations")
        for op in j["ops"]:
            if not op["alternatives"]:
                raise ValueError(f"Job {j['id']} op {op['id']} has no eligible machine")
            for a in op["alternatives"]:
                if a["machine"] not in machine_ids:
                    raise ValueError(f"Op (job={j['id']}, op={op['id']}) references unknown machine {a['machine']}")
                if a["p"] <= 0:
                    raise ValueError(f"Non-positive processing time on (job={j['id']}, op={op['id']}, machine={a['machine']})")
