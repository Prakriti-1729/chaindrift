"""Loads the TOML knowledge base that describes how chains diverge from Ethereum."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources

from ..models import SEVERITIES, Assessment


def _load(name: str) -> dict:
    with resources.files(__package__).joinpath(name).open("rb") as fh:
        return tomllib.load(fh)


@dataclass(frozen=True)
class Chain:
    id: str
    name: str
    chain_id: int
    kind: str
    vm: str
    block_time_s: float
    docs: str
    reviewed: str


class KnowledgeBase:
    def __init__(self) -> None:
        self.chains: dict[str, Chain] = {
            cid: Chain(id=cid, **data) for cid, data in _load("chains.toml")["chains"].items()
        }
        self.rules: dict[str, dict] = _load("divergences.toml")["rules"]
        self.precompiles: dict[int, dict] = {
            int(k, 16): v for k, v in _load("precompiles.toml")["precompiles"].items()
        }
        self.addresses: dict[int, dict] = {
            int(k, 16): {**v, "address": k} for k, v in _load("addresses.toml")["addresses"].items()
        }
        opcodes = _load("opcodes.toml")
        self.vm_notes: dict[str, dict] = opcodes.get("vm_notes", {})
        self.opcodes: dict[str, dict] = opcodes["opcodes"]
        self.chain_by_numeric_id = {c.chain_id: c for c in self.chains.values()}
        self._validate()

    # ------------------------------------------------------------------ helpers
    def render(self, text: str, chain: str) -> str:
        c = self.chains[chain]
        bt = c.block_time_s
        return text.replace("{chain}", c.name).replace("{block_time_s}", f"{bt:g}")

    def make(self, chain: str, entry: dict) -> Assessment:
        return Assessment(
            chain=chain,
            severity=entry["severity"],
            confidence=entry.get("confidence", "medium"),
            note=self.render(entry.get("note", ""), chain),
        )

    def assess_rule(self, rule_id: str, chain: str, variant: str | None = None) -> Assessment:
        """Look up a rule's behaviour on a chain.

        Precedence: variant+chain, variant default, rule+chain, rule default.
        """
        rule = self.rules[rule_id]
        if variant and variant in rule.get("variants", {}):
            v = rule["variants"][variant]
            if chain in v.get("chains", {}):
                return self.make(chain, v["chains"][chain])
            if "default" in v:
                return self.make(chain, v["default"])
        if chain in rule.get("chains", {}):
            return self.make(chain, rule["chains"][chain])
        return self.make(chain, rule["default"])

    def _validate(self) -> None:
        """Fail fast on typos in the TOML, since it is meant to be edited by contributors."""
        problems = []

        def check_entry(where: str, entry: dict) -> None:
            if entry.get("severity") not in SEVERITIES:
                problems.append(f"{where}: bad severity {entry.get('severity')!r}")

        for rid, rule in self.rules.items():
            for key in ("title", "description", "fix"):
                if key not in rule:
                    problems.append(f"rules.{rid}: missing {key}")
            if "default" in rule:
                check_entry(f"rules.{rid}.default", rule["default"])
            for chain, entry in rule.get("chains", {}).items():
                if chain not in self.chains:
                    problems.append(f"rules.{rid}.chains: unknown chain {chain!r}")
                check_entry(f"rules.{rid}.chains.{chain}", entry)
            for vname, v in rule.get("variants", {}).items():
                if "default" in v:
                    check_entry(f"rules.{rid}.variants.{vname}.default", v["default"])
                for chain, entry in v.get("chains", {}).items():
                    if chain not in self.chains:
                        problems.append(f"rules.{rid}.variants.{vname}: unknown chain {chain!r}")
                    check_entry(f"rules.{rid}.variants.{vname}.chains.{chain}", entry)
        for addr, p in self.precompiles.items():
            for chain, entry in p.get("chains", {}).items():
                if chain not in self.chains:
                    problems.append(f"precompiles.{addr:#x}: unknown chain {chain!r}")
                if entry.get("support") not in ("yes", "no", "limited", "unknown"):
                    problems.append(f"precompiles.{addr:#x}.{chain}: bad support value")
        for addr, a in self.addresses.items():
            on = a["on"]
            chains = (a.get("missing", []) if on == "*" else on)
            for chain in chains:
                if chain not in self.chains:
                    problems.append(f"addresses.{a['address']}: unknown chain {chain!r}")
        for name, op in self.opcodes.items():
            check_entry(f"opcodes.{name}.default", op["default"])
            for chain, entry in op.get("chains", {}).items():
                if chain not in self.chains:
                    problems.append(f"opcodes.{name}: unknown chain {chain!r}")
                check_entry(f"opcodes.{name}.chains.{chain}", entry)
        if problems:
            raise ValueError("Invalid ChainDrift knowledge base:\n  " + "\n  ".join(problems))


@lru_cache(maxsize=1)
def load_knowledge() -> KnowledgeBase:
    return KnowledgeBase()
