# optspec-scheduling-solver

Time-indexed Mixed-Integer Linear Programming solver for QCentroid use case **743**
(`dynamic-production-scheduling-with-quantum-inspired-metaheuristics`),
generated using the [opt-specialists](https://github.com/georgekorpas/opt-specialists)
discipline (`00_classifier.md` → `03_MIP_specialist.md`).

**Experiment:** does a solver generated using the opt-specialists discipline
(classifier → matched specialist) outperform one generated without it
(see [`CrlsK/classical-scheduling-solver`](https://github.com/CrlsK/classical-scheduling-solver))
on the QCentroid Dynamic Production Scheduling use case?

## Pipeline

```
QCentroid use case 743 page (Business / Feasibility / Scientific approach / Technical details)
    ▼
01_use_case_understanding.md     ← business + LaTeX formulation + critical analysis
    ▼
00_classifier.md                 ← reads the LaTeX, picks ONE specialist
    ▼
02_classifier_output.json        ← {"specialist_id": "MIP", "confidence": "high", ...}
    ▼
03_MIP_specialist.md             ← Phase 1 verify, Phase 2 restate, Phase 3 implement, Phase 4 self-check
    ▼
qcentroid.py + mip_model.py + adapter.py + outputs.py + synthetic.py + app.py
    ▼
QCentroid build → smoke-test → benchmark vs classical-scheduling-solver
```

## Headline result (local A/B run, 2026-05-08)

| Instance | KPI                  | Treatment (opt-specialists MIP) | Baseline (greedy, no discipline) | Improvement |
|----------|----------------------|---------------------------------|----------------------------------|-------------|
| small    | objective_value      | 4.0                             | 5.0                              | +20.0 %     |
| small    | makespan_hours       | 4                               | 5                                | +20.0 %     |
| medium   | makespan_hours       | 12                              | 18                               | +33.3 %     |
| medium   | objective_value      | 16.50                           | 18.0                             | +8.3 %      |

Treatment is **optimal** within 1 % MIP-gap; baseline is feasible greedy. Re-run with:

```bash
cd ab_test
python run_ab_test.py --treatment .. --baseline ../baseline_greedy --instances small,medium --report report.html
```

## Files

- `qcentroid.py` — entry point. `run(data, solver_params, extra_arguments)` is the QCentroid platform contract; `solver(input_data, **kwargs)` is the in-process API.
- `mip_model.py` — Pyomo time-indexed MIP (Pyomo + HiGHS, Gurobi auto-detected).
- `adapter.py` — QCentroid platform schema → internal canonical schema (matches Technical Details tab).
- `outputs.py` — writes `additional_output/{gantt.html, schedule.json, audit.json, specialist_report.html}`.
- `synthetic.py` — reproducible reference instances (`generate_small`, `generate_medium`).
- `app.py` — runtime wrapper (mirrors the convention in `CrlsK/classical-scheduling-solver/app.py`).
- `requirements.txt`, `Dockerfile` — pinned deps + build image with build-time smoke check.
- `tests/test_smoke.py` — pytest suite.
- `01_use_case_understanding.md`, `02_classifier_output.json`, `03_specialist_blueprint.md` — design docs.
- `ab_test/run_ab_test.py` — A/B harness vs. the baseline greedy.
- `baseline_greedy/qcentroid.py` — control arm (one-pass EDD greedy, NO opt-specialists discipline).

## Deploy

1. Connect this repo to QCentroid as a new solver under use case 743 (`dynamic-production-scheduling-with-quantum-inspired-metaheuristics`).
2. Trigger build (`qc_trigger_solver_build`). The Dockerfile runs the small synthetic instance as a build-time smoke check.
3. Submit a job alongside the existing quantum-inspired metaheuristic solver (`qc_run_and_compare`). The platform's per-KPI charts populate from `makespan_hours`, `objective_value`, `on_time_delivery_pct`, `total_tardiness_hours`, `avg_machine_utilization_pct`, `total_changeovers`, plus the standard `benchmark` sub-dict (`execution_cost`, `time_elapsed`, `energy_consumption`).

## Sources

- [QCentroid use case 743](https://app.sandbox.qcentroid.com/use-cases/dynamic-production-scheduling-with-quantum-inspired-metaheuristics)
- [opt-specialists repository](https://github.com/georgekorpas/opt-specialists)
- A/B target: [`CrlsK/classical-scheduling-solver`](https://github.com/CrlsK/classical-scheduling-solver)
