"""Apply a fix to the partner's own Python.

The running bot may edit files inside its own directory. It may not edit
newserv, the game client, or the file that enforces this boundary.
A change is kept only when the checks pass. Otherwise the file is restored.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

FROZEN_FILES = frozenset({"self_update.py"})
_BLOCKED_PARTS = frozenset({"newserv", "patch-bb", "patch-pc", "client"})


class PatchError(Exception):
    pass


class SelfPatcher:
    def __init__(self, root: Path):
        self.root = root.resolve()

    def resolve(self, relative: str) -> Path:
        raw = relative.replace("\\", "/").strip()
        if not raw or raw.startswith("/") or ":" in raw:
            raise PatchError("path is outside the partner")
        parts = [part for part in raw.split("/") if part not in ("", ".")]
        if any(part == ".." or part.lower() in _BLOCKED_PARTS for part in parts):
            raise PatchError("path is outside the partner")
        path = (self.root.joinpath(*parts)).resolve()
        if path != self.root and self.root not in path.parents:
            raise PatchError("path is outside the partner")
        if path.suffix != ".py":
            raise PatchError("only partner python can be patched")
        if path.name in FROZEN_FILES:
            raise PatchError("that file is the update boundary")
        return path

    def apply(self, relative: str, old: str, new: str, tester) -> str:
        if old == new:
            raise PatchError("patch is empty")
        path = self.resolve(relative)
        original = path.read_text(encoding="utf-8")
        if old not in original:
            raise PatchError("could not find the code to replace")
        updated = original.replace(old, new, 1)
        path.write_text(updated, encoding="utf-8")
        try:
            if not tester():
                raise PatchError("checks failed")
        except Exception:
            path.write_text(original, encoding="utf-8")
            raise
        return f"updated {path.name}"


def run_partner_tests(root: Path) -> bool:
    """Run this package's unit tests. A missing interpreter counts as a failure."""

    python = _python()
    if python is None:
        return False
    result = subprocess.run(
        [python, "-m", "unittest", "discover", "-s", str(root), "-p", "test_*.py"],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _python() -> str | None:
    for name in ("python", "py"):
        found = shutil.which(name)
        if not found:
            continue
        if "WindowsApps" in found:
            continue
        return found
    return None
