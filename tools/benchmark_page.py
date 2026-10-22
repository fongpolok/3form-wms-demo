"""
Build the client benchmark page from docs/plan/engine-benchmark.json:

    python tools/benchmark_page.py            -> docs/plan/04-engine-benchmark.html

The page is marked DRAFT unless the benchmark ran against a real cuOpt server (CUOPT_URL set when
running tools/benchmark_engines.py), so CPU stand-in numbers are never shown to clients as cuOpt.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "docs/plan/engine-benchmark.json"
OUT = ROOT / "docs/plan/04-engine-benchmark.html"

TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Planner Benchmark</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&family=Source+Serif+4:opsz,wght@8..60,600&display=swap" rel="stylesheet">
<style>
:root {
  --bg: #f4f7fc; --surface: #ffffff; --surface-2: #f8faff; --ink: #111827; --ink-2: #4b5563; --line: #e5e7eb;
  --line-strong: #c9d0db; --grid: #e5e7eb; --builtin: #eb6834; --cuopt: #0050cc; --warn-bg: #fff4e5; --warn-ink: #8a4b00;
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --bg: #0b1220; --surface: #121a2b; --surface-2: #17213a; --ink: #e8edf6; --ink-2: #aab4c5; --line: #26314a;
  --line-strong: #3a4664; --grid: #26314a; --builtin: #d95926; --cuopt: #5592ec; --warn-bg: #3a2a10; --warn-ink: #ffd27a; } }
:root[data-theme="dark"] {
  --bg: #0b1220; --surface: #121a2b; --surface-2: #17213a; --ink: #e8edf6; --ink-2: #aab4c5; --line: #26314a;
  --line-strong: #3a4664; --grid: #26314a; --builtin: #d95926; --cuopt: #5592ec; --warn-bg: #3a2a10; --warn-ink: #ffd27a; }
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink); font: 16px/1.5 Inter, system-ui, sans-serif; }
main { max-width: 1040px; margin: 0 auto; padding: 32px 16px 64px; display: grid; gap: 20px; }
h1 { font: 600 2rem/1.15 "Source Serif 4", Georgia, serif; margin: 0; }
h2 { font-size: 1.125rem; margin: 0; }
.lede { color: var(--ink-2); margin: 6px 0 0; max-width: 62ch; }
.draft { background: var(--warn-bg); color: var(--warn-ink); border-radius: 12px; padding: 12px 16px; font-weight: 600; }
.card { background: var(--surface); border: 1px solid var(--line); border-radius: 16px; padding: 20px; display: grid; gap: 12px; min-width: 0; }
.grid2 { display: grid; grid-template-columns: repeat(auto-fit, minmax(420px, 1fr)); gap: 20px; }
@media (max-width: 480px) { .grid2 { grid-template-columns: 1fr; } }
.sub { color: var(--ink-2); font-size: 0.875rem; margin: 2px 0 0; }
.legend { display: flex; gap: 18px; flex-wrap: wrap; font-size: 0.875rem; color: var(--ink-2); list-style: none; margin: 0; padding: 0; }
.legend li { display: inline-flex; align-items: center; gap: 8px; }
.sw { width: 12px; height: 12px; display: inline-block; }
.sw.b { background: var(--builtin); border-radius: 50%; } .sw.c { background: var(--cuopt); transform: rotate(45deg); width: 10px; height: 10px; border-radius: 2px; }
svg { width: 100%; height: auto; display: block; overflow: visible; }
svg text { fill: var(--ink-2); font: 12px Inter, sans-serif; font-variant-numeric: tabular-nums; }
.tip { position: fixed; pointer-events: none; background: var(--surface); color: var(--ink); border: 1px solid var(--line-strong);
       border-radius: 10px; padding: 8px 12px; font-size: 0.875rem; box-shadow: 0 6px 20px rgb(0 0 0 / .14); display: none; z-index: 9; }
table { width: 100%; border-collapse: collapse; font-size: 0.875rem; font-variant-numeric: tabular-nums; }
th, td { text-align: right; padding: 8px 10px; border-bottom: 1px solid var(--line); }
td { white-space: nowrap; }
th:first-child, td:first-child { text-align: left; }
th { color: var(--ink-2); font-weight: 600; }
.wrap { overflow-x: auto; }
.foot { color: var(--ink-2); font-size: 0.8125rem; }
.hit { fill: transparent; cursor: crosshair; }
.hit:focus { outline: none; } .hit:focus-visible { stroke: var(--ink); stroke-width: 2; }
</style>
</head>
<body>
<main>
  <header>
    <h1>Production planning: built-in vs NVIDIA cuOpt</h1>
    <p class="lede">Sample factories with 6 workstations in a line, two shifts and three products, from 5 to __MAXN__ orders.
      Both engines plan the same orders under the same calendar; the lower line is better on both charts.</p>
  </header>
  __DRAFT__
  <div class="grid2">
    <section class="card" aria-labelledby="c1">
      <div><h2 id="c1">When all work orders are finished</h2><p class="sub">Hours from the start of the plan (working calendar applied)</p></div>
      <ul class="legend"><li><span class="sw b"></span>Built-in</li><li><span class="sw c"></span>__CUOPT_NAME__</li></ul>
      <svg id="done" viewBox="0 0 460 280" role="img" aria-labelledby="c1 d1"><desc id="d1">__DESC1__</desc></svg>
    </section>
    <section class="card" aria-labelledby="c2">
      <div><h2 id="c2">Time to make the plan</h2><p class="sub">Seconds, log scale. cuOpt stops at its time limit (__LIMIT__ s)</p></div>
      <ul class="legend"><li><span class="sw b"></span>Built-in</li><li><span class="sw c"></span>__CUOPT_NAME__</li></ul>
      <svg id="speed" viewBox="0 0 460 280" role="img" aria-labelledby="c2 d2"><desc id="d2">__DESC2__</desc></svg>
    </section>
  </div>
  <section class="card" aria-labelledby="c3">
    <div><h2 id="c3">Problem size and results</h2><p class="sub">Decisions = the sequencing choices cuOpt weighs; they grow with the square of the orders per workstation</p></div>
    <div class="wrap"><table>
      <thead><tr><th>Orders</th><th>Steps</th><th>Decisions</th><th>All done, built-in</th><th>All done, __CUOPT_NAME__</th>
        <th>Changeovers, built-in</th><th>Changeovers, __CUOPT_NAME__</th><th>Hours late, built-in</th><th>Hours late, __CUOPT_NAME__</th></tr></thead>
      <tbody>__ROWS__</tbody></table></div>
  </section>
  <p class="foot">__FOOT__</p>
</main>
<div class="tip" id="tip" role="status"></div>
<script>
const DATA = __DATA__;
const H = 280, M = { l: 56, r: 16, t: 12, b: 36 };
let W = 460;
const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const NS = 'http://www.w3.org/2000/svg';
const el = (tag, attrs, parent) => { const e = document.createElementNS(NS, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); parent.appendChild(e); return e; };
const tip = document.getElementById('tip');
function niceTicks(max) { const step = [1, 2, 5, 10, 20, 25, 50, 100].map((s) => s * Math.pow(10, Math.floor(Math.log10(max)) - 1)).find((s) => max / s <= 6); const top = Math.ceil(max / step) * step; const out = []; for (let v = 0; v <= top + 1e-9; v += step) out.push(+v.toFixed(6)); return out; }
function chart(id, get, opts) {
  const svg = document.getElementById(id);
  W = Math.max(300, Math.round(svg.parentElement.clientWidth - 40));   // draw at real width: text stays 12px
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  const rows = DATA.rows;
  const xs = rows.map((r) => r.orders);
  const x = (v) => M.l + ((v - Math.min(...xs)) / (Math.max(...xs) - Math.min(...xs))) * (W - M.l - M.r);
  const vals = rows.flatMap((r) => [get(r, 'builtin'), get(r, 'cuopt')]).filter((v) => v != null);
  let y, ticks;
  if (opts.log) {
    const lo = Math.pow(10, Math.floor(Math.log10(Math.max(1e-3, Math.min(...vals))))), hi = Math.pow(10, Math.ceil(Math.log10(Math.max(...vals))));
    y = (v) => H - M.b - ((Math.log10(Math.max(v, lo)) - Math.log10(lo)) / (Math.log10(hi) - Math.log10(lo))) * (H - M.t - M.b);
    ticks = []; for (let v = lo; v <= hi * 1.0001; v *= 10) ticks.push(v);
  } else {
    ticks = niceTicks(Math.max(...vals) * 1.05);
    const hi = ticks[ticks.length - 1];
    y = (v) => H - M.b - (v / hi) * (H - M.t - M.b);
  }
  for (const t of ticks) {
    el('line', { x1: M.l, x2: W - M.r, y1: y(t), y2: y(t), stroke: css('--grid'), 'stroke-width': 1 }, svg);
    el('text', { x: M.l - 8, y: y(t) + 4, 'text-anchor': 'end' }, svg).textContent = (opts.tickFmt || opts.fmt)(t);
  }
  for (const v of xs) el('text', { x: x(v), y: H - M.b + 20, 'text-anchor': 'middle' }, svg).textContent = v;
  el('text', { x: (M.l + W - M.r) / 2, y: H - 2, 'text-anchor': 'middle' }, svg).textContent = 'orders';
  for (const [eng, color] of [['builtin', '--builtin'], ['cuopt', '--cuopt']]) {
    const pts = rows.map((r) => [x(r.orders), get(r, eng)]).filter((p) => p[1] != null).map(([px, v]) => [px, y(v)]);
    el('polyline', { points: pts.map((p) => p.join(',')).join(' '), fill: 'none', stroke: css(color), 'stroke-width': 2, 'stroke-linejoin': 'round' }, svg);
    for (const [px, py] of pts) {
      if (eng === 'builtin') el('circle', { cx: px, cy: py, r: 5, fill: css(color), stroke: css('--surface'), 'stroke-width': 2 }, svg);
      else el('rect', { x: px - 4.5, y: py - 4.5, width: 9, height: 9, rx: 1.5, fill: css(color), stroke: css('--surface'), 'stroke-width': 2, transform: `rotate(45 ${px} ${py})` }, svg);
    }
  }
  // Hover / focus: one hit column per size (bigger than the marks).
  const colW = (W - M.l - M.r) / Math.max(1, rows.length - 1);
  rows.forEach((r) => {
    const hit = el('rect', { class: 'hit', x: x(r.orders) - colW / 2, y: M.t, width: colW, height: H - M.t - M.b, tabindex: 0,
      'aria-label': `${r.orders} orders: built-in ${opts.fmt(get(r, 'builtin'))}, ${DATA.cuopt_name} ${get(r, 'cuopt') == null ? 'no plan' : opts.fmt(get(r, 'cuopt'))}` }, svg);
    const show = (ev) => {
      tip.innerHTML = `<strong>${r.orders} orders</strong> · ${r.decisions ?? '–'} decisions<br>` +
        `<span style="color:${css('--builtin')}">●</span> Built-in: ${opts.fmt(get(r, 'builtin'))}<br>` +
        `<span style="color:${css('--cuopt')}">◆</span> ${DATA.cuopt_name}: ${get(r, 'cuopt') == null ? 'no plan' : opts.fmt(get(r, 'cuopt'))}`;
      const b = (ev.target || hit).getBoundingClientRect();
      tip.style.display = 'block'; const tw = tip.offsetWidth; tip.style.left = Math.max(8, Math.min(b.left + b.width / 2 - tw / 2, innerWidth - tw - 8)) + 'px'; tip.style.top = (b.top + 8) + 'px';
    };
    hit.addEventListener('mouseenter', show); hit.addEventListener('focus', show);
    hit.addEventListener('mouseleave', () => (tip.style.display = 'none')); hit.addEventListener('blur', () => (tip.style.display = 'none'));
  });
}
const secs = (v) => v == null ? '–' : v < 0.01 ? '< 0.01 s' : v < 1 ? `${v.toFixed(2)} s` : `${v.toFixed(v < 10 ? 1 : 0)} s`;
function draw() {
  for (const id of ['done', 'speed']) document.getElementById(id).querySelectorAll(':scope > :not(desc)').forEach((n) => n.remove());
  chart('done', (r, e) => r[e]?.all_done_hours ?? null, { fmt: (v) => `${Math.round(v)} h` });
  chart('speed', (r, e) => r[e]?.seconds ?? null, { log: true, fmt: secs, tickFmt: (v) => `${+v.toPrecision(1)} s` });
}
draw();
matchMedia('(prefers-color-scheme: dark)').addEventListener('change', draw);
let rt; addEventListener('resize', () => { clearTimeout(rt); rt = setTimeout(draw, 120); });
</script>
</body>
</html>
"""


def fmt(v, unit=""):
    return "–" if v is None else f"{v:g}{unit}"


def main():
    data = json.loads(SRC.read_text())
    real = not data["solver"].startswith("pretend")
    data["cuopt_name"] = "NVIDIA cuOpt" if real else "cuOpt (CPU stand-in)"
    rows_html = []
    for r in data["rows"]:
        b, c = r["builtin"], r.get("cuopt", {})
        rows_html.append(
            f"<tr><td>{r['orders']}</td><td>{r['steps']}</td><td>{r.get('decisions', 0):,}</td>"
            f"<td>{fmt(b['all_done_hours'], ' h')}</td><td>{fmt(c.get('all_done_hours'), ' h')}</td>"
            f"<td>{b['changeovers']}</td><td>{fmt(c.get('changeovers'))}</td>"
            f"<td>{fmt(b['hours_late'], ' h')}</td><td>{fmt(c.get('hours_late'), ' h')}</td></tr>")
    first, last = data["rows"][0], data["rows"][-1]
    desc1 = (f"Line chart, orders on the x axis from {first['orders']} to {last['orders']}, hours until all work is done "
             f"on the y axis. At {last['orders']} orders: built-in {fmt(last['builtin']['all_done_hours'], ' hours')}, "
             f"{data['cuopt_name']} {fmt(last.get('cuopt', {}).get('all_done_hours'), ' hours')}.")
    desc2 = (f"Line chart on a log scale, planning time in seconds. Built-in stays below 0.01 seconds; "
             f"{data['cuopt_name']} uses up to its {data['time_limit_seconds']:g}-second limit.")
    draft = "" if real else ('<p class="draft" role="note">DRAFT, not for clients: the cuOpt numbers come from a CPU '
                             'stand-in (HiGHS), not NVIDIA cuOpt on a GPU. Re-run tools/benchmark_engines.py with '
                             'CUOPT_URL set to a real cuOpt server, then rebuild this page.</p>')
    foot = (f"Benchmark run {data['run_at']} · solver: {data['solver']} · time limit {data['time_limit_seconds']:g} s · "
            f"{data['workstations']} workstations · {data['changeover_minutes']}-minute changeovers · "
            "changeover cost 30 minutes (cuOpt), same-product grouping 1 day (built-in). Generated by tools/benchmark_page.py.")
    html = (TEMPLATE.replace("__DATA__", json.dumps(data)).replace("__ROWS__", "".join(rows_html))
            .replace("__DRAFT__", draft).replace("__CUOPT_NAME__", data["cuopt_name"])
            .replace("__MAXN__", str(last["orders"])).replace("__LIMIT__", f"{data['time_limit_seconds']:g}")
            .replace("__DESC1__", desc1).replace("__DESC2__", desc2).replace("__FOOT__", foot))
    OUT.write_text(html)
    print("written", OUT)


if __name__ == "__main__":
    main()
