"""Command-line interface: `chaindrift scan`, `chaindrift chains`, `chaindrift rules`."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .knowledge import load_knowledge
from .models import SEVERITIES, SEVERITY_RANK

FORMATS = ("text", "json", "html", "sarif")


def _cmd_scan(args) -> int:
    from .engine import analyze
    from .report import render_html, render_json, render_sarif, render_text

    chains = [c.strip() for c in args.chains.split(",")] if args.chains else None
    rules = [r.strip() for r in args.rules.split(",")] if args.rules else None
    try:
        report = analyze(
            args.target,
            chains=chains,
            solc=args.solc,
            solc_args=args.solc_args,
            include_deps=args.include_deps,
            rules=rules,
            min_severity=args.min_severity,
        )
    except (ValueError, KeyError) as exc:
        print(f"chaindrift: {exc}", file=sys.stderr)
        return 2

    fmt = args.format
    if fmt is None and args.output:
        suffix = Path(args.output).suffix.lower()
        fmt = {".html": "html", ".htm": "html", ".json": "json", ".sarif": "sarif"}.get(suffix, "text")
    fmt = fmt or "text"

    if fmt == "text":
        out = render_text(report, color=False if args.output else None)
    else:
        out = {"json": render_json, "html": render_html, "sarif": render_sarif}[fmt](report)

    if args.output:
        Path(args.output).write_text(out, encoding="utf-8")
        counts = report.counts()
        summary = ", ".join(f"{counts[s]} {s}" for s in reversed(SEVERITIES) if counts.get(s)) or "no findings"
        print(f"Wrote {fmt} report to {args.output} ({len(report.findings)} findings: {summary})")
    else:
        print(out)

    # Exit codes: 0 = clean, 1 = a finding reached --fail-on, 2 = something could not be analysed.
    # A compile error must never let CI pass silently, so it wins over everything else.
    if report.errors:
        print(f"chaindrift: {len(report.errors)} target(s) failed to compile; results are incomplete.", file=sys.stderr)
        return 2
    if args.fail_on and any(SEVERITY_RANK[f.severity] >= SEVERITY_RANK[args.fail_on] for f in report.findings):
        return 1
    return 0


def _cmd_chains(_args) -> int:
    kb = load_knowledge()
    print(f"{'id':<11} {'name':<19} {'chain id':>9}  {'block':>6}  type")
    for c in kb.chains.values():
        print(f"{c.id:<11} {c.name:<19} {c.chain_id:>9}  {c.block_time_s:>5g}s  {c.kind}")
    return 0


def _cmd_rules(_args) -> int:
    from .rules import ALL_RULES

    kb = load_knowledge()
    for r in ALL_RULES:
        print(f"{r.id:<18} {kb.rules[r.id]['title']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="chaindrift",
        description="Find Solidity code that behaves differently across EVM chains.",
    )
    p.add_argument("--version", action="version", version=f"chaindrift {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("scan", help="analyse a .sol file, a folder of .sol files, or a Foundry/Hardhat project")
    s.add_argument("target")
    s.add_argument("--chains", help="comma-separated chain ids (default: all). See `chaindrift chains`.")
    s.add_argument("--rules", help="comma-separated rule ids to run (default: all). See `chaindrift rules`.")
    s.add_argument("--format", choices=FORMATS, help="output format (default: text, or inferred from -o)")
    s.add_argument("-o", "--output", help="write the report to a file")
    s.add_argument("--solc", help="path to a solc binary (default: $CHAINDRIFT_SOLC, solc-select, then PATH)")
    s.add_argument("--solc-args", help="extra solc arguments, e.g. \"--evm-version paris\"")
    s.add_argument("--include-deps", action="store_true", help="also report findings inside dependencies (lib/, node_modules/)")
    s.add_argument("--min-severity", choices=SEVERITIES[1:], default="info", help="hide findings below this severity")
    s.add_argument("--fail-on", choices=SEVERITIES[1:], help="exit with code 1 if any finding is at or above this severity (for CI)")
    s.set_defaults(func=_cmd_scan)

    c = sub.add_parser("chains", help="list the chains in the knowledge base")
    c.set_defaults(func=_cmd_chains)
    r = sub.add_parser("rules", help="list the detection rules")
    r.set_defaults(func=_cmd_rules)
    return p


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
