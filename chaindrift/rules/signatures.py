"""Cross-chain signature replay via EIP-712 domains."""

from __future__ import annotations

from slither.slithir.variables import Constant

from .base import Rule, global_read


def _is_constructor_like(function) -> bool:
    return function.is_constructor or function.name.startswith("slitherConstructor")


class ChainIdReplay(Rule):
    id = "chainid-replay"

    def detect(self, ctx):
        for contract in ctx.contracts:
            domain_sites = []
            for function in contract.functions_and_modifiers_declared:
                for node in function.nodes:
                    for ir in node.irs:
                        for v in ir.read:
                            if isinstance(v, Constant) and isinstance(v.value, str) and "EIP712Domain(" in v.value:
                                domain_sites.append((function, node, v.value))
            if not domain_sites:
                continue

            reads_outside_ctor = reads_in_ctor = False
            for function in contract.functions_and_modifiers:  # includes inherited code
                for node in function.nodes:
                    if global_read(node, {"block.chainid"}, {"chainid"}):
                        if _is_constructor_like(function):
                            reads_in_ctor = True
                        else:
                            reads_outside_ctor = True

            function, node, typestring = domain_sites[0]
            if "chainId" not in typestring:
                yield ctx.site(self.id, contract, function, node, f"EIP-712 domain type has no chainId: {typestring!r}", "no-chainid")
            elif not reads_in_ctor and not reads_outside_ctor:
                yield ctx.site(self.id, contract, function, node, "EIP-712 domain declares chainId but never reads block.chainid (hardcoded value?)", "hardcoded")
            elif reads_in_ctor and not reads_outside_ctor:
                yield ctx.site(self.id, contract, function, node, "EIP-712 domain separator is cached at deployment; block.chainid is never re-checked", "cached")
