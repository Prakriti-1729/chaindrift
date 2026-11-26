"""Knowledge-base integrity, bytecode scanning, reporters and CLI."""

from __future__ import annotations

import json
from pathlib import Path

from chaindrift.cli import main
from chaindrift.engine import analyze
from chaindrift.knowledge import load_knowledge
from chaindrift.report import render_html, render_json, render_sarif, render_text
from chaindrift.rules import ALL_RULES
from chaindrift.rules.execution import scan_opcodes

CONTRACTS = Path(__file__).parent / "contracts"


def test_every_rule_has_metadata():
    kb = load_knowledge()
    for rule in ALL_RULES:
        meta = kb.rules[rule.id]
        assert meta["title"] and meta["description"] and meta["fix"]


def test_knowledge_base_chains():
    kb = load_knowledge()
    assert {"ethereum", "arbitrum", "optimism", "base", "zksync"} <= set(kb.chains)
    assert kb.chain_by_numeric_id[42161].id == "arbitrum"


def test_scan_skips_push_immediates():
    wanted = {0x5F: "PUSH0", 0x5C: "TLOAD"}
    # PUSH2 0x5f5c (data, must be ignored), then PUSH0, then TLOAD
    assert scan_opcodes("615f5c5f5c", wanted) == {"PUSH0": 1, "TLOAD": 1}
    # PUSH32 swallows 32 bytes of 0x5f
    assert scan_opcodes("0x7f" + "5f" * 32, wanted) == {}


def test_scan_strips_metadata():
    wanted = {0x5F: "PUSH0"}
    meta = bytes([0xA2]) + b"\x5f" * 5
    code = b"\x00" + meta + len(meta).to_bytes(2, "big")
    assert scan_opcodes(code.hex(), wanted) == {}


def test_reporters_render():
    report = analyze(CONTRACTS / "Precompile.sol")
    data = json.loads(render_json(report))
    assert data["tool"] == "chaindrift" and data["findings"]
    sarif = json.loads(render_sarif(report))
    assert sarif["version"] == "2.1.0" and sarif["runs"][0]["results"]
    html = render_html(report)
    assert "Divergence matrix" in html and "P256VERIFY" in html
    assert "<script>" in html and "</html>" in html
    text = render_text(report, color=False)
    assert "P256VERIFY" in text


def test_html_escapes_contract_strings():
    report = analyze(CONTRACTS / "ChainIdReplay.sol", rules=["chainid-replay"])
    html = render_html(report)
    # the EIP-712 type string from the contract ends up escaped, never as raw markup
    assert "EIP712Domain(string name,string version,address verifyingContract)" in html


def test_cli_fail_on_exit_code(tmp_path, capsys):
    out = tmp_path / "r.json"
    code = main(["scan", str(CONTRACTS / "Selfdestruct.sol"), "-o", str(out), "--fail-on", "high"])
    assert code == 1
    assert json.loads(out.read_text(encoding="utf-8"))["findings"]
    code = main(["scan", str(CONTRACTS / "Clean.sol"), "--rules", "selfdestruct", "--fail-on", "high"])
    assert code == 0


def test_cli_lists(capsys):
    assert main(["chains"]) == 0
    assert "Arbitrum One" in capsys.readouterr().out
    assert main(["rules"]) == 0
    assert "chainid-replay" in capsys.readouterr().out
