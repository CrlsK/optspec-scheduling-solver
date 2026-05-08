"""Smoke test - runs the small + medium synthetic instances and asserts schema."""
import sys, os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from qcentroid import solver
from synthetic import generate_small, generate_medium


_REQUIRED_KPIS = [
    "objective_value", "makespan_hours", "total_tardiness_hours",
    "on_time_delivery_pct", "avg_machine_utilization_pct", "total_changeovers",
]


def _check(result):
    r = result["result"]
    for k in _REQUIRED_KPIS:
        assert k in r, f"missing top-level KPI {k}"
    assert "benchmark" in r and {"execution_cost", "time_elapsed", "energy_consumption"} <= set(r["benchmark"])


def test_small():
    out = solver(generate_small(), max_exec_time_m=1)
    _check(out)
    assert out["result"]["solution_status"] in ("optimal", "feasible", "feasible_time_limit")
    assert len(out["result"]["schedule"]) > 0


def test_medium():
    out = solver(generate_medium(), max_exec_time_m=2)
    _check(out)
    assert out["result"]["solution_status"] in ("optimal", "feasible", "feasible_time_limit")


if __name__ == "__main__":
    test_small()
    test_medium()
    print("OK")
