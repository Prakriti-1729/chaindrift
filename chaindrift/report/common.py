from __future__ import annotations

from ..models import SEVERITY_RANK


def grouped_assessments(finding, kb):
    """Group affected chains that share the same severity and (chain-agnostic) note.

    Returns [(chain_names, severity, confidence, note)], most severe first.
    """
    groups: dict[tuple, dict] = {}
    for chain, a in finding.assessments.items():
        if a.severity == "none":
            continue
        name = kb.chains[chain].name
        template = a.note.replace(name, "{chain}")
        key = (a.severity, a.confidence, template)
        groups.setdefault(key, {"names": [], "note": a.note})["names"].append(name)
    out = []
    for (severity, confidence, template), g in groups.items():
        names = g["names"]
        note = g["note"] if len(names) == 1 else template.replace("{chain}", "these chains")
        out.append((names, severity, confidence, note))
    out.sort(key=lambda g: -SEVERITY_RANK[g[1]])
    return out
