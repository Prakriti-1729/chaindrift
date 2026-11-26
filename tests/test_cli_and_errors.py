"""Error handling, CLI behaviour and helper units. Added after an end-to-end CLI run found
that a missing target, an empty folder or a broken contract could let CI pass silently."""

from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path

import pytest

from chaindrift.cli import main
from chaindrift.engine import analyze
from chaindrift.knowledge import KnowledgeBase, load_knowledge
from chaindrift.models import Assessment, Finding, Site
from chaindrift.report.common import grouped_assessments
from chaindrift.solc import find_solc

CONTRACTS = Path(__file__).parent / "contracts"
BROKEN = "pragma solidity ^0.8.20;\ncontract Broken { function f( }\n"


# --------------------------------------------------------------------------- bad input

def test_missing_target_is_an_error():
    with pytest.raises(ValueError, match="Target not found"):
        analyze("does/not/exist.sol")
    assert main(["scan", "does/not/exist.sol"]) == 2


def test_empty_folder_is_an_error(tmp_path):
    with pytest.raises(ValueError, match="No Solidity files"):
        analyze(tmp_path)
    assert main(["scan", str(tmp_path)]) == 2


def test_unknown_rule_has_a_helpful_message(capsys):
    with pytest.raises(ValueError, match="Unknown rule.*nosuchrule.*chaindrift rules"):
        analyze(CONTRACTS / "Clean.sol", rules=["nosuchrule"])
    assert main(["scan", str(CONTRACTS / "Clean.sol"), "--rules", "nosuchrule"]) == 2
    assert "Unknown rule" in capsys.readouterr().err


def test_broken_contract_is_reported_and_fails(tmp_path, capsys):
    (tmp_path / "Broken.sol").write_text(BROKEN)
    report = analyze(tmp_path / "Broken.sol")
    assert report.errors and not report.contracts
    assert main(["scan", str(tmp_path / "Broken.sol")]) == 2
    assert "failed to compile" in capsys.readouterr().err


def test_partial_failure_still_reports_good_files_but_exits_2(tmp_path):
    (tmp_path / "Broken.sol").write_text(BROKEN)
    shutil.copy(CONTRACTS / "Selfdestruct.sol", tmp_path)
    report = analyze(tmp_path, rules=["selfdestruct"])
    assert len(report.errors) == 1
    assert [f.site.rule_id for f in report.findings] == ["selfdestruct"]
    # compile errors win over --fail-on: CI must not pass with unanalysed code
    assert main(["scan", str(tmp_path), "--rules", "selfdestruct"]) == 2


def test_dependency_folders_are_skipped(tmp_path):
    (tmp_path / "lib").mkdir()
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "lib" / "Broken.sol").write_text(BROKEN)
    (tmp_path / "node_modules" / "Broken.sol").write_text(BROKEN)
    shutil.copy(CONTRACTS / "Selfdestruct.sol", tmp_path)
    report = analyze(tmp_path, rules=["selfdestruct"])
    assert report.errors == []
    assert report.contracts == ["Killable"]


# --------------------------------------------------------------------------- compiler options

def test_evm_version_changes_opcode_findings():
    default = analyze(CONTRACTS / "Selfdestruct.sol", rules=["opcode-support"])
    assert any("PUSH0" in f.site.detail for f in default.findings)
    paris = analyze(CONTRACTS / "Selfdestruct.sol", rules=["opcode-support"], solc_args="--evm-version paris")
    assert paris.errors == [] and paris.findings == []  # pre-Shanghai: no PUSH0 emitted


def test_find_solc_precedence(monkeypatch):
    monkeypatch.setenv("CHAINDRIFT_SOLC", "/from/env/solc")
    assert find_solc("/explicit/solc") == "/explicit/solc"
    assert find_solc() == "/from/env/solc"
    monkeypatch.delenv("CHAINDRIFT_SOLC")
    assert find_solc() is not None  # the test environment has a solc-select artifact or solc on PATH


# --------------------------------------------------------------------------- CLI output formats

@pytest.mark.parametrize("suffix,check", [
    (".json", lambda s: json.loads(s)["tool"] == "chaindrift"),
    (".sarif", lambda s: json.loads(s)["version"] == "2.1.0"),
    (".html", lambda s: s.startswith("<!DOCTYPE html>")),
    (".txt", lambda s: s.startswith("ChainDrift - cross-chain divergence report")),
])
def test_output_format_inferred_from_extension(tmp_path, suffix, check):
    out = tmp_path / f"report{suffix}"
    assert main(["scan", str(CONTRACTS / "TransferSend.sol"), "-o", str(out)]) == 0
    assert check(out.read_text(encoding="utf-8"))


def test_text_file_output_has_no_ansi_colours(tmp_path):
    out = tmp_path / "r.txt"
    main(["scan", str(CONTRACTS / "TransferSend.sol"), "-o", str(out)])
    assert "\x1b[" not in out.read_text(encoding="utf-8")


def test_sarif_levels_follow_severity(tmp_path):
    out = tmp_path / "r.sarif"
    main(["scan", str(CONTRACTS / "ChainGated.sol"), "--rules", "chain-gated-logic,selfdestruct", "-o", str(out)])
    results = json.loads(out.read_text(encoding="utf-8"))["runs"][0]["results"]
    assert {r["level"] for r in results} == {"note"}  # chain-gated-logic is info -> note


def test_fail_on_threshold(tmp_path):
    target = str(CONTRACTS / "ChainGated.sol")
    assert main(["scan", target, "--rules", "chain-gated-logic", "--fail-on", "info", "-o", str(tmp_path / "a.json")]) == 1
    assert main(["scan", target, "--rules", "chain-gated-logic", "--fail-on", "low", "-o", str(tmp_path / "b.json")]) == 0


# --------------------------------------------------------------------------- units

def test_knowledge_base_rejects_bad_data():
    kb = load_knowledge()
    broken = copy.copy(kb)
    broken.rules = copy.deepcopy(kb.rules)
    broken.rules["selfdestruct"]["chains"]["zksync"]["severity"] = "catastrophic"
    broken.rules["selfdestruct"]["chains"]["solana"] = {"severity": "high", "note": ""}
    with pytest.raises(ValueError) as exc:
        KnowledgeBase._validate(broken)
    assert "bad severity" in str(exc.value) and "unknown chain 'solana'" in str(exc.value)


def test_assess_rule_precedence():
    kb = load_knowledge()
    # variant + chain beats everything
    assert kb.assess_rule("create2-address", "zksync", "salted-new").severity == "medium"
    # unknown variant falls back to the rule's chain entry
    assert kb.assess_rule("create2-address", "zksync", "precompute").severity == "high"
    # chain without an entry falls back to the rule default, with {chain} rendered
    a = kb.assess_rule("prevrandao", "linea")
    assert a.severity == "high" and "Linea" in a.note and "{chain}" not in a.note


def test_grouped_assessments_merges_identical_notes():
    kb = load_knowledge()
    site = Site("x", "C", None, "f.sol", 1, "", "")
    f = Finding(site, "t", "d", "fix", [])
    for chain in ("arbitrum", "base", "scroll"):
        name = kb.chains[chain].name
        f.assessments[chain] = Assessment(chain, "high", "high", f"Broken on {name}.")
    f.assessments["zksync"] = Assessment("zksync", "medium", "high", "Different.")
    f.assessments["ethereum"] = Assessment("ethereum", "none", "high", "")
    groups = grouped_assessments(f, kb)
    assert groups[0] == (["Arbitrum One", "Base", "Scroll"], "high", "high", "Broken on these chains.")
    assert groups[1][0] == ["ZKsync Era"]
    assert len(groups) == 2  # 'none' is never listed
