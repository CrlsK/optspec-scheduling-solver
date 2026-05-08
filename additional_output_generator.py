"""
Additional Output Generator for QCentroid Solvers
Generates rich HTML visualizations and CSV exports in additional_output/ folder.
Platform picks up files from this folder and displays them in the job detail view.

All HTML is self-contained (inline CSS/SVG) — no external dependencies needed.

Identical to the file used by classical-scheduling-solver and
quantum-scheduling-solver (md5 a3665311f5c6be5dd2bdfe947f09e259) so all
three solvers produce comparable additional_output/ artifacts in the
QCentroid file viewer.
"""

import os
import json
import csv
import io
import math
from typing import Dict, List, Any


def _safe_get(obj, key, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return default


_SPECIALTY_YES = "⚡ Yes"
_EMDASH = "—"


def generate_additional_output(input_data: dict, result: dict, algorithm_name: str = "Solver"):
    os.makedirs("additional_output", exist_ok=True)
    _files = [
        ("additional_output/01_input_overview.html", _generate_input_overview_html, (input_data,)),
        ("additional_output/02_problem_structure.html", _generate_problem_structure_html, (input_data,)),
        ("additional_output/03_executive_dashboard.html", _generate_executive_dashboard_html, (result, input_data, algorithm_name)),
        ("additional_output/04_gantt_schedule.html", _generate_gantt_html, (result, input_data)),
        ("additional_output/05_machine_utilization.html", _generate_machine_utilization_html, (result, input_data)),
        ("additional_output/06_delivery_analysis.html", _generate_delivery_analysis_html, (result, input_data)),
        ("additional_output/07_financial_impact.html", _generate_financial_impact_html, (result, input_data)),
        ("additional_output/08_energy_report.html", _generate_energy_report_html, (result, input_data)),
        ("additional_output/09_schedule_assignments.csv", _generate_schedule_csv, (result,)),
        ("additional_output/10_kpi_summary.csv", _generate_kpi_csv, (result,)),
        ("additional_output/11_machine_metrics.csv", _generate_machine_csv, (result,)),
        ("additional_output/12_job_delivery.csv", _generate_delivery_csv, (result,)),
    ]
    generated = 0
    for path, func, args in _files:
        try:
            content = func(*args)
            _write_file(path, content)
            generated += 1
        except Exception:
            pass
    return generated


def _write_file(path, content):
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception:
        pass


_CSS = "<style>" + \
    "* { margin: 0; padding: 0; box-sizing: border-box; }" + \
    "body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #e2e8f0; padding: 24px; }" + \
    ".container { max-width: 1200px; margin: 0 auto; }" + \
    "h1 { font-size: 28px; font-weight: 700; color: #f8fafc; margin-bottom: 8px; }" + \
    "h2 { font-size: 20px; font-weight: 600; color: #94a3b8; margin: 24px 0 12px; }" + \
    "h3 { font-size: 16px; font-weight: 600; color: #cbd5e1; margin: 16px 0 8px; }" + \
    ".subtitle { color: #64748b; font-size: 14px; margin-bottom: 24px; }" + \
    ".grid { display: grid; gap: 16px; margin-bottom: 24px; }" + \
    ".grid-2 { grid-template-columns: 1fr 1fr; } .grid-3 { grid-template-columns: 1fr 1fr 1fr; }" + \
    ".grid-4 { grid-template-columns: 1fr 1fr 1fr 1fr; } .grid-5 { grid-template-columns: 1fr 1fr 1fr 1fr 1fr; }" + \
    ".card { background: #1e293b; border-radius: 12px; padding: 20px; border: 1px solid #334155; }" + \
    ".kpi-card { text-align: center; }" + \
    ".kpi-value { font-size: 32px; font-weight: 700; color: #f8fafc; }" + \
    ".kpi-label { font-size: 12px; color: #94a3b8; margin-top: 4px; text-transform: uppercase; letter-spacing: 0.5px; }" + \
    ".kpi-delta { font-size: 13px; margin-top: 4px; }" + \
    ".positive { color: #4ade80; } .negative { color: #f87171; } .neutral { color: #fbbf24; }" + \
    ".badge { display: inline-block; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 600; }" + \
    ".badge-green { background: #064e3b; color: #6ee7b7; } .badge-red { background: #7f1d1d; color: #fca5a5; }" + \
    ".badge-yellow { background: #713f12; color: #fde68a; } .badge-blue { background: #1e3a5f; color: #93c5fd; }" + \
    "table { width: 100%; border-collapse: collapse; font-size: 13px; }" + \
    "th { background: #334155; color: #94a3b8; text-align: left; padding: 10px 12px; font-weight: 600; }" + \
    "td { padding: 10px 12px; border-bottom: 1px solid #1e293b; }" + \
    ".bar-bg { background: #334155; border-radius: 4px; height: 20px; overflow: hidden; }" + \
    ".bar-fill { height: 100%; border-radius: 4px; transition: width 0.3s; }" + \
    "</style>"


def _html_wrapper(title, subtitle, body):
    return "<!DOCTYPE html><html><head><meta charset='UTF-8'><title>" + title + "</title>" + _CSS + "</head><body><div class='container'><h1>" + title + "</h1><div class='subtitle'>" + subtitle + "</div>" + body + "</div></body></html>"


def _kpi_card(value, label, delta=None, delta_good=True):
    delta_html = ""
    if delta is not None:
        cls = "positive" if (delta >= 0) == delta_good else "negative"
        sign = "+" if delta >= 0 else ""
        delta_html = f'<div class="kpi-delta {cls}">{sign}{delta:.1f}%</div>'
    return f'<div class="card kpi-card"><div class="kpi-value">{value}</div><div class="kpi-label">{label}</div>{delta_html}</div>'


def _badge(text, variant="blue"):
    return f'<span class="badge badge-{variant}">{text}</span>'


def _bar_chart_inline(value, max_val=100, color="#3b82f6"):
    pct = min(100, max(0, (value / max_val * 100) if max_val > 0 else 0))
    return f'<div class="bar-bg"><div class="bar-fill" style="width:{pct:.0f}%;background:{color}"></div></div>'


def _svg_donut(pct, label, size=120, color="#3b82f6"):
    r = 40
    circ = 2 * math.pi * r
    dash = circ * pct / 100
    gap = circ - dash
    return f'<svg width="{size}" height="{size}" viewBox="0 0 100 100"><circle cx="50" cy="50" r="{r}" fill="none" stroke="#334155" stroke-width="8"/><circle cx="50" cy="50" r="{r}" fill="none" stroke="{color}" stroke-width="8" stroke-dasharray="{dash:.1f} {gap:.1f}" stroke-dashoffset="{circ/4:.1f}" stroke-linecap="round"/><text x="50" y="48" text-anchor="middle" fill="#f8fafc" font-size="18" font-weight="700">{pct:.0f}%</text><text x="50" y="64" text-anchor="middle" fill="#94a3b8" font-size="8">{label}</text></svg>'


def _generate_input_overview_html(input_data):
    metadata = input_data.get("metadata", {}) if isinstance(input_data.get("metadata"), dict) else {}
    machines = input_data.get("machines", [])
    jobs = input_data.get("jobs", [])
    plant = metadata.get("plant_name", metadata.get("plant", ""))
    body = f'<div class="grid grid-4">{_kpi_card(len(jobs), "Total Jobs")}{_kpi_card(len(machines), "Machines")}{_kpi_card(input_data.get("planning_horizon_hours", 72), "Horizon (h)")}{_kpi_card(input_data.get("num_jobs", len(jobs)), "Job count")}</div>'
    return _html_wrapper("Input Overview", plant or "Dataset", body)


def _generate_problem_structure_html(input_data):
    jobs = input_data.get("jobs", [])
    machines = input_data.get("machines", [])
    rows = "".join(f"<tr><td>{j.get('job_id', j.get('id',''))}</td><td>{j.get('priority','')}</td><td>{j.get('due_date', j.get('due_hour',''))}</td></tr>" for j in jobs)
    body = f'<div class="card"><h3>Jobs ({len(jobs)})</h3><table><tr><th>ID</th><th>Priority</th><th>Due</th></tr>{rows}</table></div>'
    return _html_wrapper("Problem Structure", f"{len(jobs)} jobs x {len(machines)} machines", body)


def _generate_executive_dashboard_html(result, input_data, algorithm):
    sched = result.get("schedule", {}) if isinstance(result.get("schedule"), dict) else {}
    makespan = sched.get("makespan", result.get("makespan_hours", 0))
    otd = sched.get("on_time_percentage", result.get("on_time_delivery_pct", 0))
    util = result.get("avg_machine_utilization_pct", 0)
    body = f'<div class="grid grid-4">{_kpi_card(f"{makespan:.1f}h", "Makespan")}{_kpi_card(f"{otd:.1f}%", "On-Time")}{_kpi_card(f"{util:.1f}%", "Utilization")}{_kpi_card(f"{result.get(\"objective_value\",0):.2f}", "Objective")}</div><div class="grid grid-3"><div class="card" style="text-align:center">{_svg_donut(otd, "On-Time")}</div><div class="card" style="text-align:center">{_svg_donut(util, "Utilization")}</div><div class="card" style="text-align:center">{_svg_donut(min(100,(1-result.get(\"total_tardiness_hours\",0)/max(makespan,1))*100), "Schedule Health")}</div></div>'
    return _html_wrapper(f"Executive Dashboard — {algorithm}", f"status: {result.get('solution_status','')}", body)


def _generate_gantt_html(result, input_data):
    sched = result.get("schedule", {}) if isinstance(result.get("schedule"), dict) else {}
    gantt = sched.get("gantt_data", []) or result.get("gantt_data", [])
    machines = input_data.get("machines", [])
    machine_ids = sorted(set(g.get("resource_id", g.get("machine_id","")) for g in gantt))
    if not machine_ids:
        return _html_wrapper("Gantt", "No data", "<p>No assignments.</p>")
    makespan = sched.get("makespan", result.get("makespan_hours", 1)) or 1
    chart_w, row_h, left = 900, 32, 100
    chart_h = len(machine_ids) * row_h + 60
    bars = []
    colors = ["#3b82f6","#8b5cf6","#ec4899","#f97316","#14b8a6","#eab308","#6366f1","#ef4444","#22c55e","#06b6d4"]
    job_ids = sorted(set(g.get("job_id","") for g in gantt))
    job_color = {j: colors[i%len(colors)] for i,j in enumerate(job_ids)}
    for g in gantt:
        mid = g.get("resource_id", g.get("machine_id",""))
        if mid not in machine_ids: continue
        s = g.get("start_hour", g.get("start_time", g.get("start", 0)))
        e = g.get("end_hour", g.get("end_time", g.get("end", 0)))
        x = left + (s/makespan)*(chart_w-left)
        w = max(2, ((e-s)/makespan)*(chart_w-left))
        y = 30 + machine_ids.index(mid)*row_h + 2
        bars.append(f'<rect x="{x:.1f}" y="{y}" width="{w:.1f}" height="{row_h-4}" rx="3" fill="{job_color.get(g.get(\"job_id\",\"\"), \"#475569\")}" opacity="0.85"><title>{g.get("job_id","")} {s:.1f}h-{e:.1f}h</title></rect>')
    y_labels = [f'<text x="{left-8}" y="{30+i*row_h+row_h/2+4}" text-anchor="end" fill="#94a3b8" font-size="11">{mid}</text>' for i, mid in enumerate(machine_ids)]
    body = f'<div class="card" style="overflow-x:auto"><svg width="{chart_w}" height="{chart_h}">{"".join(y_labels)}{"".join(bars)}</svg></div>'
    return _html_wrapper("Gantt Schedule", f"{len(gantt)} ops, makespan {makespan:.1f}h", body)


def _get_util(d):
    if isinstance(d, dict): return d.get("utilization_percentage", 0)
    if isinstance(d, (int, float)): return d
    return 0


def _generate_machine_utilization_html(result, input_data):
    mu = result.get("machine_utilization", {})
    if not isinstance(mu, dict) or not mu:
        return _html_wrapper("Machine Utilization", "Aggregate only", f'<div class="card"><h3>Avg utilization</h3><p style="font-size:24px">{result.get("avg_machine_utilization_pct",0):.1f}%</p></div>')
    rows = "".join(f"<tr><td>{mid}</td><td>{_bar_chart_inline(_get_util(d))} {_get_util(d):.1f}%</td></tr>" for mid, d in sorted(mu.items(), key=lambda x: _get_util(x[1]), reverse=True))
    body = f'<div class="card"><table><tr><th>Machine</th><th>Utilization</th></tr>{rows}</table></div>'
    return _html_wrapper("Machine Utilization", f"{len(mu)} machines", body)


def _generate_delivery_analysis_html(result, input_data):
    jm = result.get("job_metrics", {})
    if not isinstance(jm, dict) or not jm:
        return _html_wrapper("Delivery Analysis", "Summary", f'<div class="card"><p>On-time: {result.get("on_time_delivery_pct",0):.1f}%</p><p>Total tardiness: {result.get("total_tardiness_hours",0):.2f}h</p></div>')
    rows = []
    for jid, d in sorted(jm.items()):
        on = d.get("on_time", False)
        rows.append(f"<tr><td>{jid}</td><td>{d.get('completion_time',0):.1f}h</td><td>{d.get('due_date',0):.1f}h</td><td>{d.get('tardiness',0):.1f}h</td><td>{_badge('ON TIME','green') if on else _badge('LATE','red')}</td></tr>")
    body = f'<div class="card"><table><tr><th>Job</th><th>Completed</th><th>Due</th><th>Tardiness</th><th>Status</th></tr>{"".join(rows)}</table></div>'
    return _html_wrapper("Delivery Analysis", f"{len(jm)} jobs", body)


def _generate_financial_impact_html(result, input_data):
    obj = result.get("objective_value", 0)
    bench = result.get("benchmark", {})
    cost = bench.get("execution_cost", {}).get("value", 0) if isinstance(bench.get("execution_cost"), dict) else bench.get("execution_cost", 0)
    body = f'<div class="grid grid-3">{_kpi_card(f"{obj:.2f}", "Objective Value")}{_kpi_card(f"{cost:.4f} cr", "Execution Cost")}{_kpi_card(f"{result.get(\"total_changeovers\",0)}", "Changeovers")}</div>'
    return _html_wrapper("Financial Impact", "Composite cost view", body)


def _generate_energy_report_html(result, input_data):
    e = result.get("total_energy_kwh", result.get("benchmark",{}).get("energy_consumption", 0))
    body = f'<div class="card"><h3>Energy Summary</h3><p style="font-size:24px;color:#fbbf24">{e:.1f} kWh</p></div>'
    return _html_wrapper("Energy Report", "Production line energy", body)


def _generate_schedule_csv(result):
    sched = result.get("schedule", {})
    assignments = sched.get("assignments", []) if isinstance(sched, dict) else []
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["job_id", "machine_id", "start", "end"])
    for a in assignments:
        w.writerow([a.get("job_id",""), a.get("machine_id",""), a.get("start", a.get("start_time",0)), a.get("end", a.get("end_time",0))])
    return buf.getvalue()


def _generate_kpi_csv(result):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["kpi", "value"])
    for k in ["objective_value","makespan_hours","total_tardiness_hours","on_time_delivery_pct","avg_machine_utilization_pct","total_changeovers"]:
        w.writerow([k, result.get(k, 0)])
    return buf.getvalue()


def _generate_machine_csv(result):
    mu = result.get("machine_utilization", {})
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["machine_id", "utilization_pct"])
    if isinstance(mu, dict):
        for mid, d in sorted(mu.items()):
            w.writerow([mid, _get_util(d)])
    return buf.getvalue()


def _generate_delivery_csv(result):
    jm = result.get("job_metrics", {})
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["job_id", "completion_time", "due_date", "tardiness", "on_time"])
    if isinstance(jm, dict):
        for jid, d in sorted(jm.items()):
            w.writerow([jid, d.get("completion_time",0), d.get("due_date",0), d.get("tardiness",0), d.get("on_time",False)])
    return buf.getvalue()
