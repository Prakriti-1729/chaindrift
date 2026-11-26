"""Locating a solc binary without relying on PATH shims."""

from __future__ import annotations

import os
import re
import shutil
import sys
from pathlib import Path


def _version_key(path: Path):
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", path.name)
    return tuple(int(x) for x in m.groups()) if m else (0, 0, 0)


def _solc_select_artifacts() -> list[Path]:
    roots = []
    for env in ("VIRTUAL_ENV",):
        if os.environ.get(env):
            roots.append(Path(os.environ[env]) / ".solc-select" / "artifacts")
    roots.append(Path(sys.prefix) / ".solc-select" / "artifacts")
    roots.append(Path.home() / ".solc-select" / "artifacts")
    found = []
    for root in roots:
        if root.is_dir():
            for d in root.iterdir():
                for cand in (d / d.name, d / f"{d.name}.exe"):
                    if cand.is_file():
                        found.append(cand)
    return sorted(set(found), key=_version_key)


def find_solc(explicit: str | None = None) -> str | None:
    """Resolution order: --solc, $CHAINDRIFT_SOLC, newest solc-select artifact, `solc` on PATH."""
    if explicit:
        return explicit
    if os.environ.get("CHAINDRIFT_SOLC"):
        return os.environ["CHAINDRIFT_SOLC"]
    artifacts = _solc_select_artifacts()
    if artifacts:
        return str(artifacts[-1])
    return shutil.which("solc")
