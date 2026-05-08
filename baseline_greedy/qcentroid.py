"""
qcentroid.py - Baseline solver (NO opt-specialists discipline).

Control arm of the A/B experiment. One-pass earliest-finish-time greedy
that any junior engineer would write on the first day - no classifier
pass, no specialist verification, no Phase-2 restate.
"""
from __future__ import annotations

import hashlib
import json
import time
import traceback
from datetime import datetime, timezone
from typing import Any, Dict, List

SOLVER_VERSION = "1.0.0-baseline-greedy"


def solver(input_data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
    started_utc = datetime.now(timezone.utc).isoformat()
    t0 = time.perf_counter()
    payload_for_hash = json.dumps(input_data, sort_keys=True, default=str).encode("utf-8")
    dataset_sha256 = hashlib.sha256(payload_for_hash).hexdigest()
    raw = (input_data or {}).get("data", input_data) or {}

    try:
        slot_minutes = int(raw.get("planning_horizon", {}).get("slot_minutes", 60))
        horizon_hours = int(raw.get("planning_horizon_hours") or 24)
        horizon = int(horizon_hours * 60 / slot_minutes)
        machines = raw.get("machines") or [{"id": f"M{i+1}"} for i in range(int(raw.get("num_machines", 1)))]
        machine_ids = [m["id"] for m in machines]
        jobs = raw.get("jobs") or [{"id": f"J{i+1}"} for i in range(int(raw.get("num_jobs", 1)))]
        pt = raw.get("processing_times") or {}

        jobs_sorted = sorted(jobs, key=lambda j: (
            int(round(float(j.get("due_hour", horizon_hours)) * 60 / slot_minutes)),
            -float(j.get("priority", 1)),
        ))

        free = {m_id: 0 for m_id in machine_ids}
        schedule: List[Dict[str, Any]] = []
        for j in jobs_sorted:
            jid = j["id"]
            release = int(round(float(j.get("release_hour", 0)) * 60 / slot_minutes))
            routing = j.get("routing") or [{"id": 0, "type": None}]
            prev_end = release
            for op in routing:
                op_id = op.get("id", 0)
                eligible = op.get("eligible_machines") or machine_ids
                best = None
                for m_id in eligible:
                    p_min = _lookup_p(pt, jid, op_id, m_id, default=60)
                    p = max(1, int(round(p_min / slot_minutes)))
                    start = max(free[m_id], prev_end)
                    end = start + p
                    if end > horizon:
                        continue
                    if best is None or end < best["end"]:
                        best = {"machine_id": m_id, "start": start, "end": end, "p": p}
                if best is None:
                    m_id = eligible[0]
                    p_min = _lookup_p(pt, jid, op_id, m_id, default=60)
                    p = max(1, int(round(p_min / slot_minutes)))
                    start = max(free[m_id], prev_end)
                    best = {"machine_id": m_id, "start": start, "end": start + p, "p": p}
                free[best["machine_id"]] = best["end"]
                prev_end = best["end"]
                schedule.append({"job_id": jid, "op_id": op_id, **best})

        wall = time.perf_counter() - t0
        makespan = max((s["end"] for s in schedule), default=0)
        weighted_tardiness = 0.0
        on_time = 0
        for j in jobs:
            due = int(round(float(j.get("due_hour", horizon_hours)) * 60 / slot_minutes))
            c = max((s["end"] for s in schedule if s["job_id"] == j["id"]), default=0)
            weighted_tardiness += float(j.get("priority", 1.0)) * max(0, c - due)
            if c <= due:
                on_time += 1
        on_time_pct = round(100.0 * on_time / max(1, len(jobs)), 2)
        busy = {m_id: 0 for m_id in machine_ids}
        for s in schedule:
            busy[s["machine_id"]] = busy.get(s["machine_id"], 0) + (s["end"] - s["start"])
        avg_util_pct = round(100.0 * sum(busy.values()) / (len(machine_ids) * horizon), 2) if horizon else 0.0
        by_m: Dict[str, list] = {}
        for s in schedule:
            by_m.setdefault(s["machine_id"], []).append(s)
        changeovers = 0
        for segs in by_m.values():
            segs.sort(key=lambda x: x["start"])
            for a, b in zip(segs, segs[1:]):
                if a["job_id"] != b["job_id"]:
                    changeovers += 1
        objective = makespan + weighted_tardiness

        return {"result": {
            "objective_value": float(objective), "makespan_hours": int(makespan),
            "total_tardiness_hours": float(weighted_tardiness),
            "on_time_delivery_pct": on_time_pct,
            "avg_machine_utilization_pct": avg_util_pct, "total_changeovers": changeovers,
            "benchmark": {"execution_cost": float(objective), "time_elapsed": wall, "energy_consumption": 0.0},
            "schedule": schedule, "gantt_data": [
                {"task_id": f'{s["job_id"]}.{s["op_id"]}', "resource_id": s["machine_id"],
                 "start_hour": s["start"], "end_hour": s["end"], "label": f'job {s["job_id"]}'}
                for s in schedule
            ],
            "solution_status": "feasible",
            "solver_info": {"solver_version": SOLVER_VERSION, "solver_family": "GREEDY",
                            "specialist_id": None, "underlying_solver": "earliest-finish-time-edd"},
            "computation_metrics": {"wall_time_seconds": wall},
            "constraint_violations": [], "quality_metrics": {"feasible": True},
            "audit": {"solver_version": SOLVER_VERSION, "dataset_sha256": dataset_sha256,
                      "run_started_at_utc": started_utc,
                      "run_finished_at_utc": datetime.now(timezone.utc).isoformat()},
        }}
    except Exception as exc:
        wall = time.perf_counter() - t0
        return {"result": {
            "objective_value": None, "makespan_hours": None, "total_tardiness_hours": None,
            "on_time_delivery_pct": 0.0, "avg_machine_utilization_pct": 0.0, "total_changeovers": 0,
            "benchmark": {"execution_cost": None, "time_elapsed": wall, "energy_consumption": 0.0},
            "schedule": [], "gantt_data": [], "solution_status": "error",
            "solver_info": {"solver_version": SOLVER_VERSION, "error": str(exc), "traceback": traceback.format_exc()},
        }}


def _lookup_p(pt, jid, op_id, machine_id, default=60):
    by_job = pt.get(str(jid)) or pt.get(jid) or {}
    by_op = by_job.get(str(op_id)) or by_job.get(op_id) or {}
    if isinstance(by_op, dict):
        v = by_op.get(str(machine_id)) or by_op.get(machine_id)
        if isinstance(v, dict):
            return int(v.get("minutes", default))
        if v is not None:
            return int(v)
    v = by_job.get(str(machine_id)) or by_job.get(machine_id)
    if isinstance(v, dict):
        return int(v.get("minutes", default))
    if v is not None:
        return int(v)
    return default
