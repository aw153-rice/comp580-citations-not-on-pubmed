"""Read resolution.json. The unresolved subset is checked against these rows."""

import json
from pathlib import Path

from .identity import PMID, reference_key

FILE_NAME = "resolution.json"
STATUSES = frozenset({"resolved", "not_found", "ambiguous"})


def load_rows(workspace, references):
    """Return ("ok", rows), or ("missing"|"malformed", message)."""
    path = Path(workspace) / FILE_NAME
    if not path.is_file():
        return ("missing", "resolution.json is missing")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return ("malformed", "resolution.json is not JSON")
    if type(data) is not dict or type(data.get("references")) is not list:
        return ("malformed", "resolution.json has no references list")
    rows = data["references"]
    if len(rows) != len(references):
        return ("malformed", "resolution.json row count does not match the input")
    parsed = []
    for reference, row in zip(references, rows):
        problem = row_problem(reference, row)
        if problem:
            return problem
        parsed.append({"kind": row["kind"], "value": row["value"], "status": row["status"], "pmid": row["pmid"]})
    problem = duplicate_problem(references, parsed)
    if problem:
        return ("malformed", problem)
    return ("ok", parsed)


def row_problem(reference, row):
    if type(row) is not dict:
        return ("malformed", "resolution.json has a reference that is not an object")
    if row.get("kind") != reference.kind.value or row.get("value") != reference.value:
        return ("malformed", "resolution.json row does not match the input")
    status = row.get("status")
    pmid = row.get("pmid")
    if type(status) is not str or status not in STATUSES:
        return ("malformed", "resolution.json has an invalid status")
    if status == "resolved":
        if type(pmid) is not str or PMID.fullmatch(pmid) is None:
            return ("malformed", "resolution.json marks a reference resolved without a pmid")
    elif pmid is not None:
        return ("malformed", "resolution.json gives a pmid to an unresolved reference")
    return None


def duplicate_problem(references, rows):
    seen = {}
    for reference, row in zip(references, rows):
        key = reference_key(reference)
        marker = (row["status"], row["pmid"])
        if key in seen and seen[key] != marker:
            return "resolution.json disagrees on a repeated reference"
        seen[key] = marker
    return None
