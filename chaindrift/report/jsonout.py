from __future__ import annotations

import json

from .. import __version__


def report_dict(report) -> dict:
    return {
        "tool": "chaindrift",
        "version": __version__,
        "target": report.target,
        "compiler": report.compiler,
        "chains": report.chains,
        "contracts": report.contracts,
        "summary": report.counts(),
        "errors": report.errors,
        "findings": [f.to_dict() for f in report.findings],
    }


def render_json(report) -> str:
    return json.dumps(report_dict(report), indent=2)
