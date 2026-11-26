"""SARIF 2.1.0 output, so findings show up in GitHub code scanning."""

from __future__ import annotations

import json

from .. import __version__
from ..knowledge import load_knowledge

_LEVEL = {"high": "error", "medium": "warning", "check": "warning", "low": "note", "info": "note"}


def render_sarif(report) -> str:
    kb = load_knowledge()
    used = sorted({f.site.rule_id for f in report.findings})
    rules = [
        {
            "id": rid,
            "name": rid,
            "shortDescription": {"text": kb.rules[rid]["title"]},
            "fullDescription": {"text": kb.rules[rid]["description"]},
            "help": {"text": kb.rules[rid]["fix"]},
        }
        for rid in used
    ]
    results = []
    for f in report.findings:
        s = f.site
        affected = [
            f"{kb.chains[c].name}: {a.severity} - {a.note}"
            for c, a in f.assessments.items()
            if a.severity != "none"
        ]
        results.append({
            "ruleId": s.rule_id,
            "level": _LEVEL.get(f.severity, "note"),
            "message": {"text": f"{s.detail}. Diverges on: " + " | ".join(affected)},
            "locations": [{
                "physicalLocation": {
                    "artifactLocation": {"uri": s.file},
                    "region": {"startLine": max(s.line, 1)},
                }
            }],
            "properties": {"chainSeverity": {c: a.severity for c, a in f.assessments.items()}},
        })
    return json.dumps({
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [{
            "tool": {"driver": {
                "name": "ChainDrift",
                "version": __version__,
                "rules": rules,
            }},
            "results": results,
        }],
    }, indent=2)
