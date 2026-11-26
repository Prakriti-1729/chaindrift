"""Compile a target with Slither, run every rule, and assess findings per chain."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from .context import Context
from .knowledge import load_knowledge
from .models import SEVERITY_RANK, Finding
from .rules import ALL_RULES, RULES_BY_ID
from .solc import find_solc

FRAMEWORK_MARKERS = ("foundry.toml", "hardhat.config.js", "hardhat.config.ts", "truffle-config.js", "brownie-config.yaml")
SKIP_DIRS = {"node_modules", "lib", ".venv", "venv", "cache", "out", "artifacts", ".git", "crytic-export"}


@dataclass
class Report:
    target: str
    chains: list[str]
    findings: list[Finding] = field(default_factory=list)
    contracts: list[str] = field(default_factory=list)
    compiler: str | None = None
    errors: list[str] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for f in self.findings:
            out[f.severity] = out.get(f.severity, 0) + 1
        return out


def _compile_units(target: Path):
    """Return a list of compile targets: the framework root, or each .sol file."""
    if target.is_file():
        return [target]
    if any((target / m).exists() for m in FRAMEWORK_MARKERS):
        return [target]
    files = []
    for p in sorted(target.rglob("*.sol")):
        if not SKIP_DIRS.intersection(p.relative_to(target).parts[:-1]):
            files.append(p)
    return files


def analyze(
    target: str | Path,
    chains: list[str] | None = None,
    solc: str | None = None,
    solc_args: str | None = None,
    include_deps: bool = False,
    rules: list[str] | None = None,
    min_severity: str = "info",
) -> Report:
    from slither import Slither  # imported lazily: slow, and not needed for `chaindrift chains`

    logging.getLogger("CryticCompile").setLevel(logging.ERROR)
    logging.getLogger("Slither").setLevel(logging.ERROR)

    kb = load_knowledge()
    chains = chains or list(kb.chains)
    unknown = [c for c in chains if c not in kb.chains]
    if unknown:
        raise ValueError(f"Unknown chain(s): {', '.join(unknown)}. Run `chaindrift chains` to list them.")
    bad_rules = [r for r in (rules or []) if r not in RULES_BY_ID]
    if bad_rules:
        raise ValueError(f"Unknown rule(s): {', '.join(bad_rules)}. Run `chaindrift rules` to list them.")
    selected_rules = [RULES_BY_ID[r] for r in rules] if rules else ALL_RULES

    shown_target = str(target).replace("\\", "/")
    target = Path(target).resolve()
    if not target.exists():
        raise ValueError(f"Target not found: {shown_target}")
    units = _compile_units(target)
    if not units:
        raise ValueError(f"No Solidity files found under {shown_target}")
    base_dir = target if target.is_dir() else target.parent
    report = Report(target=shown_target, chains=chains)
    solc_path = find_solc(solc)

    seen_sites = set()
    seen_contracts = set()
    for unit in units:
        kwargs = {}
        if solc_path and unit.is_file():
            kwargs["solc"] = solc_path
        if solc_args:
            kwargs["solc_args"] = solc_args
        try:
            sl = Slither(str(unit), **kwargs)
        except Exception as exc:  # compilation errors: report and keep going
            report.errors.append(f"{unit}: {exc}")
            continue
        for cu in sl.crytic_compile.compilation_units.values():
            report.compiler = report.compiler or cu.compiler_version.version
        ctx = Context(sl, kb, base_dir, include_deps=include_deps)
        for c in ctx.contracts:
            key = (c.source_mapping.filename.absolute, c.name)
            if key not in seen_contracts:
                seen_contracts.add(key)
                report.contracts.append(c.name)

        for rule in selected_rules:
            meta = kb.rules[rule.id]
            for site in rule.detect(ctx):
                key = (site.rule_id, site.file, site.line, site.contract, site.variant)
                if key in seen_sites:
                    continue
                seen_sites.add(key)
                finding = Finding(
                    site=site,
                    title=meta["title"],
                    description=meta["description"],
                    fix=meta["fix"],
                    references=list(meta.get("references", [])),
                )
                for chain in chains:
                    finding.assessments[chain] = rule.assess(ctx, site, chain)
                if SEVERITY_RANK[finding.severity] >= max(SEVERITY_RANK[min_severity], 1):
                    report.findings.append(finding)

    report.findings.sort(key=lambda f: (-SEVERITY_RANK[f.severity], f.site.file, f.site.line, f.site.rule_id))
    return report
