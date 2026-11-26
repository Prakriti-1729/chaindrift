"""Analysis context: one compiled project plus convenient iteration and Site construction."""

from __future__ import annotations

import os
from pathlib import Path

from .knowledge import KnowledgeBase
from .models import Site


def _display_name(function) -> str | None:
    if function is None:
        return None
    name = function.name
    if name.startswith("slitherConstructorConstantVariables"):
        return "(constant initializers)"
    if name.startswith("slitherConstructorVariables"):
        return "(state variable initializers)"
    return function.full_name


class Context:
    def __init__(self, slither, kb: KnowledgeBase, base_dir: Path, include_deps: bool = False):
        self.slither = slither
        self.kb = kb
        self.base_dir = base_dir
        self.contracts = [
            c for c in slither.contracts if include_deps or not c.is_from_dependency()
        ]
        self._lines: dict[str, list[str]] = {}

    # ---------------------------------------------------------------- iteration
    def functions(self):
        for contract in self.contracts:
            for function in contract.functions_and_modifiers_declared:
                yield contract, function

    def nodes(self):
        for contract, function in self.functions():
            for node in function.nodes:
                yield contract, function, node

    def irs(self):
        for contract, function, node in self.nodes():
            for ir in node.irs:
                yield contract, function, node, ir

    # ------------------------------------------------------------------- sites
    def _source_line(self, path: str, line: int) -> str:
        if path not in self._lines:
            try:
                self._lines[path] = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                self._lines[path] = []
        lines = self._lines[path]
        return lines[line - 1].strip() if 0 < line <= len(lines) else ""

    def _rel(self, path: str) -> str:
        try:
            return os.path.relpath(path, self.base_dir).replace("\\", "/")
        except ValueError:  # different drive on Windows
            return path.replace("\\", "/")

    def site(self, rule_id, contract, function, located, detail, variant=None) -> Site:
        """Build a Site. `located` is anything with a .source_mapping (node, variable, contract)."""
        sm = located.source_mapping
        path = sm.filename.absolute
        line = sm.lines[0] if sm.lines else 0
        return Site(
            rule_id=rule_id,
            contract=contract.name,
            function=_display_name(function),
            file=self._rel(path),
            line=line,
            snippet=self._source_line(path, line),
            detail=detail,
            variant=variant,
        )

    # ----------------------------------------------------------------- bytecode
    def bytecodes(self):
        """Yield (contract, init_hex, runtime_hex) for every analysed contract with code."""
        wanted = {(c.source_mapping.filename.absolute, c.name): c for c in self.contracts}
        by_name: dict[str, list] = {}
        for c in self.contracts:
            by_name.setdefault(c.name, []).append(c)
        seen = set()
        for cu in self.slither.crytic_compile.compilation_units.values():
            for su in cu.source_units.values():
                su_path = getattr(su.filename, "absolute", str(su.filename))
                for name in su.contracts_names:
                    contract = wanted.get((su_path, name))
                    if contract is None and len(by_name.get(name, [])) == 1:
                        contract = by_name[name][0]
                    if contract is None or id(contract) in seen:
                        continue
                    seen.add(id(contract))
                    init = su.bytecode_init(name) or ""
                    runtime = su.bytecode_runtime(name) or ""
                    if init or runtime:
                        yield contract, init, runtime
