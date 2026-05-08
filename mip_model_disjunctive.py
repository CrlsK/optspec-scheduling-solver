"""
mip_model_disjunctive.py — Disjunctive Big-M FJSP MIP.

Iter 2 architecture per Sustainability 15(1):776 (2023): replaces the
time-indexed encoding with a sequencing-based disjunctive formulation.
Solves the SAME multi-operation flexible job-shop problem the heuristics
solve, so the benchmark is apples-to-apples.

Variables
---------
x[i, o, j]                  in {0,1}   op (i,o) assigned to machine j
y[(i1,o1), (i2,o2), j]      in {0,1}   on machine j, op (i2,o2) follows op (i1,o1)
s[i, o]                     in R_{>=0} start time of op (i,o)
c[i, o]                     in R_{>=0} completion of op (i,o)
T[i]                        in R_{>=0} tardiness of job i
Cmax                        in R_{>=0} makespan

Constraints
-----------
A1. Assignment:           sum_j x[i,o,j] = 1
A2. Eligibility:          x[i,o,j] = 0 if j not eligible for (i,o)
P1. Precedence in-job:    s[i, o+1] >= c[i, o]
P2. Op duration:          c[i,o] = s[i,o] + sum_j p[i,o,j] * x[i,o,j]
D1. Disjunctive sequencing on machine j (Big-M):
    s[i2,o2] >= c[i1,o1] + S[j, grade(i1), grade(i2)]
              - M * (3 - x[i1,o1,j] - x[i2,o2,j] - y[(i1,o1),(i2,o2),j])
D2. Symmetry: y[a,b,j] + y[b,a,j] >= x[a,j] + x[b,j] - 1   (one of them is on j -> one direction picked)
M1. Makespan:             Cmax >= c[i, last_op_i]
T1. Tardiness:            T[i] >= Cmax_i - d[i]; T[i] >= 0
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Tuple, Optional

import pyomo.environ as pyo


def build_and_solve(
    internal: Dict[str, Any],
    time_limit_s: float,
    mip_gap: float,
    solver_name: str,
    extended: bool = True,
    warm_start: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Disjunctive MIP. extended flag is accepted for interface parity but
    multi-op is always honored (it's the whole point of this formulation).
    """
    horizon = internal["horizon"]
    jobs = internal["jobs"]
    machines = internal["machines"]
    weights = internal["objective_weights"]
    BIG_M = float(horizon * 2 + 100)  # large enough to dominate any precedence delta

    # -------- index sets --------
    op_keys: List[Tuple[str, int]] = []
    op_eligible: Dict[Tuple[str, int], List[str]] = {}
    op_p: Dict[Tuple[str, int, str], int] = {}  # (i, o, j) -> p
    op_energy: Dict[Tuple[str, int, str], float] = {}
    job_due: Dict[str, int] = {}
    job_release: Dict[str, int] = {}
    job_weight_v: Dict[str, float] = {}
    job_op_seq: Dict[str, List[int]] = {}  # job -> list of op_ids in routing order

    for j in jobs:
        ids = []
        for op in j["ops"]:
            key = (j["id"], op["id"])
            op_keys.append(key)
            elig = []
            for alt in op["alternatives"]:
                m_id = alt["machine"]
                p = max(1, int(alt["p"]))
                elig.append(m_id)
                op_p[(j["id"], op["id"], m_id)] = p
                op_energy[(j["id"], op["id"], m_id)] = float(alt.get("energy_kwh", 0.0))
            op_eligible[key] = elig
            ids.append(op["id"])
        job_op_seq[j["id"]] = ids
        job_due[j["id"]] = int(j["due_date"])
        job_release[j["id"]] = int(j.get("release", 0))
        job_weight_v[j["id"]] = float(j["weight"])

    machine_ids = [m["id"] for m in machines]

    # x triples (i, o, j) only for eligible j
    x_triples = [(i, o, j) for (i, o) in op_keys for j in op_eligible[(i, o)]]
    # y sequence pairs on each machine: any two ops eligible on j
    y_idx: List[Tuple[str, int, str, int, str]] = []
    by_machine: Dict[str, List[Tuple[str, int]]] = {}
    for (i, o) in op_keys:
        for j in op_eligible[(i, o)]:
            by_machine.setdefault(j, []).append((i, o))
    for j, ops_on in by_machine.items():
        for a in range(len(ops_on)):
            for b in range(len(ops_on)):
                if a == b:
                    continue
                i1, o1 = ops_on[a]
                i2, o2 = ops_on[b]
                y_idx.append((i1, o1, i2, o2, j))

    model = pyo.ConcreteModel()
    model.X_TRIPLES = pyo.Set(initialize=x_triples, dimen=3)
    model.Y_IDX = pyo.Set(initialize=y_idx, dimen=5)
    model.OPS = pyo.Set(initialize=op_keys, dimen=2)
    model.JOBS = pyo.Set(initialize=[j["id"] for j in jobs])
    model.MACHINES = pyo.Set(initialize=machine_ids)

    model.x = pyo.Var(model.X_TRIPLES, within=pyo.Binary)
    model.y = pyo.Var(model.Y_IDX, within=pyo.Binary)
    model.s = pyo.Var(model.OPS, within=pyo.NonNegativeReals, bounds=(0, BIG_M))
    model.c = pyo.Var(model.OPS, within=pyo.NonNegativeReals, bounds=(0, BIG_M))
    model.T = pyo.Var(model.JOBS, within=pyo.NonNegativeReals, bounds=(0, BIG_M))
    model.Cmax = pyo.Var(within=pyo.NonNegativeReals, bounds=(0, BIG_M))

    # -------- constraints --------
    def _A1_assign(m, i, o):
        return sum(m.x[i, o, j] for j in op_eligible[(i, o)]) == 1
    model.A1_Assign = pyo.Constraint(model.OPS, rule=_A1_assign)

    def _P2_duration(m, i, o):
        return m.c[i, o] == m.s[i, o] + sum(op_p[(i, o, j)] * m.x[i, o, j] for j in op_eligible[(i, o)])
    model.P2_Duration = pyo.Constraint(model.OPS, rule=_P2_duration)

    # release time: s[i, first_op] >= release_i
    first_op_pairs = [(j["id"], j["ops"][0]["id"]) for j in jobs]
    model.FIRST_OP = pyo.Set(initialize=first_op_pairs, dimen=2)

    def _release_rule(m, i, o):
        return m.s[i, o] >= job_release[i]
    model.Release = pyo.Constraint(model.FIRST_OP, rule=_release_rule)

    # P1 precedence within job (only for jobs with >1 ops)
    prec_pairs = []
    prev_of = {}
    for j_id, ids in job_op_seq.items():
        for k in range(1, len(ids)):
            prec_pairs.append((j_id, ids[k]))
            prev_of[(j_id, ids[k])] = ids[k - 1]
    model.PREC_PAIRS = pyo.Set(initialize=prec_pairs, dimen=2)

    def _P1_precedence(m, i, o):
        return m.s[i, o] >= m.c[i, prev_of[(i, o)]]
    if prec_pairs:
        model.P1_Precedence = pyo.Constraint(model.PREC_PAIRS, rule=_P1_precedence)

    # D1 disjunctive sequencing on machine
    setup_default = 0
    setup_mat = internal.get("setup_matrix") or {}

    def _D1_disj(m, i1, o1, i2, o2, j):
        # setup time depends on (j, i1->i2). Default constant for now.
        s_jit = 0
        if isinstance(setup_mat.get(j), dict):
            s_jit = int(setup_mat[j].get("default_minutes", 0)) // max(1, internal.get("slot_minutes", 60))
        return m.s[i2, o2] >= m.c[i1, o1] + s_jit - BIG_M * (3 - m.x[i1, o1, j] - m.x[i2, o2, j] - m.y[i1, o1, i2, o2, j])
    model.D1_Disj = pyo.Constraint(model.Y_IDX, rule=_D1_disj)

    # D2 symmetry: if both ops are on j, exactly one direction wins
    def _D2_sym(m, i1, o1, i2, o2, j):
        if (i1, o1) == (i2, o2):
            return pyo.Constraint.Skip
        # only need one constraint per unordered pair
        if (i1, o1) > (i2, o2):
            return pyo.Constraint.Skip
        # if both on j, y_a_b + y_b_a >= 1
        return m.y[i1, o1, i2, o2, j] + m.y[i2, o2, i1, o1, j] >= m.x[i1, o1, j] + m.x[i2, o2, j] - 1
    model.D2_Sym = pyo.Constraint(model.Y_IDX, rule=_D2_sym)

    # M1 makespan
    last_op_pairs = [(j["id"], j["ops"][-1]["id"]) for j in jobs]
    model.LAST_OP = pyo.Set(initialize=last_op_pairs, dimen=2)
    model.M1_Makespan = pyo.Constraint(model.LAST_OP, rule=lambda m, i, o: m.Cmax >= m.c[i, o])

    # T1 tardiness
    def _T1(m, i):
        last_o = job_op_seq[i][-1]
        return m.T[i] >= m.c[i, last_o] - job_due[i]
    model.T1_Tardiness = pyo.Constraint(model.JOBS, rule=_T1)

    # -------- objective --------
    energy_tou = internal.get("energy_tou") or {}

    def _energy_term():
        terms = []
        for (i, o, j) in x_triples:
            ekwh = op_energy.get((i, o, j), 0.0)
            avg_price = 0.10
            if energy_tou and j in energy_tou:
                avg_price = sum(energy_tou[j]) / max(1, len(energy_tou[j]))
            terms.append(ekwh * avg_price * model.x[i, o, j])
        return sum(terms) if terms else 0

    obj_expr = (
        weights["alpha"] * model.Cmax
        + weights["beta"] * sum(job_weight_v[i] * model.T[i] for i in model.JOBS)
        + weights["gamma"] * _energy_term()
    )
    model.Obj = pyo.Objective(expr=obj_expr, sense=pyo.minimize)

    # -------- warm start --------
    n_warm = 0
    if warm_start:
        for ws in warm_start:
            i = ws.get("job_id")
            o = ws.get("op_id", 0)
            j = ws.get("machine_id")
            t = ws.get("start", ws.get("start_time", 0))
            if (i, o, j) in op_p:
                try:
                    model.x[i, o, j].set_value(1)
                    model.s[i, o].set_value(float(t))
                    n_warm += 1
                except Exception:
                    pass

    # -------- solve --------
    chosen, results = _solve(model, solver_name, time_limit_s, mip_gap)

    # -------- extract --------
    return _extract(model, x_triples, op_p, op_energy, jobs, results, chosen, n_warm)


def _solve(model, solver_name, time_limit_s, mip_gap):
    chosen = solver_name
    if chosen == "auto":
        chosen = "gurobi" if os.environ.get("GRB_LICENSE_FILE") else "highs"
    if chosen == "gurobi":
        opt = pyo.SolverFactory("gurobi")
        opt.options["TimeLimit"] = float(time_limit_s)
        opt.options["MIPGap"] = float(mip_gap)
        opt.options["Threads"] = max(1, min(8, os.cpu_count() or 1))
    elif chosen == "highs":
        opt = pyo.SolverFactory("appsi_highs")
        opt.config.time_limit = float(time_limit_s)
        opt.config.mip_gap = float(mip_gap)
    else:
        raise ValueError(f"Unsupported solver: {solver_name}")
    results = opt.solve(model, tee=False)
    return chosen, results


def _extract(model, x_triples, op_p, op_energy, jobs, results, chosen, n_warm):
    status = "unknown"
    try:
        tc = str(results.solver.termination_condition).lower()
        if "optimal" in tc:
            status = "optimal"
        elif "feasible" in tc:
            status = "feasible"
        elif "timelimit" in tc:
            status = "feasible_time_limit"
        elif "infeasible" in tc:
            status = "infeasible"
    except Exception:
        pass

    schedule = []
    for (i, o, j) in x_triples:
        try:
            v = pyo.value(model.x[i, o, j])
        except Exception:
            v = 0
        if v is not None and v >= 0.5:
            try:
                s_val = float(pyo.value(model.s[i, o]))
                c_val = float(pyo.value(model.c[i, o]))
            except Exception:
                continue
            schedule.append({
                "job_id": i, "op_id": o, "machine_id": j,
                "start": int(round(s_val)), "end": int(round(c_val)),
                "p": op_p[(i, o, j)],
            })
    schedule.sort(key=lambda s: (s["machine_id"], s["start"]))

    makespan = max((s["end"] for s in schedule), default=0)
    weighted_tardiness = 0.0
    for j in jobs:
        c = max((s["end"] for s in schedule if s["job_id"] == j["id"]), default=0)
        weighted_tardiness += float(j["weight"]) * max(0, c - int(j["due_date"]))

    obj_val = pyo.value(model.Obj)
    energy_kwh = sum(op_energy.get((s["job_id"], s["op_id"], s["machine_id"]), 0.0) for s in schedule)

    try:
        n_vars = sum(1 for _ in model.component_data_objects(pyo.Var, active=True))
        n_cons = sum(1 for _ in model.component_data_objects(pyo.Constraint, active=True))
    except Exception:
        n_vars = n_cons = None

    best_bound = None
    mip_gap_achieved = None
    try:
        best_bound = float(results.problem.lower_bound)
        if obj_val and best_bound is not None and obj_val != 0:
            mip_gap_achieved = abs(obj_val - best_bound) / max(1e-9, abs(obj_val))
    except Exception:
        pass

    return {
        "status": status,
        "schedule": schedule,
        "makespan": int(makespan),
        "weighted_tardiness": float(weighted_tardiness),
        "objective_value": float(obj_val) if obj_val is not None else None,
        "energy_kwh": float(energy_kwh),
        "solver_name": chosen,
        "n_variables": n_vars,
        "n_constraints": n_cons,
        "n_binaries_after_pruning": len(x_triples),  # disjunctive: assignment binaries
        "best_bound": best_bound,
        "mip_gap_achieved": mip_gap_achieved,
        "warm_start_hits": n_warm,
        "constraint_violations": [],
    }
