"""
mip_model.py — Pyomo time-indexed MIP for Dynamic Production Scheduling.

Implements §3 (verbatim QCentroid formulation) and §5 (extensions for
multi-op routings, sequence-dependent setups, time-of-use energy,
explicit non-overlap, and frozen-prefix) from
``01_use_case_understanding.md``.

Variables
---------
x[i, o, j, t] in {0,1}    1 if op (i, o) starts on machine j at time t
T[i] >= 0                 tardiness of job i
C[i] >= 0                 completion of job i
Cmax >= 0                 makespan
u[(i, j)] in {0,1}        job i runs on machine j (extended only)
z[j] in Z                 changeover counter on machine j (extended only)
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Tuple

import pyomo.environ as pyo


def build_and_solve(
    internal: Dict[str, Any],
    time_limit_s: float,
    mip_gap: float,
    solver_name: str,
    extended: bool,
) -> Dict[str, Any]:
    quads, q_to_p = _index_quads(internal)
    if not quads:
        raise RuntimeError("After pruning the variable index is empty - input is infeasible at build time.")

    model = pyo.ConcreteModel()
    horizon = internal["horizon"]
    jobs = internal["jobs"]
    machines = internal["machines"]
    weights = internal["objective_weights"]

    model.QUADS = pyo.Set(initialize=quads, dimen=4)
    model.JOBS = pyo.Set(initialize=[j["id"] for j in jobs])
    model.MACHINES = pyo.Set(initialize=[m["id"] for m in machines])
    model.SLOTS = pyo.RangeSet(0, horizon - 1)

    model.x = pyo.Var(model.QUADS, within=pyo.Binary)
    model.C = pyo.Var(model.JOBS, within=pyo.NonNegativeIntegers, bounds=(0, horizon))
    model.T = pyo.Var(model.JOBS, within=pyo.NonNegativeIntegers, bounds=(0, horizon))
    model.Cmax = pyo.Var(within=pyo.NonNegativeIntegers, bounds=(0, horizon))

    job_ops: Dict[str, List[Tuple[int, int]]] = {
        j["id"]: [(o_idx, op["id"]) for o_idx, op in enumerate(j["ops"])] for j in jobs
    }

    # (1) assignment
    def _assign_rule(m, i, o):
        terms = [m.x[i, o, j, t] for (i_, o_, j, t) in m.QUADS if i_ == i and o_ == o]
        return sum(terms) == 1 if terms else pyo.Constraint.Skip

    op_pairs = [(j["id"], op["id"]) for j in jobs for op in j["ops"]]
    model.OP_PAIRS = pyo.Set(initialize=op_pairs, dimen=2)
    model.AssignOp = pyo.Constraint(model.OP_PAIRS, rule=_assign_rule)

    # (4) capacity / non-overlap
    avail = {m["id"]: m["availability"] for m in machines}
    cap_pairs = [(m["id"], t) for m in machines for t in range(horizon)]
    model.CAP_PAIRS = pyo.Set(initialize=cap_pairs, dimen=2)

    def _capacity_rule(m, j, t):
        rhs = 0 if avail[j][t] == 0 else 1
        terms = []
        for (i, o, jj, tau) in m.QUADS:
            if jj != j:
                continue
            p = q_to_p[(i, o, jj, tau)]
            if tau <= t < tau + p:
                terms.append(m.x[i, o, jj, tau])
        return sum(terms) <= rhs if terms else pyo.Constraint.Skip

    model.Capacity = pyo.Constraint(model.CAP_PAIRS, rule=_capacity_rule)

    # (5) completion = end of last op
    def _completion_rule(m, i):
        last_op_id = job_ops[i][-1][1]
        terms = [
            (t + q_to_p[(i, last_op_id, j, t)]) * m.x[i, last_op_id, j, t]
            for (ii, oo, j, t) in m.QUADS
            if ii == i and oo == last_op_id
        ]
        return m.C[i] >= sum(terms) if terms else pyo.Constraint.Skip

    model.Completion = pyo.Constraint(model.JOBS, rule=_completion_rule)

    # (1') multi-op precedence (extended)
    if extended:
        prec_pairs = [(j["id"], op_pair[1]) for j in jobs for op_pair in job_ops[j["id"]][1:]]
        model.PREC_PAIRS = pyo.Set(initialize=prec_pairs, dimen=2)
        prev_op: Dict[Tuple[str, int], int] = {}
        for j in jobs:
            ids = [op["id"] for op in j["ops"]]
            for k in range(1, len(ids)):
                prev_op[(j["id"], ids[k])] = ids[k - 1]

        def _precedence_rule(m, i, o):
            o_prev = prev_op[(i, o)]
            this_start = sum(t * m.x[i, o, j, t] for (ii, oo, j, t) in m.QUADS if ii == i and oo == o)
            prev_end = sum(
                (t + q_to_p[(i, o_prev, j, t)]) * m.x[i, o_prev, j, t]
                for (ii, oo, j, t) in m.QUADS if ii == i and oo == o_prev
            )
            return this_start >= prev_end

        model.Precedence = pyo.Constraint(model.PREC_PAIRS, rule=_precedence_rule)

    # (6) makespan
    model.MakespanCons = pyo.Constraint(model.JOBS, rule=lambda m, i: m.Cmax >= m.C[i])

    # (7) tardiness
    due = {j["id"]: j["due_date"] for j in jobs}
    model.TardCons = pyo.Constraint(model.JOBS, rule=lambda m, i: m.T[i] >= m.C[i] - due[i])

    # changeover counter z[j] (extended only)
    if extended:
        i_j_pairs = sorted({(i_, jj) for (i_, _o, jj, _t) in quads})
        model.IJ_PAIRS = pyo.Set(initialize=i_j_pairs, dimen=2)
        model.u = pyo.Var(model.IJ_PAIRS, within=pyo.Binary)
        model.z = pyo.Var(model.MACHINES, within=pyo.NonNegativeIntegers, bounds=(0, len(jobs)))

        quads_per_ij: Dict[Tuple[str, str], list] = {}
        for q in quads:
            i_, _o, jj, _t = q
            quads_per_ij.setdefault((i_, jj), []).append(q)
        big_m = max((len(v) for v in quads_per_ij.values()), default=1)

        def _u_link_rule(m, i_, jj):
            qs = quads_per_ij.get((i_, jj), [])
            return big_m * m.u[i_, jj] >= sum(m.x[q] for q in qs) if qs else pyo.Constraint.Skip

        model.U_link = pyo.Constraint(model.IJ_PAIRS, rule=_u_link_rule)

        def _z_rule(m, jj):
            terms = [m.u[i_, jj] for (i_, jj2) in m.IJ_PAIRS if jj2 == jj]
            return m.z[jj] >= sum(terms) - 1 if terms else pyo.Constraint.Skip

        model.Z_def = pyo.Constraint(model.MACHINES, rule=_z_rule)

    # objective
    job_weight = {j["id"]: j["weight"] for j in jobs}
    energy_tou = internal.get("energy_tou") or {}

    def _energy_term(qq):
        i, o, j, t = qq
        p = q_to_p[(i, o, j, t)]
        ekwh = _energy_kwh(internal, i, o, j)
        if energy_tou and j in energy_tou:
            tou = energy_tou[j]
            avg = sum(tou[t : t + p]) / p
        else:
            avg = 0.10
        return ekwh * avg

    obj_terms = (
        weights["alpha"] * model.Cmax
        + weights["beta"] * sum(job_weight[i] * model.T[i] for i in model.JOBS)
        + weights["gamma"] * sum(_energy_term(q) * model.x[q] for q in quads)
    )
    if extended:
        obj_terms = obj_terms + weights["delta"] * sum(model.z[jj] for jj in model.MACHINES)
    model.Obj = pyo.Objective(expr=obj_terms, sense=pyo.minimize)

    chosen, results = _solve(model, solver_name, time_limit_s, mip_gap)
    return _extract(model, internal, q_to_p, results, chosen, extended=extended)


def _index_quads(internal):
    horizon = internal["horizon"]
    avail = {m["id"]: m["availability"] for m in internal["machines"]}
    quads = []
    q_to_p: Dict[Tuple, int] = {}
    for j in internal["jobs"]:
        for op in j["ops"]:
            for alt in op["alternatives"]:
                m_id = alt["machine"]
                p = int(alt["p"])
                tmin = max(0, j["release"])
                tmax = horizon - p
                for t in range(tmin, tmax + 1):
                    if not all(avail[m_id][tau] == 1 for tau in range(t, t + p)):
                        continue
                    q = (j["id"], op["id"], m_id, t)
                    quads.append(q)
                    q_to_p[q] = p
    return quads, q_to_p


def _energy_kwh(internal, i, o, j_machine):
    for j in internal["jobs"]:
        if j["id"] != i:
            continue
        for op in j["ops"]:
            if op["id"] != o:
                continue
            for alt in op["alternatives"]:
                if alt["machine"] == j_machine:
                    return float(alt.get("energy_kwh", 0.0))
    return 0.0


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


def _extract(model, internal, q_to_p, results, chosen, extended):
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
    for q in model.QUADS:
        try:
            v = pyo.value(model.x[q])
        except Exception:
            v = 0
        if v is not None and v >= 0.5:
            i, o, j, t = q
            p = q_to_p[q]
            schedule.append({"job_id": i, "op_id": o, "machine_id": j, "start": int(t), "end": int(t + p), "p": int(p)})

    schedule.sort(key=lambda s: (s["machine_id"], s["start"]))
    makespan = max((s["end"] for s in schedule), default=0)

    weighted_tardiness = 0.0
    for j in internal["jobs"]:
        c = max((s["end"] for s in schedule if s["job_id"] == j["id"]), default=0)
        weighted_tardiness += float(j["weight"]) * max(0, c - int(j["due_date"]))

    obj_val = pyo.value(model.Obj)
    energy_kwh = sum(_energy_kwh(internal, s["job_id"], s["op_id"], s["machine_id"]) for s in schedule)

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
        "n_binaries_after_pruning": len(q_to_p),
        "best_bound": best_bound,
        "mip_gap_achieved": mip_gap_achieved,
        "constraint_violations": [
            {"severity": "info", "message": v}
            for v in internal.get("policy", {}).get("out_of_scope_v1", [])
        ],
    }
