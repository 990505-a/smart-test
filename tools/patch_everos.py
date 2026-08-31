"""Idempotent site-packages patch for the everos 1.2.3 / everalgo 0.4.0 skew.

everos 1.2.3 pins everalgo-agent-memory==0.4.0 while a sibling everalgo dist
ships ``everalgo/boundary/chat.py`` whose ``DetectionResult`` grew a required
``should_wait`` field. ``everalgo/agent_memory/boundary.py`` (0.4.0) still
constructs it with two arguments, so every ``POST /api/v2/memory/add`` in
agent mode dies with::

    TypeError: DetectionResult.__new__() missing 1 required positional
    argument: 'should_wait'

The agent-mode caller (everos/service/_boundary.py) only reads ``cells`` and
``tail``, so ``should_wait=None`` ("no wait recommendation") is semantically
safe. Run this before starting the EverOS server; it no-ops once upstream
ships a fixed everalgo (constructor pattern won't match).

Usage:  python tools/patch_everos.py   (exit 0 = patched or already patched)
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_FIXES = {
    # old fragment -> patched fragment (both call sites in agent_memory/boundary.py)
    "DetectionResult(cells=[], tail=list(items))": (
        "DetectionResult(cells=[], tail=list(items), should_wait=None)"
    ),
    "DetectionResult(cells=remapped_cells, tail=tail)": (
        "DetectionResult(cells=remapped_cells, tail=tail, should_wait=None)"
    ),
}


def _target_file() -> Path:
    spec = importlib.util.find_spec("everalgo")
    if spec is None or spec.submodule_search_locations is None:
        raise SystemExit("everalgo is not installed in this interpreter")
    return Path(list(spec.submodule_search_locations)[0]) / "agent_memory" / "boundary.py"


def main() -> int:
    path = _target_file()
    text = path.read_text(encoding="utf-8")
    patched = text
    applied = 0
    for old, new in _FIXES.items():
        if new in patched:
            continue  # already patched
        if old in patched:
            patched = patched.replace(old, new)
            applied += 1
    if applied:
        path.write_text(patched, encoding="utf-8")
        print(f"patched {applied} call site(s) in {path}")
    elif any(new in text for new in _FIXES.values()):
        print(f"already patched: {path}")
    else:
        # Neither pattern present — upstream layout changed (fixed or refactored).
        print(f"pattern not found (upstream may have fixed it): {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
