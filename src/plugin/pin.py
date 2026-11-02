"""Reference tool: the same unresolved subset, with no workspace file, pinned before the task runs."""

from __future__ import annotations

from pathlib import Path

from contract import UnresolvedInput, UnresolvedOutput
from plugin.client import get_client
from plugin.resolve import classify


def pin_unresolved(given: UnresolvedInput, _workspace: Path) -> UnresolvedOutput:
    output, _rows = classify(given, get_client())
    return output
