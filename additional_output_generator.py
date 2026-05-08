"""
Additional Output Generator for QCentroid Solvers (opt-specialists slim).
Round 1 fix: precompute values before f-strings to avoid backslash-in-fstring (Python 3.11).
"""

import os
import csv
import io
import math


def _safe_get(obj, key, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return default


_SPECIALTY_YES = "⚡ Yes"
_EMDASH = "—"


def generate_additional_output(input_data, result, algorithm_name="Solver"):
    os.makedirs("additional_output", exist_ok=True)
    files = [
        ("additional_output/01_input_overview.html", _input_overview, (input_data,)),
        ("additional_output/02_problem_structure.html", _problem_structure, (input_data,)),
        ("additional_output/03_executive_dashboard.html", _executive_dashboard, (result, input_data, algorithm_name)),
        ("additional_output/04_gantt_schedule.html", _gantt, (result, input_data)),
        ("additional_output/05_machine_utilization.html", _machine_util, (result, input_data)),
        ("additional_output/06_delivery_analysis.html", _delivery, (result, input_data)),
        ("additional_output/07_financial_impact.html", _financial, (result, input_data)),
        ("additional_output/08_energy_report.html", _energy, (result, input_data)),
        ("additional_output/09_schedule_assignments.csv", _csv_schedule, (result,)),
        ("additional_output/10_kpi_summary.csv", _csv_kpi, (result,)),
        ("additional_output/11_machine_metrics.csv", _csv_machine, (result,)),
        ("additional_output/12_job_delivery.csv", _csv_delivery, (result,)),
    ]
    n = 0
    for path, func, args in files:
        try:
            content = func(*args)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            n += 1
        except Exception:
            pass
    return n


_CSS = """<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
       background: #0f172a; color: #e2e8f0; padding: 24px; }
.container { max-width: 1200px; margin: 0 auto; }
h1 { font-size: 28px; font-weight: 700; color: #f8fafc; margin-bottom: 8px; }
h3 { font-size: 16px; font-weight: 600; color: #cbd5e1; margin: 16px 0 8px; }
.subtitle { color: #64748b; font-size: 14px; margin-bottom: 24px; }
.grid { display: grid; gap: 16px; margin-bottom: 24px; }
.grid-3 { grid-template-columns: 1fr 1fr 1fr; }
.grid-4 { grid-template-columns: 1fr 1fr 1fr 1fr; }
.card { background: #1e293b; border-radius: 12px; padding: 20px; border: 1px solid #334155; }
.kpi-card { text-align: center; }
.kpi-value { font-size: 32px; font-weight: 700; color: #f8fafc; }
.kpi-label { font-size: 12px; color: #94a3b8; margin-top: 4px; text-transform: uppercase; letter-spacing: 0.5px; }
.badge { display: inline-block; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 600; }
.badge-green { background: #064e3b; color: #6ee7b7; }
.badge-red { background: #7f1d1d; color: #fca5a5; }
.badge-blue { background: #1e3a5f; color: #93c5fd; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th { background: #334155; color: #94a3b8; text-align: left; padding: 10px 12px; font-weight: 600; }
td { padding: 10px 12px; border-bottom: 1px solid #1e293b; }
.bar-bg { background: #334155; border-radius: 4px; height: 20px; overflow: hidden; }
.bar-fill { height: 100%; border-radius: 4px; }
</style>"""


def _wrap(title, subtitle, body):
    return ("<!DOCTYPE html><html><head><meta charset='UTF-8'><title>" + title + "</title>"
            + _CSS + "</head><body><div class='container'><h1>" + title + "</h1>"
            + "<div class='subtitle'>" + subtitle + "</div>" + body + "</div></body></html>")


def _kpi(value, label):
    return ('<div class="card kpi-card"><div class="kpi-value">' + str(value)
            + '</div><div class="kpi-label">' + str(label) + '</div></div>')


def _badge(text, variant="blue"):
    return '<span class="badge badge-' + variant + '">' + str(text) + '</span>'


def _bar(value, color="#3b82f6"):
    pct = min(100, max(0, value))
    return ('<div class="bar-bg"><div class="bar-fill" style="width:' + str(round(pct))
            + '%;background:' + color + '"></div></div>')


def _donut(pct, label, size=120, color="#3b82f6"):
    r = 40
    circ = 2 * math.pi * r
    dash = circ * pct / 100
    gap = circ - dash
    return ('<svg width="' + str(size) + '" height="' + str(size) + '" viewBox="0 0 100 100">'
            + '<circle cx="50" cy="50" r="' + str(r) + '" fill="none" stroke="#334155" stroke-width="8"/>'
            + '<circle cx="50" cy="50" r="' + str(r) + '" fill="none" stroke="' + color
            + '" stroke-width="8" stroke-dasharray="' + format(dash, '.1f') + ' ' + format(gap, '.1f')
            + '" stroke-dashoffset="' + format(circ/4, '.1f') + '" stroke-linecap="round"/>'
            + '<text x="50" y="48" text-anchor="middle" fill="#f8fafc" font-size="18" font-weight="700">'
            + str(round(pct)) + '%</text>'
            + '<text x="50" y="64" text-anchor="middle" fill="#94a3b8" font-size="8">' + label + '</text>'
            + '</svg>')


def _input_overview(input_data):
    metadata = input_data.get("metadata", {}) if isinstance(input_data.get("metadata"), dict) else {}
    machines = input_data.get("machines", [])
    jobs = input_data.get("jobs", [])
    plant = metadata.get("plant_name", metadata.get("plant", ""))
    horizon_h = input_data.get("planning_horizon_hours", 72)
    body = ('<div class="grid grid-4">'
            + _kpi(len(jobs), "Total Jobs")
            + _kpi(len(machines), "Machines")
            + _kpi(str(horizon_h) + "h", "Horizon")
            + _kpi(input_data.get("num_jobs", len(jobs)), "Job count")
            + '</div>')
    return _wrap("Input Overview", plant or "Dataset", body)


def _problem_structure(input_data):
    jobs = input_data.get("jobs", [])
    machines = input_data.get("machines", [])
    rows = []
    for j in jobs:
        jid = j.get("job_id", j.get("id", ""))
        prio = j.get("priority", "")
        due = j.get("due_date", j.get("due_hour", ""))
        rows.append("<tr><td>" + str(jid) + "</td><td>" + str(prio) + "</td><td>" + str(due) + "</td></tr>")
    body = ('<div class="card"><h3>Jobs (' + str(len(jobs)) + ')</h3>'
            + '<table><tr><th>ID</th><th>Priority</th><th>Due</th></tr>'
            + "".join(rows) + '</table></div>')
    return _wrap("Problem Structure", str(len(jobs)) + " jobs x " + str(len(machines)) + " machines", body)


def _executive_dashboard(result, input_data, algorithm):
    sched = result.get("schedule", {}) if isinstance(result.get("schedule"), dict) else {}
    makespan = sched.get("makespan", result.get("makespan_hours", 0)) or 0
    otd = sched.get("on_time_percentage", result.get("on_time_delivery_pct", 0)) or 0
    util = result.get("avg_machine_utilization_pct", 0) or 0
    obj = result.get("objective_value", 0) or 0
    tard = result.get("total_tardiness_hours", 0) or 0
    health = max(0, min(100, (1 - tard / max(makespan, 1)) * 100))
    status = result.get("solution_status", "")
    body = ('<div class="grid grid-4">'
            + _kpi(format(makespan, '.1f') + "h", "Makespan")
            + _kpi(format(otd, '.1f') + "%", "On-Time")
            + _kpi(format(util, '.1f') + "%", "Utilization")
            + _kpi(format(obj, '.2f'), "Objective")
            + '</div>'
            + '<div class="grid grid-3">'
            + '<div class="card" style="text-align:center">' + _donut(otd, "On-Time") + '</div>'
            + '<div class="card" style="text-align:center">' + _donut(util, "Utilization") + '</div>'
            + '<div class="card" style="text-align:center">' + _donut(health, "Schedule Health") + '</div>'
            + '</div>')
    return _wrap("Executive Dashboard - " + str(algorithm), "status: " + str(status), body)


def _gantt(result, input_data):
    sched = result.get("schedule", {}) if isinstance(result.get("schedule"), dict) else {}
    g = sched.get("gantt_data", []) or result.get("gantt_data", [])
    if not g:
        return _wrap("Gantt", "No data", "<p>No assignments.</p>")
    machine_ids = sorted(set(item.get("resource_id", item.get("machine_id", "")) for item in g))
    makespan = sched.get("makespan", result.get("makespan_hours", 1)) or 1
    chart_w, row_h, left = 900, 32, 100
    chart_h = len(machine_ids) * row_h + 60
    colors = ["#3b82f6", "#8b5cf6", "#ec4899", "#f97316", "#14b8a6", "#eab308",
              "#6366f1", "#ef4444", "#22c55e", "#06b6d4"]
    job_ids = sorted(set(item.get("job_id", "") for item in g))
    job_color = {jid: colors[i % len(colors)] for i, jid in enumerate(job_ids)}
    bars = []
    for item in g:
        mid = item.get("resource_id", item.get("machine_id", ""))
        if mid not in machine_ids:
            continue
        s = item.get("start_hour", item.get("start_time", item.get("start", 0)))
        e = item.get("end_hour", item.get("end_time", item.get("end", 0)))
        x = left + (s / makespan) * (chart_w - left)
        w = max(2, ((e - s) / makespan) * (chart_w - left))
        y = 30 + machine_ids.index(mid) * row_h + 2
        c = job_color.get(item.get("job_id", ""), "#475569")
        bars.append('<rect x="' + format(x, '.1f') + '" y="' + str(y) + '" width="' + format(w, '.1f')
                    + '" height="' + str(row_h - 4) + '" rx="3" fill="' + c + '" opacity="0.85"/>')
    y_labels = []
    for i, mid in enumerate(machine_ids):
        y = 30 + i * row_h + row_h / 2 + 4
        y_labels.append('<text x="' + str(left - 8) + '" y="' + format(y, '.0f')
                        + '" text-anchor="end" fill="#94a3b8" font-size="11">' + str(mid) + '</text>')
    body = ('<div class="card" style="overflow-x:auto"><svg width="' + str(chart_w)
            + '" height="' + str(chart_h) + '">' + "".join(y_labels) + "".join(bars)
            + '</svg></div>')
    return _wrap("Gantt Schedule", str(len(g)) + " ops, makespan " + format(makespan, '.1f') + "h", body)


def _get_util(d):
    if isinstance(d, dict):
        return d.get("utilization_percentage", 0)
    if isinstance(d, (int, float)):
        return d
    return 0


def _machine_util(result, input_data):
    mu = result.get("machine_utilization", {})
    if not isinstance(mu, dict) or not mu:
        avg = result.get("avg_machine_utilization_pct", 0)
        body = ('<div class="card"><h3>Avg utilization</h3><p style="font-size:24px">'
                + format(avg, '.1f') + '%</p></div>')
        return _wrap("Machine Utilization", "Aggregate only", body)
    rows = []
    for mid, d in sorted(mu.items(), key=lambda x: _get_util(x[1]), reverse=True):
        u = _get_util(d)
        rows.append("<tr><td>" + str(mid) + "</td><td>" + _bar(u) + " " + format(u, '.1f') + "%</td></tr>")
    body = ('<div class="card"><table><tr><th>Machine</th><th>Utilization</th></tr>'
            + "".join(rows) + '</table></div>')
    return _wrap("Machine Utilization", str(len(mu)) + " machines", body)


def _delivery(result, input_data):
    jm = result.get("job_metrics", {})
    if not isinstance(jm, dict) or not jm:
        otd = result.get("on_time_delivery_pct", 0)
        tard = result.get("total_tardiness_hours", 0)
        body = ('<div class="card"><p>On-time: ' + format(otd, '.1f') + '%</p>'
                + '<p>Total tardiness: ' + format(tard, '.2f') + 'h</p></div>')
        return _wrap("Delivery Analysis", "Summary", body)
    rows = []
    for jid, d in sorted(jm.items()):
        comp = d.get("completion_time", 0) or 0
        due = d.get("due_date", 0) or 0
        tard = d.get("tardiness", 0) or 0
        on = d.get("on_time", False)
        status = _badge("ON TIME", "green") if on else _badge("LATE", "red")
        rows.append("<tr><td>" + str(jid) + "</td><td>" + format(comp, '.1f') + "h</td><td>"
                    + format(due, '.1f') + "h</td><td>" + format(tard, '.1f') + "h</td><td>"
                    + status + "</td></tr>")
    body = ('<div class="card"><table><tr><th>Job</th><th>Completed</th><th>Due</th>'
            + '<th>Tardiness</th><th>Status</th></tr>' + "".join(rows) + '</table></div>')
    return _wrap("Delivery Analysis", str(len(jm)) + " jobs", body)


def _financial(result, input_data):
    obj = result.get("objective_value", 0) or 0
    bench = result.get("benchmark", {})
    cost_obj = bench.get("execution_cost", {})
    cost = cost_obj.get("value", 0) if isinstance(cost_obj, dict) else (cost_obj or 0)
    chg = result.get("total_changeovers", 0) or 0
    body = ('<div class="grid grid-3">'
            + _kpi(format(obj, '.2f'), "Objective Value")
            + _kpi(format(cost, '.4f') + " cr", "Execution Cost")
            + _kpi(str(chg), "Changeovers")
            + '</div>')
    return _wrap("Financial Impact", "Composite cost view", body)


def _energy(result, input_data):
    e = result.get("total_energy_kwh", 0)
    if not e:
        bench = result.get("benchmark", {})
        e = bench.get("energy_consumption", 0) if isinstance(bench, dict) else 0
    body = ('<div class="card"><h3>Energy Summary</h3>'
            + '<p style="font-size:24px;color:#fbbf24">' + format(e or 0, '.1f') + ' kWh</p></div>')
    return _wrap("Energy Report", "Production line energy", body)


def _csv_schedule(result):
    sched = result.get("schedule", {})
    assignments = sched.get("assignments", []) if isinstance(sched, dict) else []
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["job_id", "machine_id", "start", "end"])
    for a in assignments:
        w.writerow([a.get("job_id", ""), a.get("machine_id", ""),
                    a.get("start", a.get("start_time", 0)),
                    a.get("end", a.get("end_time", 0))])
    return buf.getvalue()


def _csv_kpi(result):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["kpi", "value"])
    for k in ["objective_value", "makespan_hours", "total_tardiness_hours",
              "on_time_delivery_pct", "avg_machine_utilization_pct", "total_changeovers"]:
        w.writerow([k, result.get(k, 0)])
    return buf.getvalue()


def _csv_machine(result):
    mu = result.get("machine_utilization", {})
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["machine_id", "utilization_pct"])
    if isinstance(mu, dict):
        for mid, d in sorted(mu.items()):
            w.writerow([mid, _get_util(d)])
    return buf.getvalue()


def _csv_delivery(result):
    jm = result.get("job_metrics", {})
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["job_id", "completion_time", "due_date", "tardiness", "on_time"])
    if isinstance(jm, dict):
        for jid, d in sorted(jm.items()):
            w.writerow([jid, d.get("completion_time", 0), d.get("due_date", 0),
                        d.get("tardiness", 0), d.get("on_time", False)])
    return buf.getvalue()
