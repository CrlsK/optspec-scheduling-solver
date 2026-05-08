"""
outputs.py — Writers for ./additional_output/ files (Gantt HTML, schedule
JSON, audit JSON, specialist report HTML). Per the QCentroid file-viewer
contract, only .html and .json files render inline.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

_CSS = """
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;margin:24px;color:#222}
h1{font-size:20px;margin-top:0}
table{border-collapse:collapse;width:100%}
th,td{border:1px solid #ddd;padding:6px 10px;font-size:13px;text-align:left}
th{background:#fafafa}
.kpi{display:inline-block;padding:6px 14px;background:#f5f5f5;border-radius:6px;margin-right:8px;font-size:13px}
.kpi b{color:#0a4}
.gantt{position:relative;border:1px solid #ccc;background:#fafafa}
.row{position:absolute;height:22px;background:#3b82f6;color:#fff;font-size:11px;line-height:22px;padding-left:4px;border-radius:3px;overflow:hidden}
.label{position:absolute;font-size:12px;color:#444;left:4px}
.axis{position:absolute;border-top:1px solid #ddd;font-size:10px;color:#888}
"""


def write_additional_outputs(out_dir: Path, schedule: List[Dict[str, Any]],
                             jobs: List[Dict[str, Any]], machines: List[Dict[str, Any]],
                             horizon: int, kpis: Dict[str, Any], meta: Dict[str, Any]) -> None:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "schedule.json").write_text(json.dumps(schedule, indent=2))
    (out_dir / "audit.json").write_text(json.dumps({"kpis": kpis, "meta": meta}, indent=2, default=str))
    (out_dir / "gantt.html").write_text(_gantt_html(schedule, machines, horizon, kpis, meta))
    (out_dir / "specialist_report.html").write_text(_report_html(schedule, jobs, machines, kpis, meta))


def _gantt_html(schedule, machines, horizon, kpis, meta):
    px_per_slot = max(2, min(20, int(1200 / max(1, horizon))))
    row_h, margin_left = 30, 120
    height = len(machines) * row_h + 30
    width = margin_left + horizon * px_per_slot + 40
    machine_idx = {m["id"]: i for i, m in enumerate(machines)}

    rows_html = [f'<div class="label" style="top:{machine_idx[m["id"]] * row_h + 4}px">{m["id"]}</div>' for m in machines]
    bars = []
    for s in schedule:
        i = machine_idx.get(s["machine_id"])
        if i is None:
            continue
        left = margin_left + s["start"] * px_per_slot
        w = max(2, (s["end"] - s["start"]) * px_per_slot)
        bars.append(
            f'<div class="row" title="job {s["job_id"]} op {s.get("op_id",0)}" '
            f'style="left:{left}px;top:{i*row_h+4}px;width:{w}px">{s["job_id"]}</div>'
        )

    axis_ticks = []
    step = max(1, horizon // 24)
    for t in range(0, horizon + 1, step):
        x = margin_left + t * px_per_slot
        axis_ticks.append(f'<div class="axis" style="left:{x}px;top:0;width:0;height:{height-20}px"></div>')
        axis_ticks.append(f'<div class="axis" style="left:{x-6}px;top:{height-18}px">{t}</div>')

    kpi_chips = "".join([
        f'<span class="kpi">makespan_hours <b>{kpis["makespan_hours"]}</b></span>',
        f'<span class="kpi">objective <b>{round(kpis["objective_value"] or 0, 2)}</b></span>',
        f'<span class="kpi">on-time % <b>{kpis["on_time_delivery_pct"]}</b></span>',
        f'<span class="kpi">tardiness h <b>{round(kpis["total_tardiness_hours"], 2)}</b></span>',
        f'<span class="kpi">utilization % <b>{kpis["avg_machine_utilization_pct"]}</b></span>',
        f'<span class="kpi">changeovers <b>{kpis["total_changeovers"]}</b></span>',
    ])

    return f"""<!doctype html><html><head><meta charset='utf-8'>
<title>Gantt</title><style>{_CSS}</style></head><body>
<h1>Schedule (opt-specialists MIP)</h1>
<div>{kpi_chips}</div>
<p style="color:#666;font-size:12px">specialist <b>{meta.get('specialist_id')}</b>
&nbsp;solver <b>{meta.get('solver_name')}</b>
&nbsp;gap <b>{round(float(meta.get('mip_gap_achieved') or 0)*100,3)} %</b>
&nbsp;wall <b>{round(meta.get('wall_seconds',0),2)} s</b></p>
<div class="gantt" style="width:{width}px;height:{height}px">{''.join(rows_html + axis_ticks + bars)}</div>
<p style="color:#888;font-size:11px">specialist source: {meta.get('specialist_source')}<br>
dataset_sha256: {meta.get('dataset_sha256')}</p></body></html>"""


def _report_html(schedule, jobs, machines, kpis, meta):
    rows = "".join(
        f"<tr><td>{s['machine_id']}</td><td>{s['job_id']}</td>"
        f"<td>{s.get('op_id',0)}</td><td>{s['start']}</td><td>{s['end']}</td>"
        f"<td>{s['p']}</td></tr>" for s in schedule
    )
    job_rows = "".join(
        f"<tr><td>{j['id']}</td><td>{j['release']}</td><td>{j['due_date']}</td>"
        f"<td>{j['weight']}</td><td>{len(j['ops'])}</td></tr>" for j in jobs
    )
    return f"""<!doctype html><html><head><meta charset='utf-8'>
<title>Specialist report</title><style>{_CSS}</style></head><body>
<h1>Specialist report - opt-specialists {meta.get('specialist_id')}</h1>
<p>Solver version <b>{meta.get('solver_version')}</b>
&nbsp;underlying <b>{meta.get('solver_name')}</b>
&nbsp;extended: <b>{meta.get('extended')}</b></p>
<h2>Top KPIs</h2>
<table><tr><th>KPI</th><th>Value</th><th>Direction</th></tr>
<tr><td>objective_value</td><td>{round(kpis['objective_value'] or 0, 4)}</td><td>lower-better</td></tr>
<tr><td>makespan_hours</td><td>{kpis['makespan_hours']}</td><td>lower-better</td></tr>
<tr><td>total_tardiness_hours</td><td>{round(kpis['total_tardiness_hours'],4)}</td><td>lower-better</td></tr>
<tr><td>on_time_delivery_pct</td><td>{kpis['on_time_delivery_pct']}</td><td>higher-better</td></tr>
<tr><td>avg_machine_utilization_pct</td><td>{kpis['avg_machine_utilization_pct']}</td><td>higher-better</td></tr>
<tr><td>total_changeovers</td><td>{kpis['total_changeovers']}</td><td>lower-better</td></tr>
</table>
<h2>Jobs ({len(jobs)})</h2>
<table><tr><th>id</th><th>release</th><th>due</th><th>weight</th><th>n_ops</th></tr>{job_rows}</table>
<h2>Schedule ({len(schedule)})</h2>
<table><tr><th>machine</th><th>job</th><th>op</th><th>start</th><th>end</th><th>p</th></tr>{rows}</table>
<p style="color:#888;font-size:12px;margin-top:32px">
specialist source: {meta.get('specialist_source')}<br>
dataset_sha256: <code>{meta.get('dataset_sha256')}</code></p></body></html>"""
