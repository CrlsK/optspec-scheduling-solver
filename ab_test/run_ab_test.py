"""
run_ab_test.py - A/B harness comparing the opt-specialists MIP solver
against any baseline solver on the same instances and computing per-KPI deltas.

Usage:
    python run_ab_test.py --treatment ..  --baseline ../baseline_greedy \\
                          --instances small,medium --report report.html

The KPI directions follow the QCentroid Technical Details tab:
    lower-better:  objective_value, makespan_hours, total_tardiness_hours, total_changeovers
    higher-better: on_time_delivery_pct, avg_machine_utilization_pct
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List

LOWER = ["objective_value", "makespan_hours", "total_tardiness_hours", "total_changeovers"]
HIGHER = ["on_time_delivery_pct", "avg_machine_utilization_pct"]
PRIMARY_KPIS = LOWER + HIGHER


def load_solver(path: str) -> Callable:
    p = Path(path).resolve()
    sys.path.insert(0, str(p))
    spec = importlib.util.spec_from_file_location(f"qc_{p.name}", p / "qcentroid.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.solver


def load_instance(name: str, treatment_dir: str) -> Dict[str, Any]:
    sys.path.insert(0, str(Path(treatment_dir).resolve()))
    from synthetic import generate_small, generate_medium  # noqa
    if name == "small":
        return generate_small()
    if name == "medium":
        return generate_medium()
    raise ValueError(f"Unknown instance: {name}")


def extract_kpis(result: Dict[str, Any]) -> Dict[str, float]:
    r = result.get("result", result)
    return {k: r.get(k) for k in PRIMARY_KPIS}


def delta_pct(treatment, baseline, lower_better):
    if treatment is None or baseline is None or baseline == 0:
        return None
    raw = (treatment - baseline) / abs(baseline) * 100.0
    return -raw if lower_better else raw


def run(treatment_path, baseline_path, instances, max_exec_time_m, seed):
    treatment_solver = load_solver(treatment_path)
    baseline_solver = load_solver(baseline_path)
    rows = []
    for inst_name in instances:
        inp = load_instance(inst_name, treatment_path)
        for label, fn in [("treatment", treatment_solver), ("baseline", baseline_solver)]:
            t0 = time.perf_counter()
            out = fn(inp, max_exec_time_m=max_exec_time_m, seed=seed)
            wall = time.perf_counter() - t0
            kpis = extract_kpis(out)
            r = out.get("result", {})
            rows.append(dict(
                instance=inst_name, side=label, kpis=kpis, wall=wall,
                status=r.get("solution_status"),
                solver_version=r.get("solver_info", {}).get("solver_version"),
                specialist_id=r.get("solver_info", {}).get("specialist_id"),
            ))
    return rows


def render_report(rows: List[Dict], outfile: Path) -> None:
    by_inst: Dict[str, Dict[str, Dict]] = {}
    for r in rows:
        by_inst.setdefault(r["instance"], {})[r["side"]] = r
    blocks: List[str] = []
    summary: List[str] = []
    for inst, sides in by_inst.items():
        t = sides.get("treatment", {})
        b = sides.get("baseline", {})
        rows_html = []
        better, worse = 0, 0
        for k in PRIMARY_KPIS:
            tv = t.get("kpis", {}).get(k)
            bv = b.get("kpis", {}).get(k)
            d = delta_pct(tv, bv, lower_better=(k in LOWER))
            color = ""
            if d is not None:
                if d > 1:
                    color = "style='background:#dcfce7'"; better += 1
                elif d < -1:
                    color = "style='background:#fee2e2'"; worse += 1
            rows_html.append(f"<tr {color}><td>{k}</td><td>{_fmt(tv)}</td><td>{_fmt(bv)}</td><td>{_fmt_pct(d)}</td></tr>")
        blocks.append(
            f"<h2>Instance: {inst}</h2>"
            f"<p>treatment <code>{t.get('status')}</code> wall {round(t.get('wall',0),2)}s, "
            f"baseline <code>{b.get('status')}</code> wall {round(b.get('wall',0),2)}s.</p>"
            f"<table><tr><th>KPI</th><th>treatment</th><th>baseline</th><th>improvement</th></tr>"
            + "".join(rows_html) + "</table>"
        )
        summary.append(f"{inst}: treatment better on {better}/{len(PRIMARY_KPIS)}, worse on {worse}.")

    html = (
        "<!doctype html><html><head><meta charset='utf-8'><title>opt-specialists A/B</title>"
        "<style>body{font-family:-apple-system,Helvetica,Arial,sans-serif;margin:24px;color:#222}"
        "table{border-collapse:collapse;margin:8px 0 24px}"
        "th,td{border:1px solid #ddd;padding:6px 12px;font-size:13px;text-align:left}"
        "h1{margin-top:0}h2{margin-top:32px}"
        "code{background:#f4f4f4;padding:1px 4px;border-radius:3px}</style></head><body>"
        "<h1>opt-specialists A/B test report</h1>"
        "<p>Hypothesis: a solver generated using the opt-specialists discipline "
        "(<code>00_classifier.md</code> + matched specialist <code>.md</code>) "
        "outperforms a solver generated without that discipline on the QCentroid "
        "<i>Dynamic Production Scheduling</i> use case (problem 743).</p>"
        "<h2>Summary</h2><ul>" + "".join(f"<li>{l}</li>" for l in summary) + "</ul>"
        + "".join(blocks) + "</body></html>"
    )
    outfile.write_text(html)


def _fmt(v):
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:.3f}"
    return str(v)


def _fmt_pct(d):
    if d is None:
        return "-"
    sign = "+" if d > 0 else ""
    return f"{sign}{d:.2f} %"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--treatment", default="..", help="dir with qcentroid.py for the opt-specialists solver")
    ap.add_argument("--baseline", default="../baseline_greedy", help="dir with qcentroid.py for the baseline")
    ap.add_argument("--instances", default="small,medium")
    ap.add_argument("--max-exec-time-m", type=float, default=2.0)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--report", default="report.html")
    args = ap.parse_args()
    rows = run(args.treatment, args.baseline, args.instances.split(","), args.max_exec_time_m, args.seed)
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    render_report(rows, Path(args.report))
    Path("rows.json").write_text(json.dumps(rows, indent=2, default=str))
    print(f"Report written to {args.report}")


if __name__ == "__main__":
    main()
