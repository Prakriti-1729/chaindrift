"""Core data types shared by the engine, rules and reporters."""

from __future__ import annotations

from dataclasses import dataclass, field

# Ordered from least to most urgent. "check" means "we don't know: verify before deploying",
# which is more urgent than a known-low issue but less than a known-medium one.
SEVERITIES = ("none", "info", "low", "check", "medium", "high")
SEVERITY_RANK = {s: i for i, s in enumerate(SEVERITIES)}


def max_severity(severities) -> str:
    best = "none"
    for s in severities:
        if SEVERITY_RANK[s] > SEVERITY_RANK[best]:
            best = s
    return best


@dataclass(frozen=True)
class Site:
    """A place in the code where a rule's construct appears. Chain-independent."""

    rule_id: str
    contract: str
    function: str | None
    file: str
    line: int
    snippet: str
    detail: str
    variant: str | None = None


@dataclass(frozen=True)
class Assessment:
    """How one Site behaves on one chain."""

    chain: str
    severity: str
    confidence: str
    note: str


@dataclass
class Finding:
    site: Site
    title: str
    description: str
    fix: str
    references: list[str]
    assessments: dict[str, Assessment] = field(default_factory=dict)

    @property
    def severity(self) -> str:
        return max_severity(a.severity for a in self.assessments.values())

    @property
    def affected_chains(self) -> list[str]:
        return [c for c, a in self.assessments.items() if a.severity != "none"]

    def to_dict(self) -> dict:
        s = self.site
        return {
            "rule": s.rule_id,
            "title": self.title,
            "severity": self.severity,
            "contract": s.contract,
            "function": s.function,
            "file": s.file,
            "line": s.line,
            "snippet": s.snippet,
            "detail": s.detail,
            "variant": s.variant,
            "description": self.description,
            "fix": self.fix,
            "references": self.references,
            "chains": {
                c: {"severity": a.severity, "confidence": a.confidence, "note": a.note}
                for c, a in self.assessments.items()
            },
        }
