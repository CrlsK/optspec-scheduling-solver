# Use Case Understanding - Dynamic Production Scheduling

> Input bundle for the opt-specialists pipeline (`00_classifier.md` -> matched
> specialist). Business framing, feasibility profile, scientific approach
> verbatim from QCentroid problem 743, plus a critical analysis of where
> the published formulation needs to be extended.
>
> Source: <https://app.sandbox.qcentroid.com/use-cases/dynamic-production-scheduling-with-quantum-inspired-metaheuristics>
> · Tenant: Jindalstainless · QCentroid id `743` · Sector: Industry · Type: Optimization

## 1. Business framing (verbatim from QCentroid)

Jindal Stainless seeks to optimize production-job allocation across machines
and time slots in its manufacturing plants, accounting for machine
availability, maintenance windows, and order priorities. Quantum-inspired
metaheuristics (quantum-annealing-inspired heuristics or tensor-network
solvers) explore the large combinatorial scheduling space to find
near-optimal schedules faster than current classical heuristics. **Inputs**:
machine capability, job processing/setup times, maintenance schedules, labor
shifts, material availability, historical production logs. **Outputs**:
executable schedules, utilization metrics, throughput projections,
feasibility / constraint-violation flags. **Success metrics**: makespan,
machine idle time, change-overs, on-time delivery, schedule computation
latency.

## 2. Feasibility profile (verbatim)

The use case falls within combinatorial NP-hard problems. Quantum-inspired
metaheuristics (annealing-inspired solvers, tensor networks) are
demonstrably applicable in academic and early-industrial settings, **without
guaranteeing they outperform the best classical metaheuristics on all
instances**. Limitations: not guaranteed to outperform classical
metaheuristics; MES/ERP integration non-trivial; current quantum hardware
not practical for industrial scheduling - focus on quantum-inspired
classical solvers. Cited reference:
sciencedirect.com/science/article/abs/pii/S0952197624017937.

## 3. Scientific approach as published by QCentroid

### 3.1 Sets

J = jobs, indexed by i. M = machines, indexed by j. T = discrete time
slots in the planning horizon, indexed by t.

### 3.2 Parameters

p_{ij}, a_{jt} ∈ {0,1}, r_i, d_i, w_i, c_{ij}.

### 3.3 Decision variables

x_{ijt} ∈ {0,1}: 1 if job i starts on machine j at time t.
C_i ≥ 0: completion time of job i.

### 3.4 Objective function

min α·C_max + β·Σ_i w_i T_i + γ·Σ_{i,j,t} c_{ij} x_{ijt}

### 3.5 Constraints (as published)

- **Job Assignment** - one job, one machine, one start time.
- **Machine Capacity** - at most one job per machine per time.
- **Release Time** - jobs cannot start before r_i.
- **Completion Time Definition** - end = start + processing.
- **Machine Availability** - jobs only on available machines.
- **Non-preemption** - jobs run to completion once started.

## 4. Critical analysis - is this the right scientific approach?

**Verdict.** The published formulation is a textbook *parallel-machine
scheduling with releases, due dates, and weights*. Internally consistent,
but **not a faithful model of the use case as written**. Six concrete gaps:

| # | Gap                                                                                  |
|---|--------------------------------------------------------------------------------------|
| 1 | Multi-operation jobs / routings missing - model collapses a job to one operation     |
| 2 | Sequence-dependent setups / changeovers not modeled, but `total_changeovers` is a top-level KPI |
| 3 | Dynamic / rolling-horizon / frozen-prefix semantics absent                          |
| 4 | Energy collapsed into static c_{ij}, no time-of-use tariff e_{jt}                   |
| 5 | Non-preemption asserted but not encoded (capacity constraint as written is ambiguous)|
| 6 | Schema declares `labor` and `materials` - neither appears in math                   |

**Scaling.** Time-indexed encoding has |J|·|M|·|T| binaries. 50 × 20 × 480 =
480 000 binaries. Industry moves to CP-SAT (interval variables + NoOverlap)
or column generation at this scale.

## 5. Extended formulation (used by this solver)

Closes gaps 1-5; gap 6 declared out-of-scope for v1, reported via
constraint_violations.

Additional sets: O_i = ordered ops of job i; M_{io} subset M = machines
eligible for op (i, o).

Additional parameters: p_{iojt} (time-dependent allowed), s_{ii'j}
(sequence-dependent setup), e_{jt} (time-of-use energy), f_i ∈ {0,1}
(frozen indicator).

Lifted decision variables:
- x_{iojt} ∈ {0,1}: op (i, o) starts on machine j at time t.
- u_{ij} ∈ {0,1}: job i runs on machine j (any op).
- z_j ∈ Z_{>=0}: changeover counter on machine j.

Objective adds δ·Σ_j z_j (changeover term, **wired into objective with
weight δ in the extended path**).

Explicit non-overlap (gap 5):
Σ_{i,o : t-p_{ij}+1 <= τ <= t} x_{iojτ} <= a_{jt}  for all (j, t).

Operation precedence within a job (gap 1):
Σ_{j,t} t·x_{i,o,j,t} >= Σ_{j,t} (t + p_{ij})·x_{i,o-1,j,t}  for all i, o ≥ 2.

Frozen prefix (gap 3): for each i with f_i = 1, fix x at the committed
(j*, t*).

## 6. Output schema declared by QCentroid (verified via qc_get_use_case_schema)

Top-level numeric KPIs the solver populates:

| Field                          | Direction      |
|--------------------------------|----------------|
| `makespan_hours`              | lower-better   |
| `objective_value`             | lower-better   |
| `on_time_delivery_pct`        | higher-better  |
| `total_tardiness_hours`       | lower-better   |
| `avg_machine_utilization_pct` | higher-better  |
| `total_changeovers`           | lower-better   |

Plus the QCentroid-standard `benchmark` sub-dict (`execution_cost`,
`time_elapsed`, `energy_consumption`), `schedule`, `gantt_data`,
`solver_info`, `computation_metrics`, `constraint_violations`,
`quality_metrics`, `solution_status`. The solver writes `gantt.html`,
`schedule.json`, `audit.json`, and `specialist_report.html` into
`./additional_output/` for the platform's per-executor file viewer.

## 7. Sample datasets

Technical Details tab states: **"There are no sample datasets available
for this use case."** This solver therefore ships its own synthetic data
generator (`synthetic.py`) with two reference instances:

- `small`: 8 jobs × 4 machines × 1 op/job - exercises the published §3 formulation.
- `medium`: 20 jobs × 8 machines × 2-4 ops/job + setup matrix + maintenance + ToU energy - exercises the §5 extensions.

## 8. A/B competitors on the platform

Two existing solvers are attached to use case 743:

| Solver name                                          | Family               |
|------------------------------------------------------|----------------------|
| `jindalstainless-classical-scheduling-alns-cpu`     | Classical ALNS       |
| `jindalstainless-quantum-scheduling-qubo-sqa-cpu`   | Quantum-inspired QUBO + SQA |

The new `optspec-mip-scheduling-cpu` solver (this repo) competes against
both, with a deterministic MIP-with-certificate guarantee that the
metaheuristics don't provide.
