from __future__ import annotations

import os
import sys
import textwrap

from ..knowledge import load_knowledge
from ..models import SEVERITIES
from .common import grouped_assessments

_COLORS = {"high": "31;1", "medium": "33", "check": "35", "low": "36", "info": "37", "none": "32"}


def _use_color(stream) -> bool:
    return hasattr(stream, "isatty") and stream.isatty() and not os.environ.get("NO_COLOR")


def render_text(report, color: bool | None = None, stream=sys.stdout) -> str:
    kb = load_knowledge()
    color = _use_color(stream) if color is None else color

    def paint(sev: str, text: str) -> str:
        return f"\033[{_COLORS[sev]}m{text}\033[0m" if color else text

    out = []
    out.append("ChainDrift - cross-chain divergence report")
    out.append(f"Target:    {report.target}")
    out.append(f"Compiler:  solc {report.compiler or '?'}   Contracts: {len(report.contracts)}")
    out.append("Chains:    " + ", ".join(kb.chains[c].name for c in report.chains))
    counts = report.counts()
    summary = "  ".join(
        paint(s, f"{counts[s]} {s}") for s in reversed(SEVERITIES) if counts.get(s)
    )
    out.append(f"Findings:  {len(report.findings)}  ({summary or 'none'})")
    for err in report.errors:
        out.append(paint("high", f"ERROR: {err}"))
    out.append("")

    width = 100
    for f in report.findings:
        s = f.site
        out.append(paint(f.severity, f"[{f.severity.upper()}]") + f" {f.title}  ({s.rule_id})")
        where = f"{s.file}:{s.line}" + (f"  in {s.contract}.{s.function}" if s.function else f"  in {s.contract}")
        out.append(f"  {where}")
        if s.snippet:
            out.append(f"  > {s.snippet[:width]}")
        out.append(f"  {s.detail}")
        for names, severity, _conf, note in grouped_assessments(f, kb):
            out.append(f"    {paint(severity, severity.upper())}  {', '.join(names)}")
            for line in textwrap.wrap(note, width=width - 8):
                out.append(" " * 8 + line)
        same = [kb.chains[c].name for c, a in f.assessments.items() if a.severity == "none"]
        if same:
            out.append(f"    {paint('none', 'unaffected:')} {', '.join(same)}")
        out.append(f"  fix: {f.fix}")
        out.append("")
    if not report.findings and not report.errors:
        out.append(paint("none", "No cross-chain divergences found for the selected chains."))
    return "\n".join(out)
