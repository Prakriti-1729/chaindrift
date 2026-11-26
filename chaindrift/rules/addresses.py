"""Rules about addresses: precompiles and hardcoded chain-specific contracts."""

from __future__ import annotations

from slither.slithir.operations import HighLevelCall, LowLevelCall, SolidityCall

from ..ir import call_name, constant_int, function_trackers
from ..models import Assessment
from .base import Rule
from .execution import YUL_CALLS

_BUILTIN_PRECOMPILES = {"ecrecover": 0x01, "sha256": 0x02, "ripemd160": 0x03}
_SUPPORT_TO_SEVERITY = {"yes": "none", "no": "high", "limited": "medium", "unknown": "check"}


def call_targets(ctx):
    """Yield (contract, function, node, address_int, how) for calls to a constant address."""
    for contract, function in ctx.functions():
        for node, ir, tracker in function_trackers(function):
            if isinstance(ir, (LowLevelCall, HighLevelCall)):
                value = tracker.resolve(ir.destination)
                if value is not None:
                    yield contract, function, node, value, f"{type(ir).__name__}"
            elif isinstance(ir, SolidityCall):
                name = call_name(ir)
                if name in YUL_CALLS and len(ir.arguments) > 1:
                    value = tracker.resolve(ir.arguments[1])
                    if value is not None:
                        yield contract, function, node, value, f"assembly {name}"
                elif name in _BUILTIN_PRECOMPILES:
                    yield contract, function, node, _BUILTIN_PRECOMPILES[name], f"builtin {name}()"


class Precompile(Rule):
    id = "precompile"

    def detect(self, ctx):
        for contract, function, node, value, how in call_targets(ctx):
            p = ctx.kb.precompiles.get(value)
            if p is not None:
                yield ctx.site(
                    self.id, contract, function, node,
                    f"calls precompile {value:#04x} {p['name']} via {how}",
                    variant=f"{value:#x}",
                )

    def assess(self, ctx, site, chain) -> Assessment:
        kb = ctx.kb
        p = kb.precompiles[int(site.variant, 16)]
        entry = p.get("chains", {}).get(chain)
        support = entry["support"] if entry else p["assume"]
        confidence = entry.get("confidence", "medium") if entry else "low"
        note = (entry or {}).get("note", "")
        if not note:
            note = {
                "yes": f"{p['name']} is available.",
                "no": f"{p['name']} is not available on {{chain}}: the call succeeds with empty return data instead of reverting.",
                "limited": f"{p['name']} is available on {{chain}} with restrictions.",
                "unknown": f"Could not confirm that {p['name']} ({p['fork']}) is available on {{chain}}. If it is missing, the call succeeds with empty return data.",
            }[support]
        return kb.make(chain, {"severity": _SUPPORT_TO_SEVERITY[support], "confidence": confidence, "note": note})


class KnownAddress(Rule):
    id = "known-address"

    def detect(self, ctx):
        table = ctx.kb.addresses
        # 1. Literal addresses anywhere (state constants, immutables, function bodies).
        for contract, function, node, ir in ctx.irs():
            for v in ir.read:
                value = constant_int(v)
                if value is not None and value > 0xFFFF and value in table:
                    yield self._site(ctx, contract, function, node, value)
        # 2. Small system addresses (0x64, 0x8006, ...) only count when they are called.
        for contract, function, node, value, _how in call_targets(ctx):
            if value in table:
                yield self._site(ctx, contract, function, node, value)

    def _site(self, ctx, contract, function, node, value):
        entry = ctx.kb.addresses[value]
        return ctx.site(
            self.id, contract, function, node,
            f"hardcodes {entry['address']} ({entry['name']})",
            variant=entry["address"],
        )

    def assess(self, ctx, site, chain) -> Assessment:
        kb = ctx.kb
        entry = kb.addresses[int(site.variant, 16)]
        confidence = entry.get("confidence", "medium")
        hint = entry.get("hint", "")
        if entry["on"] == "*":
            if chain in entry.get("missing", []):
                sev = entry.get("missing_severity", "high")
                return kb.make(chain, {"severity": sev, "confidence": confidence, "note": f"Not at this address on {{chain}}. {hint}"})
            return kb.make(chain, {"severity": "none", "confidence": confidence, "note": "Deployed at the same address."})
        if chain in entry["on"]:
            return kb.make(chain, {"severity": "none", "confidence": confidence, "note": "This is the right address on {chain}."})
        return kb.make(chain, {
            "severity": "high",
            "confidence": confidence,
            "note": f"{entry['name']} is not at this address on {{chain}}: high-level calls revert, low-level calls silently succeed. {hint}",
        })
