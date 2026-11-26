"""Small helpers on top of Slither's IR (SlithIR).

Slither lowers both Solidity and inline assembly (Yul) into the same IR:
  * Solidity globals like `block.number` show up in `node.solidity_variables_read`
  * Yul builtins like `number()` or `staticcall(...)` show up as SolidityCall operations
These helpers hide that difference from the rules.
"""

from __future__ import annotations

import re

from slither.core.declarations.solidity_variables import SolidityVariable
from slither.core.solidity_types import ElementaryType
from slither.core.variables.state_variable import StateVariable
from slither.slithir.operations import Assignment, SolidityCall, TypeConversion
from slither.slithir.variables import Constant

_INT_IN_EXPR = re.compile(r"^(?:address\()?\s*(0x[0-9a-fA-F]+|\d+)\s*\)?$")


def call_name(ir) -> str | None:
    """Base name of a SolidityCall: 'staticcall(uint256,...)' -> 'staticcall'."""
    if isinstance(ir, SolidityCall):
        return ir.function.name.split("(", 1)[0]
    return None


def constant_int(v) -> int | None:
    """Integer value of a Slither Constant (addresses included), else None."""
    if not isinstance(v, Constant):
        return None
    val = v.value
    if isinstance(val, bool):
        return None
    if isinstance(val, int):
        return val
    if isinstance(val, str):
        s = val.strip()
        try:
            return int(s, 16) if s.lower().startswith("0x") else int(s)
        except ValueError:
            return None
    return None


def is_solidity_var(v, *names: str) -> bool:
    return isinstance(v, SolidityVariable) and v.name in names


def _is_address_type(t) -> bool:
    return isinstance(t, ElementaryType) and t.name in ("address", "address payable")


class ConstTracker:
    """Tracks which IR variables in a function hold a compile-time integer.

    Handles chains like `TMP_1 = CONVERT 256 to address; TMP_2 = CONVERT TMP_1 to IFoo`
    and constant state variables (`address constant ORACLE = 0x...`).
    """

    def __init__(self) -> None:
        self.values: dict[str, int] = {}
        self.address_like: set[str] = set()

    def feed(self, ir) -> None:
        if isinstance(ir, TypeConversion) and ir.lvalue is not None:
            val = self.resolve(ir.variable)
            if val is not None:
                self.values[ir.lvalue.name] = val
                # A conversion to `address` or to a contract/interface type means
                # "this number is used as an address".
                t = ir.type
                if _is_address_type(t) or not isinstance(t, ElementaryType):
                    self.address_like.add(ir.lvalue.name)
                elif ir.variable is not None and getattr(ir.variable, "name", None) in self.address_like:
                    self.address_like.add(ir.lvalue.name)
        elif isinstance(ir, Assignment) and ir.lvalue is not None:
            val = self.resolve(ir.rvalue)
            if val is not None and not isinstance(ir.lvalue, StateVariable):
                self.values[ir.lvalue.name] = val

    def resolve(self, v) -> int | None:
        if v is None:
            return None
        c = constant_int(v)
        if c is not None:
            return c
        if isinstance(v, StateVariable) and v.is_constant and v.expression is not None:
            m = _INT_IN_EXPR.match(str(v.expression))
            if m:
                return int(m.group(1), 0)
            return None
        name = getattr(v, "name", None)
        if name is not None and name in self.values:
            return self.values[name]
        return None


def function_trackers(function):
    """Yield (node, ir, tracker) for every IR in a function, with the tracker updated
    up to (and including) the current IR."""
    tracker = ConstTracker()
    for node in function.nodes:
        for ir in node.irs:
            tracker.feed(ir)
            yield node, ir, tracker
