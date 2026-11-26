"""Rules about value transfer, gas, deployment and opcodes."""

from __future__ import annotations

import re

from slither.slithir.operations import (
    Binary,
    BinaryType,
    HighLevelCall,
    LowLevelCall,
    NewContract,
    Send,
    SolidityCall,
    Transfer,
)
from slither.slithir.variables import Constant

from ..ir import call_name, function_trackers
from ..models import SEVERITY_RANK, Assessment
from .base import Rule

YUL_CALLS = {"call", "staticcall", "delegatecall", "callcode"}


class TransferSend(Rule):
    id = "transfer-send"

    def detect(self, ctx):
        for contract, function, node, ir in ctx.irs():
            if isinstance(ir, Transfer):
                yield ctx.site(self.id, contract, function, node, "sends native currency with .transfer() (2300 gas stipend)")
            elif isinstance(ir, Send):
                yield ctx.site(self.id, contract, function, node, "sends native currency with .send() (2300 gas stipend)")


class HardcodedGas(Rule):
    id = "hardcoded-gas"
    _CMP = {BinaryType.LESS, BinaryType.GREATER, BinaryType.LESS_EQUAL, BinaryType.GREATER_EQUAL}

    def detect(self, ctx):
        for contract, function in ctx.functions():
            gas_tmps: set[str] = set()
            for node, ir, tracker in function_trackers(function):
                name = call_name(ir)
                if name in ("gasleft", "gas") and ir.lvalue is not None:
                    gas_tmps.add(ir.lvalue.name)
                    continue
                if isinstance(ir, (LowLevelCall, HighLevelCall)) and ir.call_gas is not None:
                    gas = tracker.resolve(ir.call_gas)
                    if gas is not None:
                        yield ctx.site(self.id, contract, function, node, f"forwards a fixed {gas} gas to an external call")
                        continue
                if name in YUL_CALLS and ir.arguments:
                    gas = tracker.resolve(ir.arguments[0])
                    if gas is not None:
                        yield ctx.site(self.id, contract, function, node, f"assembly {name} forwards a fixed {gas} gas")
                        continue
                pair = None
                if isinstance(ir, Binary) and ir.type in self._CMP:
                    pair = (ir.variable_left, ir.variable_right)
                elif name in ("lt", "gt", "slt", "sgt") and len(ir.arguments) == 2:
                    pair = tuple(ir.arguments)
                if pair:
                    for a, b in (pair, pair[::-1]):
                        if getattr(a, "name", None) in gas_tmps and tracker.resolve(b) is not None:
                            yield ctx.site(self.id, contract, function, node, f"compares remaining gas with the constant {tracker.resolve(b)}")
                            break


class Create2Address(Rule):
    id = "create2-address"

    def detect(self, ctx):
        for contract, function in ctx.functions():
            for node, ir, tracker in function_trackers(function):
                name = call_name(ir)
                if name in ("create", "create2"):
                    yield ctx.site(self.id, contract, function, node, f"deploys raw bytecode with assembly {name}()", "raw-create")
                elif name == "abi.encodePacked" and len(ir.arguments) >= 4 and self._is_ff(ir.arguments[0], tracker):
                    yield ctx.site(self.id, contract, function, node, "precomputes a CREATE2 address (keccak256(0xff ++ deployer ++ salt ++ codehash))", "precompute")
                elif isinstance(ir, NewContract) and getattr(ir, "call_salt", None) is not None:
                    yield ctx.site(self.id, contract, function, node, f"deploys {ir.contract_name} with a CREATE2 salt", "salted-new")

    @staticmethod
    def _is_ff(arg, tracker) -> bool:
        if tracker.resolve(arg) == 0xFF:
            return True
        if isinstance(arg, Constant) and isinstance(arg.value, str):
            return arg.value.lower() in ("\xff", "ff", "0xff")
        return False


class Selfdestruct(Rule):
    id = "selfdestruct"

    def detect(self, ctx):
        for contract, function, node, ir in ctx.irs():
            if isinstance(ir, SolidityCall) and call_name(ir) in ("selfdestruct", "suicide"):
                yield ctx.site(self.id, contract, function, node, "calls selfdestruct")


# ----------------------------------------------------------------- bytecode
_LIB_PLACEHOLDER = re.compile(r"__\$[0-9a-fA-F]{34}\$__|__[A-Za-z0-9_:./\-]{36}__")


def _strip_metadata(code: bytes) -> bytes:
    """Drop solc's CBOR metadata trailer (its length is stored in the last two bytes)."""
    if len(code) < 2:
        return code
    meta_len = int.from_bytes(code[-2:], "big")
    if 0 < meta_len + 2 <= len(code) and code[-meta_len - 2] in (0xA1, 0xA2, 0xA3, 0xA4):
        return code[: -meta_len - 2]
    return code


def scan_opcodes(hex_code: str, wanted: dict[int, str]) -> dict[str, int]:
    """Count occurrences of the `wanted` opcodes, skipping PUSH immediates."""
    hex_code = hex_code[2:] if hex_code.startswith("0x") else hex_code
    hex_code = _LIB_PLACEHOLDER.sub("00" * 20, hex_code)
    try:
        code = _strip_metadata(bytes.fromhex(hex_code))
    except ValueError:
        return {}
    counts: dict[str, int] = {}
    i = 0
    while i < len(code):
        op = code[i]
        if op in wanted:
            counts[wanted[op]] = counts.get(wanted[op], 0) + 1
        i += 1 + (op - 0x5F if 0x60 <= op <= 0x7F else 0)
    return counts


class OpcodeSupport(Rule):
    id = "opcode-support"

    def detect(self, ctx):
        wanted = {op["byte"]: name for name, op in ctx.kb.opcodes.items()}
        for contract, init, runtime in ctx.bytecodes():
            counts = scan_opcodes(runtime, wanted)
            for name, n in scan_opcodes(init, wanted).items():
                counts.setdefault(name, n)
            if not counts:
                continue
            names = sorted(counts)
            listed = ", ".join(f"{n} ({ctx.kb.opcodes[n]['fork']}, EIP-{ctx.kb.opcodes[n]['eip']})" for n in names)
            # One finding per contract; the variant carries the opcode list for assess().
            yield ctx.site(self.id, contract, None, contract, f"bytecode uses {listed}", variant=",".join(names))

    def assess(self, ctx, site, chain) -> Assessment:
        kb = ctx.kb
        if chain in kb.vm_notes:
            return kb.make(chain, kb.vm_notes[chain])
        parts = []
        for name in site.variant.split(","):
            op = kb.opcodes[name]
            a = kb.make(chain, op.get("chains", {}).get(chain, op["default"]))
            if a.severity != "none":
                parts.append((name, a))
        if not parts:
            return Assessment(chain, "none", "medium", "All of these opcodes are supported.")
        worst = max(parts, key=lambda p: SEVERITY_RANK[p[1].severity])[1]
        note = " ".join(f"{name}: {a.note}" for name, a in parts)
        conf = min((a.confidence for _, a in parts), key=["low", "medium", "high"].index)
        return Assessment(chain, worst.severity, conf, note)
