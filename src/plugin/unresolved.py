"""The task tool: record which references PubMed cannot match to one record."""

from __future__ import annotations

import json
from pathlib import Path

from contract import UnresolvedInput, UnresolvedOutput
from plugin.client import get_client
from plugin.resolve import classify

RESOLUTION_FILE = "resolution.json"


def unresolved_citations(given: UnresolvedInput, workspace: Path) -> UnresolvedOutput:
    output, rows = classify(given, get_client())
    payload = {"references": rows}
    (workspace / RESOLUTION_FILE).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return output
