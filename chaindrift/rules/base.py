from __future__ import annotations

from collections.abc import Iterable

from slither.slithir.operations import SolidityCall

from ..ir import call_name
from ..models import Assessment, Site


class Rule:
    """A rule finds Sites (chain-independent) and assesses each Site per chain."""

    id: str = ""

    def detect(self, ctx) -> Iterable[Site]:
        raise NotImplementedError

    def assess(self, ctx, site: Site, chain: str) -> Assessment:
        return ctx.kb.assess_rule(self.id, chain, site.variant)


def global_read(node, solidity_names: set[str], yul_names: set[str]) -> str | None:
    """Return the name of the first matching global read in a node.

    Covers both Solidity (`block.number`) and inline assembly (`number()`).
    """
    for v in node.solidity_variables_read:
        if v.name in solidity_names:
            return v.name
    for ir in node.irs:
        if isinstance(ir, SolidityCall):
            name = call_name(ir)
            if name in yul_names:
                return f"{name}() (assembly)"
    return None
