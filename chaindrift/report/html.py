"""Self-contained HTML report: summary tiles, a findings x chains divergence matrix, and detail cards."""

from __future__ import annotations

import datetime as _dt
import json
from html import escape

from .. import __version__
from ..knowledge import load_knowledge
from .common import grouped_assessments

_LABEL = {"high": "HIGH", "medium": "MED", "check": "CHECK", "low": "LOW", "info": "INFO", "none": "✓"}
_LONG = {
    "high": "High", "medium": "Medium", "check": "Verify", "low": "Low", "info": "Info",
    "none": "Same as Ethereum",
}

_CSS = """
:root{
  --page:#0d0d0d; --surface:#1a1a19; --surface-2:#222220; --ink:#f0efec; --ink-2:#c3c2b7; --muted:#898781;
  --grid:#2c2c2a; --axis:#383835; --ring:rgba(255,255,255,0.10);
  --critical:#d03b3b; --serious:#ec835a; --warning:#fab219; --good:#0ca30c; --neutral:#898781;
  --code:#141413;
}
@media (prefers-color-scheme: light){
  :root{
    --page:#f9f9f7; --surface:#fcfcfb; --surface-2:#f3f2ee; --ink:#0b0b0b; --ink-2:#52514e; --muted:#898781;
    --grid:#e1e0d9; --axis:#c3c2b7; --ring:rgba(11,11,11,0.10); --code:#f3f2ee;
  }
}
*{box-sizing:border-box}
body{margin:0;background:var(--page);color:var(--ink);font:14px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
a{color:inherit}
header.top{display:flex;justify-content:space-between;align-items:flex-end;gap:24px;flex-wrap:wrap;
  padding:28px 40px 20px;border-bottom:1px solid var(--grid)}
.brand{font-size:22px;font-weight:700;letter-spacing:-0.01em}
.brand .tag{font-size:13px;font-weight:400;color:var(--ink-2);margin-left:10px}
.meta{color:var(--ink-2);font-size:13px;text-align:right}
.meta code{color:var(--ink)}
main{padding:24px 40px 64px;max-width:1500px;margin:0 auto}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin-bottom:20px}
.tile{background:var(--surface);border:1px solid var(--ring);border-radius:10px;padding:14px 16px}
.tile .k{color:var(--ink-2);font-size:12px;display:flex;align-items:center;gap:6px}
.tile .v{font-size:30px;font-weight:650;margin-top:2px}
.tile .s{color:var(--muted);font-size:12px}
.card{background:var(--surface);border:1px solid var(--ring);border-radius:12px;padding:20px 22px;margin-bottom:20px}
.card h2{margin:0 0 2px;font-size:16px}
.card .sub{margin:0 0 14px;color:var(--ink-2);font-size:13px}
.filters{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:12px}
.chip{border:1px solid var(--axis);background:transparent;color:var(--ink);border-radius:999px;padding:4px 12px;
  font:inherit;font-size:12px;cursor:pointer;display:inline-flex;align-items:center;gap:6px}
.chip[aria-pressed="false"]{opacity:.45}
.chip:hover{background:var(--surface-2)}
input.search{margin-left:auto;background:var(--surface-2);color:var(--ink);border:1px solid var(--axis);
  border-radius:8px;padding:6px 10px;font:inherit;font-size:13px;min-width:240px}
.dot{width:8px;height:8px;border-radius:50%;display:inline-block;flex:none}
.d-high{background:var(--critical)} .d-medium{background:var(--serious)} .d-check{background:var(--warning)}
.d-low{background:var(--neutral)} .d-info{background:var(--neutral)} .d-none{background:var(--good)}
.matrix-wrap{overflow-x:auto;border:1px solid var(--grid);border-radius:8px}
table.matrix{border-collapse:separate;border-spacing:2px;width:100%;font-size:12.5px}
.matrix th{position:sticky;top:0;background:var(--surface);color:var(--ink-2);font-weight:600;text-align:center;
  padding:8px 6px;white-space:nowrap;border-bottom:1px solid var(--axis)}
.matrix th.left{text-align:left}
.matrix th.ref{color:var(--ink)}
.matrix td{padding:6px 8px;vertical-align:middle}
.matrix td.what a{text-decoration:none;font-weight:600}
.matrix td.what a:hover{text-decoration:underline}
.matrix td.what .d{color:var(--muted);font-size:12px;max-width:380px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.matrix td.loc{color:var(--ink-2);font-family:ui-monospace,Consolas,monospace;font-size:12px;white-space:nowrap}
.matrix tbody tr:hover td{background:var(--surface-2)}
td.cell{text-align:center;border-radius:4px;white-space:nowrap;font-weight:600;font-size:11px;letter-spacing:.02em;cursor:default;min-width:72px}
td.cell .in{display:inline-flex;align-items:center;gap:5px}
td.c-high{background:color-mix(in srgb,var(--critical) 22%,transparent)}
td.c-medium{background:color-mix(in srgb,var(--serious) 20%,transparent)}
td.c-check{background:color-mix(in srgb,var(--warning) 16%,transparent)}
td.c-low,td.c-info{background:color-mix(in srgb,var(--neutral) 12%,transparent);color:var(--ink-2)}
td.c-none{color:var(--muted);font-weight:400}
.legend{display:flex;gap:16px;flex-wrap:wrap;margin-top:12px;color:var(--ink-2);font-size:12px}
.legend span{display:inline-flex;align-items:center;gap:6px}
table.chains{border-collapse:collapse;width:100%;font-size:13px}
table.chains th,table.chains td{padding:7px 10px;border-bottom:1px solid var(--grid);text-align:left}
table.chains th{color:var(--ink-2);font-weight:600}
table.chains td.n{font-variant-numeric:tabular-nums;text-align:right;width:90px}
table.chains th.n{text-align:right}
.finding{background:var(--surface);border:1px solid var(--ring);border-radius:12px;padding:18px 22px;margin-bottom:14px;scroll-margin-top:16px}
.finding:target{outline:2px solid var(--warning)}
.fh{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.badge{font-size:11px;font-weight:700;letter-spacing:.04em;padding:2px 8px;border-radius:999px;display:inline-flex;gap:6px;align-items:center;
  border:1px solid var(--axis)}
.fh h3{margin:0;font-size:15px}
.rule{color:var(--muted);font-family:ui-monospace,Consolas,monospace;font-size:12px}
.where{color:var(--ink-2);font-size:13px;margin-top:4px}
pre.snip{background:var(--code);border:1px solid var(--grid);border-radius:8px;padding:10px 12px;margin:10px 0;
  font:12.5px/1.5 ui-monospace,Consolas,monospace;overflow-x:auto;white-space:pre}
.desc{color:var(--ink-2);margin:6px 0 10px}
table.per{border-collapse:collapse;width:100%;font-size:13px;margin:6px 0 10px}
table.per td{padding:6px 8px;border-top:1px solid var(--grid);vertical-align:top}
table.per td.c{white-space:nowrap;width:170px}
table.per td.s{white-space:nowrap;width:110px}
table.per td.conf{color:var(--muted);white-space:nowrap;width:120px;font-size:12px}
.same{color:var(--muted);font-size:12.5px;margin:4px 0 10px}
.fix{border-left:3px solid var(--good);padding:6px 12px;background:var(--surface-2);border-radius:0 8px 8px 0}
.refs{margin:8px 0 0;padding-left:18px;color:var(--ink-2);font-size:12.5px}
.err{border:1px solid var(--critical);border-radius:8px;padding:10px 14px;margin-bottom:16px;font-family:ui-monospace,Consolas,monospace;font-size:12px;white-space:pre-wrap}
.tip{position:fixed;pointer-events:none;z-index:10;max-width:380px;background:var(--surface-2);color:var(--ink);
  border:1px solid var(--axis);border-radius:8px;padding:10px 12px;font-size:12.5px;box-shadow:0 6px 24px rgba(0,0,0,.35);display:none}
.tip .t{font-weight:650;display:flex;gap:6px;align-items:center;margin-bottom:4px}
.tip .c{color:var(--muted);font-size:11.5px;margin-top:6px}
footer{color:var(--muted);font-size:12px;padding:0 40px 40px;max-width:1500px;margin:0 auto}
.empty{color:var(--ink-2);padding:20px 0}
"""

_JS = """
(function(){
  const tip = document.getElementById('tip');
  document.querySelectorAll('td.cell').forEach(td => {
    td.addEventListener('mouseenter', () => {
      const d = td.dataset;
      tip.replaceChildren();
      const t = document.createElement('div'); t.className = 't';
      const dot = document.createElement('span'); dot.className = 'dot d-' + d.sev;
      t.append(dot, document.createTextNode(d.chain + ' \\u00b7 ' + d.sevlong));
      const n = document.createElement('div'); n.textContent = d.note;
      const c = document.createElement('div'); c.className = 'c'; c.textContent = 'confidence: ' + d.conf;
      tip.append(t, n, c);
      tip.style.display = 'block';
    });
    td.addEventListener('mousemove', e => {
      const pad = 14, w = tip.offsetWidth, h = tip.offsetHeight;
      let x = e.clientX + pad, y = e.clientY + pad;
      if (x + w > window.innerWidth - 8) x = e.clientX - w - pad;
      if (y + h > window.innerHeight - 8) y = e.clientY - h - pad;
      tip.style.left = x + 'px'; tip.style.top = y + 'px';
    });
    td.addEventListener('mouseleave', () => { tip.style.display = 'none'; });
  });
  const chips = document.querySelectorAll('.chip[data-sev]');
  const search = document.getElementById('q');
  function apply(){
    const on = new Set([...chips].filter(c => c.getAttribute('aria-pressed') === 'true').map(c => c.dataset.sev));
    const q = (search.value || '').toLowerCase();
    document.querySelectorAll('[data-row]').forEach(el => {
      const show = on.has(el.dataset.sev) && (!q || el.dataset.text.includes(q));
      el.style.display = show ? '' : 'none';
    });
  }
  chips.forEach(c => c.addEventListener('click', () => {
    c.setAttribute('aria-pressed', c.getAttribute('aria-pressed') === 'true' ? 'false' : 'true'); apply();
  }));
  search.addEventListener('input', apply);
})();
"""


def _e(x) -> str:
    return escape(str(x), quote=True)


def render_html(report) -> str:
    kb = load_knowledge()
    chains = report.chains
    counts = report.counts()
    findings = report.findings
    generated = _dt.datetime.now().strftime("%Y-%m-%d %H:%M")

    # --- per-chain tallies -----------------------------------------------
    tally = {c: {"high": 0, "medium": 0, "check": 0, "low": 0} for c in chains}
    for f in findings:
        for c, a in f.assessments.items():
            if a.severity in tally[c]:
                tally[c][a.severity] += 1
    ranked = sorted(chains, key=lambda c: (-tally[c]["high"], -tally[c]["medium"], -tally[c]["check"]))
    riskiest = ranked[0] if ranked and findings else None

    p = []
    p.append("<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>")
    p.append("<meta name='viewport' content='width=device-width,initial-scale=1'>")
    p.append(f"<title>ChainDrift report</title><style>{_CSS}</style></head><body>")
    p.append("<header class='top'><div><div class='brand'>ChainDrift<span class='tag'>cross-chain divergence report</span></div></div>")
    p.append(
        f"<div class='meta'>target <code>{_e(report.target)}</code><br>"
        f"solc {_e(report.compiler or '?')} &middot; {len(report.contracts)} contracts &middot; "
        f"{len(chains)} chains &middot; generated {generated} &middot; v{__version__}</div></header><main>"
    )
    for err in report.errors:
        p.append(f"<div class='err'>{_e(err)}</div>")

    # --- tiles --------------------------------------------------------------
    def tile(label, value, sub="", sev=None):
        dot = f"<span class='dot d-{sev}'></span>" if sev else ""
        return f"<div class='tile'><div class='k'>{dot}{_e(label)}</div><div class='v'>{_e(value)}</div><div class='s'>{_e(sub)}</div></div>"

    p.append("<section class='tiles'>")
    p.append(tile("Findings", len(findings), f"{len({f.site.rule_id for f in findings})} rules triggered"))
    p.append(tile("High", counts.get("high", 0), "breaks or is exploitable on some chain", "high"))
    p.append(tile("Medium", counts.get("medium", 0), "behaves differently", "medium"))
    p.append(tile("Verify", counts.get("check", 0), "unknown behaviour; check docs", "check"))
    if riskiest:
        t = tally[riskiest]
        p.append(tile("Most divergent chain", kb.chains[riskiest].name, f"{t['high']} high, {t['medium']} medium"))
    p.append("</section>")

    # --- matrix ---------------------------------------------------------------
    p.append("<section class='card'><h2>Divergence matrix</h2>")
    p.append("<p class='sub'>One row per code site, one column per chain. Hover a cell for the chain-specific behaviour. "
             "Ethereum is the reference implementation.</p>")
    p.append("<div class='filters'>")
    for sev in ("high", "medium", "check", "low", "info"):
        if counts.get(sev):
            p.append(f"<button class='chip' data-sev='{sev}' aria-pressed='true'><span class='dot d-{sev}'></span>"
                     f"{_LONG[sev]} ({counts[sev]})</button>")
    p.append("<input id='q' class='search' type='search' placeholder='Filter by rule, file, contract...'></div>")

    if findings:
        p.append("<div class='matrix-wrap'><table class='matrix'><thead><tr><th class='left'>Finding</th><th class='left'>Location</th>")
        for c in chains:
            cls = "ref" if c == "ethereum" else ""
            p.append(f"<th class='{cls}'>{_e(kb.chains[c].name)}</th>")
        p.append("</tr></thead><tbody>")
        for i, f in enumerate(findings):
            s = f.site
            text = f"{s.rule_id} {f.title} {s.file} {s.contract} {s.function or ''} {s.detail}".lower()
            p.append(f"<tr data-row data-sev='{f.severity}' data-text='{_e(text)}'>")
            p.append(f"<td class='what'><a href='#f-{i}'>{_e(f.title)}</a><div class='d' title='{_e(s.detail)}'>{_e(s.detail)}</div></td>")
            p.append(f"<td class='loc'>{_e(s.file)}:{s.line}</td>")
            for c in chains:
                a = f.assessments[c]
                dot = "" if a.severity == "none" else f"<span class='dot d-{a.severity}'></span>"
                p.append(
                    f"<td class='cell c-{a.severity}' data-sev='{a.severity}' data-sevlong='{_e(_LONG[a.severity])}' "
                    f"data-chain='{_e(kb.chains[c].name)}' data-note='{_e(a.note)}' data-conf='{_e(a.confidence)}'>"
                    f"<span class='in'>{dot}{_LABEL[a.severity]}</span></td>"
                )
            p.append("</tr>")
        p.append("</tbody></table></div>")
        p.append("<div class='legend'>" + "".join(
            f"<span><span class='dot d-{s}'></span>{_LONG[s]}</span>" for s in ("high", "medium", "check", "low", "none")
        ) + "</div>")
    else:
        p.append("<div class='empty'>No cross-chain divergences found for the selected chains.</div>")
    p.append("</section>")

    # --- per-chain table -----------------------------------------------------
    if findings:
        p.append("<section class='card'><h2>By chain</h2><p class='sub'>How many findings change behaviour on each chain.</p>")
        p.append("<table class='chains'><thead><tr><th>Chain</th><th>Type</th><th>VM</th>"
                 "<th class='n'>High</th><th class='n'>Medium</th><th class='n'>Verify</th><th class='n'>Low</th></tr></thead><tbody>")
        for c in ranked:
            ch, t = kb.chains[c], tally[c]
            p.append(f"<tr><td><a href='{_e(ch.docs)}'>{_e(ch.name)}</a></td><td>{_e(ch.kind)}</td><td>{_e(ch.vm)}</td>"
                     f"<td class='n'>{t['high']}</td><td class='n'>{t['medium']}</td><td class='n'>{t['check']}</td><td class='n'>{t['low']}</td></tr>")
        p.append("</tbody></table></section>")

    # --- detail cards -------------------------------------------------------
    for i, f in enumerate(findings):
        s = f.site
        text = f"{s.rule_id} {f.title} {s.file} {s.contract} {s.function or ''} {s.detail}".lower()
        where = f"{s.contract}.{s.function}" if s.function else s.contract
        p.append(f"<article class='finding' id='f-{i}' data-row data-sev='{f.severity}' data-text='{_e(text)}'>")
        p.append(f"<div class='fh'><span class='badge'><span class='dot d-{f.severity}'></span>{_LONG[f.severity].upper()}</span>"
                 f"<h3>{_e(f.title)}</h3><span class='rule'>{_e(s.rule_id)}</span></div>")
        p.append(f"<div class='where'><code>{_e(s.file)}:{s.line}</code> in <code>{_e(where)}</code> &mdash; {_e(s.detail)}</div>")
        if s.snippet:
            p.append(f"<pre class='snip'>{s.line:>4} | {_e(s.snippet)}</pre>")
        p.append(f"<p class='desc'>{_e(f.description)}</p>")
        groups = grouped_assessments(f, kb)
        if groups:
            p.append("<table class='per'>")
            for names, severity, confidence, note in groups:
                p.append(f"<tr><td class='c'>{'<br>'.join(_e(n) for n in names)}</td>"
                         f"<td class='s'><span class='badge'><span class='dot d-{severity}'></span>{_LONG[severity]}</span></td>"
                         f"<td>{_e(note)}</td><td class='conf'>confidence: {_e(confidence)}</td></tr>")
            p.append("</table>")
        same = [kb.chains[c].name for c, a in f.assessments.items() if a.severity == "none"]
        if same:
            p.append(f"<div class='same'>Unaffected on: {_e(', '.join(same))}</div>")
        p.append(f"<div class='fix'><strong>Fix:</strong> {_e(f.fix)}</div>")
        if f.references:
            p.append("<ul class='refs'>" + "".join(f"<li><a href='{_e(r)}'>{_e(r)}</a></li>" for r in f.references) + "</ul>")
        p.append("</article>")

    p.append("</main><footer>ChainDrift checks code against a curated knowledge base of chain behaviour (reviewed mid-2026). "
             "Chains upgrade often: every chain-specific claim carries a confidence level and should be verified against the chain's "
             "own documentation before you rely on it.</footer>")
    p.append("<div id='tip' class='tip' role='tooltip'></div>")
    p.append(f"<script>{_JS}</script></body></html>")
    return "".join(p)
