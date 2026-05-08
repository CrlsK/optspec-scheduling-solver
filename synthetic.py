"""
synthetic.py — Reproducible synthetic input data conforming to the QCentroid
Technical Details schema for use case 743.
"""
from __future__ import annotations

import random
from typing import Any, Dict


def generate_small(seed: int = 42) -> Dict[str, Any]:
    rng = random.Random(seed)
    n_jobs, n_machines, horizon_hours = 8, 4, 24
    machines = [{"id": f"M{m+1}", "permitted_operations": []} for m in range(n_machines)]
    pt: Dict[str, Any] = {}
    jobs = []
    for j in range(n_jobs):
        jid = f"J{j+1}"
        pt[jid] = {}
        for m in machines:
            pt[jid][m["id"]] = {"minutes": rng.randint(60, 240), "energy_kwh": round(rng.uniform(2.0, 5.0), 2)}
        jobs.append({"id": jid, "release_hour": 0, "due_hour": horizon_hours, "priority": rng.choice([1, 1, 2, 3])})
    return {
        "data": {
            "num_jobs": n_jobs, "num_machines": n_machines,
            "planning_horizon_hours": horizon_hours,
            "planning_horizon": {"hours": horizon_hours, "slot_minutes": 60},
            "jobs": jobs, "machines": machines, "processing_times": pt,
            "maintenance_schedules": [],
            "business_constraints": {"objective_weights": {"alpha": 1.0, "beta": 1.0, "gamma": 0.1, "delta": 0.5}},
        }
    }


def generate_medium(seed: int = 42) -> Dict[str, Any]:
    rng = random.Random(seed)
    n_jobs, n_machines, horizon_hours = 20, 8, 48
    op_types = ["cut", "mill", "grind", "anneal", "inspect"]
    machines = []
    for m in range(n_machines):
        caps = rng.sample(op_types, k=rng.randint(2, 4))
        machines.append({"id": f"M{m+1}", "permitted_operations": caps})
    pt: Dict[str, Any] = {}
    jobs = []
    for j in range(n_jobs):
        jid = f"J{j+1}"
        n_ops = rng.randint(2, 4)
        routing = []
        for o in range(n_ops):
            t = op_types[o % len(op_types)]
            eligible = [m["id"] for m in machines if t in m["permitted_operations"]]
            if not eligible:
                eligible = [machines[0]["id"]]
            routing.append({"id": o, "type": t, "eligible_machines": eligible,
                            "default_processing_minutes": rng.randint(45, 180),
                            "default_setup_minutes": rng.choice([0, 15, 30])})
        pt[jid] = {}
        for o, op in enumerate(routing):
            pt[jid][o] = {}
            for m_id in op["eligible_machines"]:
                pt[jid][o][m_id] = {"minutes": rng.randint(45, 180), "energy_kwh": round(rng.uniform(2.0, 8.0), 2)}
        jobs.append({"id": jid, "release_hour": rng.randint(0, 6), "due_hour": rng.randint(20, horizon_hours),
                     "priority": rng.choice([1, 1, 2, 3, 5]), "routing": routing,
                     "required_operations": [op["type"] for op in routing]})
    setup_matrix = {m["id"]: {"default_minutes": 15} for m in machines}
    maintenance = [{"machine_id": "M3", "start_hour": 8, "end_hour": 12},
                   {"machine_id": "M5", "start_hour": 30, "end_hour": 34}]
    night, day, peak = 0.07, 0.13, 0.22
    tariff_24h = [night] * 6 + [day] * 8 + [peak] * 4 + [day] * 4 + [night] * 2
    tariff = (tariff_24h * ((horizon_hours // 24) + 1))[:horizon_hours]
    energy_tou = {m["id"]: tariff for m in machines}
    return {
        "data": {
            "num_jobs": n_jobs, "num_machines": n_machines,
            "planning_horizon_hours": horizon_hours,
            "planning_horizon": {"hours": horizon_hours, "slot_minutes": 60},
            "jobs": jobs, "machines": machines, "processing_times": pt,
            "setup_matrix": setup_matrix, "maintenance_schedules": maintenance,
            "business_constraints": {"energy_tariff": energy_tou,
                                     "objective_weights": {"alpha": 1.0, "beta": 2.0, "gamma": 0.2, "delta": 1.0}},
        }
    }
