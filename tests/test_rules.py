"""End-to-end tests: compile each fixture contract with Slither and check what every rule reports."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pytest

from chaindrift.engine import analyze
from chaindrift.rules import ALL_RULES

CONTRACTS = Path(__file__).parent / "contracts"
NON_OPCODE_RULES = tuple(r.id for r in ALL_RULES if r.id != "opcode-support")


@lru_cache(maxsize=None)
def scan(name: str):
    report = analyze(CONTRACTS / name)
    assert not report.errors, report.errors
    return report


def found(name: str, rule: str):
    return [f for f in scan(name).findings if f.site.rule_id == rule]


def sev(finding, chain: str) -> str:
    return finding.assessments[chain].severity


# --------------------------------------------------------------------------- per rule

def test_block_number():
    fs = found("BlockNumber.sol", "block-number")
    assert len(fs) == 4  # constant + constructor + vested() + assembly number()
    assert {f.site.variant for f in fs} == {None, "constant"}
    assert any("assembly" in f.site.detail for f in fs)
    for f in fs:
        assert sev(f, "arbitrum") == "high"
        assert sev(f, "ethereum") == "none"
    # block time is interpolated into the note
    assert "2s" in fs[0].assessments["optimism"].note


def test_prevrandao():
    fs = found("Prevrandao.sol", "prevrandao")
    assert len(fs) == 2
    for f in fs:
        assert sev(f, "arbitrum") == "high"
        assert "constant 1" in f.assessments["arbitrum"].note
        assert sev(f, "ethereum") == "medium"


def test_transfer_send():
    fs = found("TransferSend.sol", "transfer-send")
    assert len(fs) == 2
    for f in fs:
        assert sev(f, "zksync") == "high"
        assert sev(f, "ethereum") == "low"


def test_create2():
    fs = found("Create2.sol", "create2-address")
    assert {f.site.variant for f in fs} == {"precompute", "raw-create", "salted-new"}
    by_variant = {f.site.variant: f for f in fs}
    assert sev(by_variant["precompute"], "zksync") == "high"
    assert sev(by_variant["salted-new"], "zksync") == "medium"
    for f in fs:
        assert f.affected_chains == ["zksync"]


def test_selfdestruct():
    (f,) = found("Selfdestruct.sol", "selfdestruct")
    assert sev(f, "zksync") == "high"
    assert sev(f, "scroll") == "high"
    assert sev(f, "ethereum") == "medium"


def test_hardcoded_gas():
    fs = found("HardcodedGas.sol", "hardcoded-gas")
    details = " ".join(f.site.detail for f in fs)
    assert len(fs) == 4
    for gas in ("50000", "30000", "100000", "25000"):
        assert gas in details
    assert all(sev(f, "zksync") == "high" and sev(f, "ethereum") == "none" for f in fs)


def test_gas_price():
    fs = found("GasPrice.sol", "gas-price")
    assert len(fs) == 2
    assert all(sev(f, "optimism") == "medium" for f in fs)


def test_eoa_check_skips_constructor_idiom():
    fs = found("EoaCheck.sol", "eoa-check")
    assert {f.site.variant for f in fs} == {"tx-origin", "code-size"}
    assert all(f.site.function != "initializing()" for f in fs)
    assert all(sev(f, "ethereum") == "medium" for f in fs)


def test_chainid_replay():
    fs = found("ChainIdReplay.sol", "chainid-replay")
    by_contract = {f.site.contract: f for f in fs}
    assert set(by_contract) == {"NoChainIdPermit", "CachedPermit"}  # GoodPermit is correct
    assert by_contract["NoChainIdPermit"].site.variant == "no-chainid"
    assert sev(by_contract["NoChainIdPermit"], "base") == "high"
    assert by_contract["CachedPermit"].site.variant == "cached"
    assert sev(by_contract["CachedPermit"], "base") == "medium"


def test_chain_gated_logic():
    fs = found("ChainGated.sol", "chain-gated-logic")
    assert len(fs) == 2
    assert any("Arbitrum One" in f.site.detail for f in fs)
    assert all(f.severity == "info" for f in fs)


def test_precompiles():
    fs = found("Precompile.sol", "precompile")
    variants = sorted(f.site.variant for f in fs)
    assert variants == ["0x100", "0x100", "0x3", "0x5"]  # SENTINEL = address(0x1) is not a call
    by_variant = {f.site.variant: f for f in fs}
    assert sev(by_variant["0x3"], "zksync") == "high"
    assert sev(by_variant["0x5"], "scroll") == "medium"
    assert sev(by_variant["0x100"], "arbitrum") == "none"
    assert sev(by_variant["0x100"], "linea") == "check"


def test_known_addresses():
    fs = {f.site.variant.lower(): f for f in found("KnownAddress.sol", "known-address")}
    weth = fs["0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"]
    assert sev(weth, "ethereum") == "none" and sev(weth, "arbitrum") == "high"
    l1block = fs["0x4200000000000000000000000000000000000015"]
    assert sev(l1block, "base") == "none" and sev(l1block, "ethereum") == "high"
    arbsys = fs["0x0000000000000000000000000000000000000064"]
    assert sev(arbsys, "arbitrum") == "none" and sev(arbsys, "optimism") == "high"
    multicall = fs["0xca11bde05977b3631167028862be2a173976ca11"]
    assert multicall.affected_chains == ["zksync"]


def test_opcodes_are_grouped_per_contract():
    (f,) = found("Opcodes.sol", "opcode-support")
    ops = set(f.site.variant.split(","))
    assert {"TLOAD", "TSTORE", "PUSH0"} <= ops
    assert sev(f, "ethereum") == "none"
    assert sev(f, "arbitrum") == "none"
    assert sev(f, "linea") == "check"
    assert sev(f, "zksync") == "info"


def test_clean_contract_has_no_divergence():
    report = analyze(CONTRACTS / "Clean.sol", rules=list(NON_OPCODE_RULES))
    assert report.findings == [], [f.site for f in report.findings]


# --------------------------------------------------------------------------- engine options

def test_chain_selection_filters_findings():
    # transfer-send is "low" on Ethereum/Arbitrum and only high on ZKsync
    report = analyze(CONTRACTS / "TransferSend.sol", chains=["ethereum", "arbitrum"], rules=["transfer-send"])
    assert report.chains == ["ethereum", "arbitrum"]
    assert all(f.severity == "low" for f in report.findings)
    # create2 diverges only on ZKsync: no findings when ZKsync is not a target
    report = analyze(CONTRACTS / "Create2.sol", chains=["ethereum", "base"], rules=["create2-address"])
    assert report.findings == []


def test_min_severity():
    report = analyze(CONTRACTS / "ChainGated.sol", rules=["chain-gated-logic"], min_severity="low")
    assert report.findings == []


def test_unknown_chain_is_rejected():
    with pytest.raises(ValueError, match="Unknown chain"):
        analyze(CONTRACTS / "Clean.sol", chains=["solana"])


def test_directory_scan_covers_all_files():
    report = analyze(CONTRACTS, rules=["transfer-send", "selfdestruct"])
    rules = {f.site.rule_id for f in report.findings}
    assert rules == {"transfer-send", "selfdestruct"}
    assert "Payouts" in report.contracts and "Killable" in report.contracts
