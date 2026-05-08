# MIP Specialist Blueprint - Dynamic Production Scheduling

> Output of `03_MIP_specialist.md` Phase 1 (verification) and Phase 2
> (restate + decisions). Becomes the spec for the implementation.

## Phase 1 - Verification

The specialist independently reads the LaTeX and confirms the classifier's choice.

- ✅ Variables include continuous (`C_i`) and binary (`x_{ijt}`) - **mixed**.
- ✅ Objective is **affine** (weighted sum).
- ✅ Constraints are affine, including indicator-style availability gating
  (`x_{ijt} = 0` when `a_{jt} = 0`) - linearizes naturally with no Big-M.
- ✅ No quadratic terms. No transcendental terms.

**Verification: ACCEPTED. Class is MIP. Proceeding to Phase 2.**

## Phase 2 - Restatement

Decision variables:
- `x[i,j,t] in {0,1}` - time-indexed start-time encoding.
- `C[i] in Z_{>=0}` - job completion time.
- `T[i] in R_{>=0}` - tardiness.
- `Cmax in Z_{>=0}` - makespan.

Objective: `min α·Cmax + β·Σ_i w_i T_i + γ·Σ_{i,j,t} c_{ij}·x_{ijt} + δ·Σ_j z_j` (last term is the changeover penalty, only in extended mode).

Constraints (in implementation order):
1. **Assignment** - `Σ_{j,t} x[i,j,t] = 1 ∀ i`.
2. **Eligibility / availability** - pre-pruned at model-build time.
3. **Release time** - pre-pruned: `t < r[i]` excluded.
4. **Capacity / non-preemption (gap fix #5)** - `Σ_i Σ_{τ : τ ≤ t < τ+p[i,j]} x[i,j,τ] ≤ a[j,t]` for every `(j,t)`.
5. **Completion** - `C[i] ≥ Σ_{j,t} (t + p[i,j])·x[i,j,t]`.
6. **Makespan** - `Cmax ≥ C[i] for every i`.
7. **Tardiness** - `T[i] ≥ C[i] - d[i]; T[i] ≥ 0`.

Extensions (`extended=True`):
- multi-operation precedence (`x[i,o,j,t]`),
- `u[i,j]` job-on-machine indicator, `z[j]` changeover counter, **wired into objective with weight `δ`**,
- time-of-use energy `e[j,t]` instead of static `c[i,j]`,
- frozen-prefix masking via release-time forcing.

Structural notes:
- |J|·|M|·|T| binaries. Domain-pruning typically removes 60-90 %.
- LP relaxation is loose for time-indexed scheduling. HiGHS adds clique cuts internally.
- Coefficients in {0, 1, p_{ij}, c_{ij}}. Numerical scaling fine.
- Big-M not needed; encoding is naturally linear.

## Phase 2 - Decisions (defaulted)

| Decision         | Default                                    |
|------------------|--------------------------------------------|
| Modeling library | Pyomo                                      |
| Default solver   | HiGHS (open-source); Gurobi auto-detected  |
| MIP gap          | 0.01 (1 %)                                 |
| Time limit       | `max_exec_time_m`-driven, default 10 min   |
| Threads          | min(8, os.cpu_count())                     |
| Indicator        | Pre-pruned linear (no Big-M)               |
| Warm-start       | Off by default                              |

## Phase 4 - Self-check

- ✅ Every decision variable in the LaTeX appears in `mip_model.py`.
- ✅ Every constraint in the LaTeX appears in `mip_model.py`.
- ✅ Units consistent (slots, EUR).
- ✅ No coefficient spans more than 1e4.
- ✅ Solver call uses finite time limit + gap.
- ✅ Reads/writes `additional_output/` for the platform file viewer.
- ✅ Embeds `benchmark` dict (`execution_cost`, `time_elapsed`, `energy_consumption`).
- ✅ Embeds compliance fields (`solver_version`, `dataset_sha256`, `run_started_at_utc`, `specialist_source`).
