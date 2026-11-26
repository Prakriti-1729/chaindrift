"""Rules about block/tx globals whose meaning differs per chain."""

from __future__ import annotations

import re

from slither.slithir.operations import Binary, BinaryType, SolidityCall

from ..ir import call_name, function_trackers, is_solidity_var
from .base import Rule, global_read

_BLOCK_TIME_NAME = re.compile(
    r"blocks?_?per_?(year|day|hour|minute|epoch|week|month)|block_?time|blocks?_?in_?(a_)?(year|day)",
    re.IGNORECASE,
)


class GlobalReadRule(Rule):
    solidity: set[str] = set()
    yul: set[str] = set()

    def detect(self, ctx):
        for contract, function, node in ctx.nodes():
            hit = global_read(node, self.solidity, self.yul)
            if hit:
                yield ctx.site(self.id, contract, function, node, f"reads {hit}")


class BlockNumber(GlobalReadRule):
    id = "block-number"
    solidity = {"block.number"}
    yul = {"number"}

    def detect(self, ctx):
        yield from super().detect(ctx)
        # Constants such as BLOCKS_PER_YEAR bake Ethereum's block time into the code.
        for contract in ctx.contracts:
            for var in contract.state_variables_declared:
                if (var.is_constant or var.is_immutable) and _BLOCK_TIME_NAME.search(var.name):
                    yield ctx.site(
                        self.id, contract, None, var,
                        f"constant {var.name} encodes a block-time assumption",
                        variant="constant",
                    )


class Prevrandao(GlobalReadRule):
    id = "prevrandao"
    solidity = {"block.prevrandao", "block.difficulty"}
    yul = {"prevrandao", "difficulty"}


class GasPrice(GlobalReadRule):
    id = "gas-price"
    solidity = {"tx.gasprice", "block.basefee"}
    yul = {"gasprice", "basefee"}


class ChainGatedLogic(Rule):
    """`block.chainid == 1`-style branches."""

    id = "chain-gated-logic"
    _EQ = {BinaryType.EQUAL, BinaryType.NOT_EQUAL}

    def detect(self, ctx):
        for contract, function in ctx.functions():
            chainid_tmps: set[str] = set()
            for node, ir, tracker in function_trackers(function):
                if isinstance(ir, SolidityCall) and call_name(ir) == "chainid" and ir.lvalue:
                    chainid_tmps.add(ir.lvalue.name)
                    continue
                pair = None
                if isinstance(ir, Binary) and ir.type in self._EQ:
                    pair = (ir.variable_left, ir.variable_right)
                elif isinstance(ir, SolidityCall) and call_name(ir) == "eq" and len(ir.arguments) == 2:
                    pair = tuple(ir.arguments)
                if not pair:
                    continue
                for a, b in (pair, pair[::-1]):
                    is_chainid = is_solidity_var(a, "block.chainid") or getattr(a, "name", None) in chainid_tmps
                    value = tracker.resolve(b)
                    if is_chainid and value is not None:
                        known = ctx.kb.chain_by_numeric_id.get(value)
                        label = f" ({known.name})" if known else ""
                        yield ctx.site(self.id, contract, function, node, f"compares block.chainid with {value}{label}")
                        break


class EoaCheck(Rule):
    id = "eoa-check"
    _EQ = {BinaryType.EQUAL, BinaryType.NOT_EQUAL}
    _CODE_CALLS = {"code", "codehash", "extcodesize", "extcodehash"}

    def detect(self, ctx):
        for contract, function, node in ctx.nodes():
            expr = str(node.expression) if node.expression is not None else ""
            for ir in node.irs:
                if isinstance(ir, Binary) and ir.type in self._EQ:
                    sides = {getattr(ir.variable_left, "name", None), getattr(ir.variable_right, "name", None)}
                    if sides == {"tx.origin", "msg.sender"}:
                        yield ctx.site(self.id, contract, function, node, "tx.origin == msg.sender used as an EOA check", "tx-origin")
                        break
                name = call_name(ir)
                if name in self._CODE_CALLS:
                    # address(this).code.length is the standard "am I in my constructor?" idiom: not an EOA check.
                    if "address(this).code" in expr or "extcodesize(address()" in expr:
                        continue
                    yield ctx.site(self.id, contract, function, node, f"inspects account code ({name}) to tell EOAs from contracts", "code-size")
                    break
                fn = getattr(ir, "function", None)
                if fn is not None and getattr(fn, "name", None) == "isContract":
                    yield ctx.site(self.id, contract, function, node, "calls isContract() to tell EOAs from contracts", "is-contract")
                    break
