"""
qcentroid.py - Entry point for the Dynamic Production Scheduling solver
(MIP variant) generated via the opt-specialists pipeline.

Round 2: extended=False is now the default. The platform's published §3
formulation is single-op per job; extended=True (multi-op routings,
sequence-dependent setups) is opt-in via solver_params.extended=true.
This keeps the time-indexed encoding small enough to solve in seconds
on real Hisar/Jajpur datasets.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from adapter import to_internal, validate_internal
from mip_model import build_and_solve
from outputs import write_additional_outputs
from additional_output_generator import generate_additional_output

SOLVER_VERSION = "1.3.0-optspec-mip-base"
SOLVER_FAMILY = "MIP"
SPECIALIST_ID = "MIP"
SPECIALIST_SOURCE = "github.com/georgekorpas/opt-specialists/blob/main/03_MIP_specialist.md"
ALGORITHM_NAME = "OptSpec_MIP_Pyomo_HiGHS"


def solver(input_data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
    started_utc = datetime.now(timezone.utc).isoformat()
    t0 = time.perf_counter()
    max_exec_time_m = float(kwargs.get("max_exec_time_m", 5.0))
    mip_gap = float(kwargs.get("mip_gap", 0.05))  # round 2: looser gap so we always return feasible
    extended = bool(kwargs.get("extended", False))  # round 2: published §3 by default
    solver_name = str(kwargs.get("solver", "auto")).lower()
    raw = (input_data or {}).get("data", input_data) or {}
    payload_for_hash = json.dumps(input_data, sort_keys=True, default=str).encode("utf-8")
    dataset_sha256 = hashlib.sha256(payload_for_hash).hexdigest()
    additional_dir = Path(os.environ.get("ADDITIONAL_OUTPUT_DIR", "./additional_output"))
    additional_dir.mkdir(parents=True, exist_ok=True)

    try:
        internal = to_internal(raw, extended=extended)
        validate_internal(internal)
    except Exception as exc:
        return _error_result("adapter", exc, started_utc, t0, dataset_sha256)

    try:
        # round 2: leave 30% of budget as buffer for output generation
        time_limit_s = max(5.0, max_exec_time_m * 60.0 * 0.7)
        sol = build_and_solve(internal, time_limit_s=time_limit_s,
                              mip_gap=mip_gap, solver_name=solver_name, extended=extended)
    except Exception as exc:
        return _error_result("solver", exc, started_utc, t0, dataset_sha256)

    wall = time.perf_counter() - t0
    schedule = sol["schedule"]
    horizon = internal["horizon"]
    makespan_hours = sol["makespan"]
    total_tardiness_hours = sol["weighted_tardiness"]
    on_time_delivery_pct = _on_time_pct(schedule, internal["jobs"])
    machine_util = _per_machine_utilization(schedule, internal["machines"], horizon)
    avg_machine_utilization_pct = (sum(m["utilization_percentage"] for m in machine_util.values()) / len(machine_util)
                                   if machine_util else 0.0)
    avg_machine_utilization_pct = round(avg_machine_utilization_pct, 2)
    job_metrics = _per_job_metrics(schedule, internal["jobs"])
    total_changeovers = sol.get("changeovers", _count_changeovers(schedule))
    energy_kwh = sol.get("energy_kwh", 0.0)
    objective_value = sol["objective_value"]

    write_additional_outputs(
        additional_dir, schedule=schedule, jobs=internal["jobs"], machines=internal["machines"],
        horizon=horizon,
        kpis=dict(makespan_hours=makespan_hours, objective_value=objective_value,
                  on_time_delivery_pct=on_time_delivery_pct,
                  total_tardiness_hours=total_tardiness_hours,
                  avg_machine_utilization_pct=avg_machine_utilization_pct,
                  total_changeovers=total_changeovers, energy_kwh=energy_kwh),
        meta=dict(solver_version=SOLVER_VERSION, specialist_id=SPECIALIST_ID,
                  specialist_source=SPECIALIST_SOURCE, dataset_sha256=dataset_sha256,
                  run_started_at_utc=started_utc, wall_seconds=wall,
                  solver_name=sol["solver_name"], mip_gap_achieved=sol.get("mip_gap_achieved"),
                  extended=extended),
    )

    finished_utc = datetime.now(timezone.utc).isoformat()
    n_on_time = round(on_time_delivery_pct * len(internal["jobs"]) / 100.0)
    schedule_wrapped = {
        "assignments": schedule,
        "gantt_data": _gantt_data(schedule, internal["machines"]),
        "makespan": makespan_hours,
        "total_tardiness": total_tardiness_hours,
        "total_idle_time": max(0, len(internal["machines"]) * horizon
                                  - sum(s["end"] - s["start"] for s in schedule)),
        "total_energy_kwh": energy_kwh,
        "total_cost": objective_value,
        "jobs_on_time": n_on_time,
        "jobs_late": len(internal["jobs"]) - n_on_time,
        "on_time_percentage": on_time_delivery_pct,
    }

    result_dict = {
        "objective_value": objective_value,
        "makespan_hours": makespan_hours,
        "total_tardiness_hours": total_tardiness_hours,
        "on_time_delivery_pct": on_time_delivery_pct,
        "avg_machine_utilization_pct": avg_machine_utilization_pct,
        "total_changeovers": total_changeovers,
        "benchmark": {
            "execution_cost": {"value": round(wall * 0.5, 4), "unit": "credits"},
            "time_elapsed": f"{wall:.1f}s",
            "energy_consumption": energy_kwh,
        },
        "schedule": schedule_wrapped,
        "gantt_data": _gantt_data(schedule, internal["machines"]),
        "total_energy_kwh": energy_kwh,
        "machine_utilization": machine_util,
        "job_metrics": job_metrics,
        "solution_status": sol["status"],
        "solver_info": {
            "solver_version": SOLVER_VERSION, "solver_family": SOLVER_FAMILY,
            "specialist_id": SPECIALIST_ID, "specialist_source": SPECIALIST_SOURCE,
            "modeling_library": "pyomo", "underlying_solver": sol["solver_name"],
            "mip_gap_target": mip_gap, "mip_gap_achieved": sol.get("mip_gap_achieved"),
            "extended": extended,
        },
        "computation_metrics": {
            "wall_time_s": wall, "algorithm": ALGORITHM_NAME,
            "n_variables": sol.get("n_variables"), "n_constraints": sol.get("n_constraints"),
            "n_binaries_after_pruning": sol.get("n_binaries_after_pruning"),
            "best_bound": sol.get("best_bound"),
        },
        "constraint_violations": sol.get("constraint_violations", []),
        "quality_metrics": {
            "objective_value": objective_value, "best_bound": sol.get("best_bound"),
            "mip_gap_achieved": sol.get("mip_gap_achieved"),
            "feasible": sol["status"] in ("optimal", "feasible"),
        },
        "audit": {
            "solver_version": SOLVER_VERSION, "specialist_id": SPECIALIST_ID,
            "specialist_source": SPECIALIST_SOURCE, "dataset_sha256": dataset_sha256,
            "run_started_at_utc": started_utc, "run_finished_at_utc": finished_utc,
            "platform_use_case": "dynamic-production-scheduling-with-quantum-inspired-metaheuristics",
        },
    }

    try:
        generate_additional_output(raw, result_dict, algorithm_name=ALGORITHM_NAME)
    except Exception:
        pass

    return {"result": result_dict}


def run(data: Dict[str, Any], solver_params: Dict[str, Any] = None,
        extra_arguments: Dict[str, Any] = None) -> Dict[str, Any]:
    """QCentroid platform entry point."""
    solver_params = solver_params or {}
    extra_arguments = extra_arguments or {}
    kwargs = dict(
        max_exec_time_m=float(extra_arguments.get("max_exec_time_m",
                                                  solver_params.get("max_exec_time_m", 5.0))),
        mip_gap=float(solver_params.get("mip_gap", 0.05)),
        extended=bool(solver_params.get("extended", False)),  # round 2 default
        solver=str(solver_params.get("solver", "auto")).lower(),
    )
    out = solver({"data": data}, **kwargs)
    return out["result"]


def _on_time_pct(schedule, jobs):
    if not jobs:
        return 100.0
    by_job = {}
    for s in schedule:
        by_job.setdefault(s["job_id"], 0)
        by_job[s["job_id"]] = max(by_job[s["job_id"]], s["end"])
    on_time = sum(1 for j in jobs if by_job.get(j["id"]) is not None
                  and by_job[j["id"]] <= j.get("due_date", 10**9))
    return round(100.0 * on_time / max(1, len(jobs)), 2)


def _per_machine_utilization(schedule, machines, horizon):
    out = {}
    for m in machines:
        mid = m["id"]
        ops = [s for s in schedule if s["machine_id"] == mid]
        busy = sum(s["end"] - s["start"] for s in ops)
        out[mid] = {
            "utilization_percentage": round(100.0 * busy / horizon, 2) if horizon else 0.0,
            "total_processing_hours": busy,
            "idle_time_hours": max(0, horizon - busy),
            "num_jobs": len(ops),
        }
    return out


def _per_job_metrics(schedule, jobs):
    by_job = {}
    for s in schedule:
        by_job.setdefault(s["job_id"], 0)
        by_job[s["job_id"]] = max(by_job[s["job_id"]], s["end"])
    out = {}
    for j in jobs:
        completion = by_job.get(j["id"], 0)
        due = j.get("due_date", 0)
        tardiness = max(0, completion - due)
        out[j["id"]] = {"completion_time": completion, "due_date": due,
                        "tardiness": tardiness, "on_time": tardiness == 0}
    return out


def _count_changeovers(schedule):
    by_m: dict = {}
    for s in schedule:
        by_m.setdefault(s["machine_id"], []).append(s)
    changeovers = 0
    for segs in by_m.values():
        segs.sort(key=lambda x: x["start"])
        for a, b in zip(segs, segs[1:]):
            if a["job_id"] != b["job_id"]:
                changeovers += 1
    return changeovers


def _gantt_data(schedule, machines):
    return [
        {"task_id": f'{s["job_id"]}.{s.get("op_id", 0)}',
         "resource_id": s["machine_id"], "start_hour": s["start"],
         "end_hour": s["end"], "label": f'job {s["job_id"]}'}
        for s in schedule
    ]


def _error_result(phase, exc, started_utc, t0, dataset_sha256):
    wall = time.perf_counter() - t0
    return {
        "result": {
            "objective_value": None, "makespan_hours": None, "total_tardiness_hours": None,
            "on_time_delivery_pct": 0.0, "avg_machine_utilization_pct": 0.0, "total_changeovers": 0,
            "benchmark": {"execution_cost": {"value": 0.0, "unit": "credits"},
                          "time_elapsed": f"{wall:.1f}s", "energy_consumption": 0.0},
            "schedule": {"assignments": [], "gantt_data": [], "makespan": 0,
                         "total_tardiness": 0, "total_idle_time": 0, "total_energy_kwh": 0,
                         "total_cost": 0, "jobs_on_time": 0, "jobs_late": 0,
                         "on_time_percentage": 0},
            "gantt_data": [], "total_energy_kwh": 0,
            "machine_utilization": {}, "job_metrics": {},
            "solution_status": "error",
            "solver_info": {"solver_version": SOLVER_VERSION, "solver_family": SOLVER_FAMILY,
                            "specialist_id": SPECIALIST_ID, "specialist_source": SPECIALIST_SOURCE,
                            "error_phase": phase, "error_type": type(exc).__name__,
                            "error_message": str(exc), "traceback": traceback.format_exc()},
            "computation_metrics": {"wall_time_s": wall, "algorithm": ALGORITHM_NAME},
            "constraint_violations": [{"severity": "fatal", "phase": phase, "message": str(exc)}],
            "quality_metrics": {"feasible": False},
            "audit": {"solver_version": SOLVER_VERSION, "specialist_id": SPECIALIST_ID,
                      "specialist_source": SPECIALIST_SOURCE, "dataset_sha256": dataset_sha256,
                      "run_started_at_utc": started_utc,
                      "run_finished_at_utc": datetime.now(timezone.utc).isoformat()},
        }
    }


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        with open(sys.argv[1]) as f:
            inp = json.load(f)
    else:
        from synthetic import generate_small
        inp = generate_small()
    out = solver(inp, max_exec_time_m=2)
    print(json.dumps(out, indent=2, default=str))
