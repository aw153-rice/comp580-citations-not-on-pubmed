"""Resolve DOIs with ESearch and bibliographic citations with ECitMatch."""

from __future__ import annotations

import os
import re

from contract import ReferenceKind, UnresolvedInput, UnresolvedOutput
from plugin.client import ECITMATCH_URL, ESEARCH_URL, TOOL_NAME

MAX_REFERENCES = 30
DOI_MAX = 200
CITATION_MAX = 300
JOURNAL_MAX = 150
YEAR_MIN = 1700
YEAR_MAX = 2100
PMID = re.compile(r"^[1-9][0-9]{0,8}$")
DOI = re.compile(r"^10\.\d{4,9}/\S+$")
VOLUME = re.compile(r"^[A-Za-z0-9]{1,16}$")
PAGE = re.compile(r"^[A-Za-z0-9]{1,16}$")
AUTHOR = re.compile(r"^[A-Za-z][A-Za-z .'\-]{0,79}$")
JOURNAL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 .,&:'()/\-]{0,149}$")
MULTI_PMID = re.compile(r"^[1-9][0-9]{0,8}(?:[\s,;]+[1-9][0-9]{0,8})+$")
UNRESOLVED = frozenset({"not_found", "ambiguous"})


def reference_key(reference) -> tuple:
    kind = reference.kind.value
    if kind == ReferenceKind.DOI.value:
        return (kind, reference.value.casefold())
    journal, year, volume, page, author = citation_fields(reference.value)
    return (kind, journal.casefold(), year, volume.casefold(), page.casefold(), author.casefold())


def citation_fields(value: str) -> tuple[str, str, str, str, str]:
    journal, year, volume, page, author = value.split("|")
    return (" ".join(journal.split()), year.strip(), volume.strip(), page.strip(), " ".join(author.split()))


def classify(given: UnresolvedInput, client) -> tuple[UnresolvedOutput, list[dict]]:
    check_references(given.references)
    found = lookup(given.references, client)
    rows = []
    unresolved = []
    seen: set[tuple] = set()
    for reference in given.references:
        key = reference_key(reference)
        status, pmid = found[key]
        rows.append({"kind": reference.kind.value, "value": reference.value, "status": status, "pmid": pmid})
        if status in UNRESOLVED and key not in seen:
            seen.add(key)
            unresolved.append(reference)
    return UnresolvedOutput(unresolved=unresolved), rows


def check_references(references) -> None:
    if len(references) > MAX_REFERENCES:
        raise ValueError(f"references has more than {MAX_REFERENCES} items")
    for reference in references:
        problem = reference_problem(reference)
        if problem:
            raise ValueError(problem)


def reference_problem(reference) -> str | None:
    kind = reference.kind.value
    raw = reference.value
    if kind == ReferenceKind.DOI.value:
        return doi_problem(raw)
    if kind == ReferenceKind.CITATION.value:
        return citation_problem(raw)
    return "kind is not doi or citation"


def doi_problem(raw: str) -> str | None:
    if raw.strip() == "":
        return "doi is empty"
    if len(raw) > DOI_MAX:
        return f"doi is longer than {DOI_MAX} characters"
    if any(ord(char) < 32 or ord(char) == 127 or ord(char) > 127 for char in raw):
        return "doi contains a character a DOI cannot contain"
    if DOI.fullmatch(raw) is None or any(char in raw for char in "\"[]"):
        return "doi is not a DOI"
    return None


def citation_problem(raw: str) -> str | None:
    if raw.strip() == "":
        return "citation is empty"
    if len(raw) > CITATION_MAX:
        return f"citation is longer than {CITATION_MAX} characters"
    if any(ord(char) < 32 or ord(char) == 127 or ord(char) > 127 for char in raw):
        return "citation contains a character the citation matcher cannot accept"
    pieces = raw.split("|")
    if len(pieces) != 5:
        return "citation is not journal|year|volume|first_page|author"
    journal, year, volume, page, author = citation_fields(raw)
    return journal_problem(journal) or year_problem(year) or volume_problem(volume) or page_problem(page) or author_problem(author)


def journal_problem(journal: str) -> str | None:
    if journal == "":
        return "journal is empty"
    if not any(char.isalpha() for char in journal):
        return "journal has no letters"
    if len(journal) > JOURNAL_MAX:
        return f"journal is longer than {JOURNAL_MAX} characters"
    if JOURNAL.fullmatch(journal) is None:
        return "journal has a character the citation matcher cannot accept"
    return None


def year_problem(year: str) -> str | None:
    if year == "":
        return "year is empty"
    if len(year) != 4 or not year.isdigit() or not YEAR_MIN <= int(year) <= YEAR_MAX:
        return f"year is not a year from {YEAR_MIN} through {YEAR_MAX}"
    return None


def volume_problem(volume: str) -> str | None:
    if volume == "":
        return "volume is empty"
    if VOLUME.fullmatch(volume) is None:
        return "volume is not a volume"
    return None


def page_problem(page: str) -> str | None:
    if page == "":
        return "first page is empty"
    if PAGE.fullmatch(page) is None:
        return "first page is not a page"
    return None


def author_problem(author: str) -> str | None:
    if author == "":
        return "author is empty"
    if AUTHOR.fullmatch(author) is None:
        return "author is not an author name"
    return None


def lookup(references, client) -> dict[tuple, tuple[str, str | None]]:
    dois: list[tuple[tuple, str]] = []
    citations: list[tuple[tuple, tuple[str, str, str, str, str]]] = []
    seen: set[tuple] = set()
    for reference in references:
        key = reference_key(reference)
        if key in seen:
            continue
        seen.add(key)
        if key[0] == ReferenceKind.DOI.value:
            dois.append((key, reference.value))
        else:
            citations.append((key, citation_fields(reference.value)))
    found: dict[tuple, tuple[str, str | None]] = {}
    for key, doi in dois:
        found[key] = resolve_doi(client, doi)
    if citations:
        found.update(resolve_citations(client, citations))
    return found


def resolve_doi(client, doi: str) -> tuple[str, str | None]:
    count, ids = esearch(client, f'"{doi}"[doi]', 2)
    if count == 0:
        if ids:
            raise RuntimeError(f"ESearch returned ids for a DOI with no hits: {doi}")
        return ("not_found", None)
    if count == 1:
        if len(ids) != 1:
            raise RuntimeError("ESearch id list does not match the count")
        return ("resolved", ids[0])
    return ("ambiguous", None)


def resolve_citations(client, citations) -> dict[tuple, tuple[str, str | None]]:
    lines = []
    pairs = []
    for index, (key, fields) in enumerate(citations):
        token = f"~{index}"
        journal, year, volume, page, author = fields
        lines.append(f"{journal}|{year}|{volume}|{page}|{author}|{token}|")
        pairs.append((key, token))
    body = client.get_text(
        ECITMATCH_URL,
        ncbi_params({"db": "pubmed", "retmode": "xml", "rettype": "xml", "bdata": "\r".join(lines)}),
    )
    parsed = parse_ecitmatch(body, [token for _key, token in pairs])
    return {key: parsed[token] for key, token in pairs}


def parse_ecitmatch(body: str, tokens: list[str]) -> dict[str, tuple[str, str | None]]:
    wanted = set(tokens)
    found: dict[str, tuple[str, str | None]] = {}
    for raw_line in body.lstrip("\ufeff").splitlines():
        line = raw_line.strip()
        if line == "":
            continue
        fields = [field.strip() for field in line.split("|")]
        hits = [index for index, field in enumerate(fields) if field in wanted]
        if len(hits) != 1:
            raise RuntimeError("ECitMatch returned a line that does not identify one citation")
        token = fields[hits[0]]
        if token in found:
            raise RuntimeError(f"ECitMatch repeated citation {token}")
        payload = "|".join(fields[hits[0] + 1 :]).strip().strip("|").strip()
        found[token] = classify_payload(payload)
    if set(found) != wanted:
        raise RuntimeError("ECitMatch did not return every citation")
    return found


def classify_payload(payload: str) -> tuple[str, str | None]:
    text = payload.strip()
    folded = text.casefold()
    if PMID.fullmatch(text):
        return ("resolved", text)
    if folded.startswith("not_found") or "invalid_journal" in folded:
        return ("not_found", None)
    if folded.startswith("ambiguous") or (text.startswith("(") and "citation" in folded):
        return ("ambiguous", None)
    if MULTI_PMID.fullmatch(text):
        return ("ambiguous", None)
    raise RuntimeError(f"ECitMatch returned an unexpected status: {text}")


def esearch(client, term: str, retmax: int) -> tuple[int, list[str]]:
    body = client.get_json(
        ESEARCH_URL,
        ncbi_params(
            {
                "db": "pubmed",
                "term": term,
                "retmode": "json",
                "retmax": str(retmax),
                "retstart": "0",
            }
        ),
    )
    if body.get("error"):
        raise RuntimeError(f"ESearch error: {body['error']}")
    result = body.get("esearchresult")
    if not isinstance(result, dict):
        raise TypeError("ESearch returned no esearchresult")
    if result.get("ERROR") or result.get("errorlist"):
        raise RuntimeError(f"ESearch error: {result.get('ERROR') or result.get('errorlist')}")
    count = as_count(result.get("count"))
    idlist = result.get("idlist")
    if not isinstance(idlist, list):
        raise TypeError("ESearch returned no id list")
    if count > retmax:
        return count, []
    if len(idlist) != count:
        raise RuntimeError("ESearch id list does not match the count")
    pmids = []
    seen: set[str] = set()
    for raw in idlist:
        pmid = as_pmid(raw)
        if pmid in seen:
            raise RuntimeError(f"ESearch repeated pmid {pmid}")
        seen.add(pmid)
        pmids.append(pmid)
    return count, pmids


def ncbi_params(extra: dict[str, str]) -> dict[str, str]:
    params = {"tool": TOOL_NAME, **extra}
    email = os.environ.get("NCBI_EMAIL", "").strip()
    api_key = os.environ.get("NCBI_API_KEY", "").strip()
    if email:
        params["email"] = email
    if api_key:
        params["api_key"] = api_key
    return params


def as_count(raw) -> int:
    if type(raw) is bool or not isinstance(raw, int | str):
        raise TypeError("ESearch returned no count")
    try:
        count = int(raw)
    except ValueError as error:
        raise RuntimeError("ESearch returned no count") from error
    if count < 0:
        raise RuntimeError("ESearch returned no count")
    return count


def as_pmid(raw) -> str:
    if isinstance(raw, bool) or not isinstance(raw, int | str):
        raise TypeError(f"invalid pmid: {raw!r}")
    text = str(raw).strip()
    if PMID.fullmatch(text) is None:
        raise RuntimeError(f"invalid pmid: {raw!r}")
    return text
