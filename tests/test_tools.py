"""Tool tests. The HTTP client is a fake, so nothing here opens a socket."""

import json
from pathlib import Path

import httpx
import pytest
from slimconfig import build_output

from contract import Reference, UnresolvedInput
from plugin.client import ECITMATCH_URL, ESEARCH_URL, HttpxClient, set_client
from plugin.pin import pin_unresolved
from plugin.resolve import reference_key as tool_key
from plugin.unresolved import RESOLUTION_FILE, unresolved_citations
from verifier.identity import reference_key as check_key

SAMPLE = [
    {"kind": "doi", "value": "10.1000/found"},
    {"kind": "doi", "value": "10.1000/missing"},
    {"kind": "citation", "value": "Science|1987|235|182|Palmenberg"},
    {"kind": "citation", "value": "Notajournal|1999|1|1|Nobody"},
    {"kind": "doi", "value": "10.1000/many"},
]
ROWS = [
    {"kind": "doi", "value": "10.1000/found", "status": "resolved", "pmid": "100"},
    {"kind": "doi", "value": "10.1000/missing", "status": "not_found", "pmid": None},
    {"kind": "citation", "value": "Science|1987|235|182|Palmenberg", "status": "resolved", "pmid": "3026048"},
    {"kind": "citation", "value": "Notajournal|1999|1|1|Nobody", "status": "not_found", "pmid": None},
    {"kind": "doi", "value": "10.1000/many", "status": "ambiguous", "pmid": None},
]
DOIS = {
    "10.1000/found": (1, ["100"]),
    "10.1000/missing": (0, []),
    "10.1000/many": (2, ["200", "201"]),
    "10.1000/triple": (3, ["200", "201"]),
}
CITATIONS = {
    ("science", "1987", "235", "182", "palmenberg"): "3026048",
    ("notajournal", "1999", "1", "1", "nobody"): "NOT_FOUND",
    ("nature", "2020", "1", "1", "smith"): "AMBIGUOUS (2 citations)",
    ("bogus", "1993", "12", "22", "public"): "NOT_FOUND; INVALID_JOURNAL",
    ("annals", "1700", "1", "1", "old"): "100",
    ("annals", "2100", "1", "1", "new"): "101",
}


class FakeClient:
    def __init__(self, handler):
        self.handler = handler
        self.calls = []

    def get_json(self, url, params):
        self.calls.append((url, dict(params)))
        body = self.handler(url, params)
        if not isinstance(body, dict):
            raise TypeError(type(body))
        return body

    def get_text(self, url, params):
        self.calls.append((url, dict(params)))
        body = self.handler(url, params)
        if not isinstance(body, str):
            raise TypeError(type(body))
        return body


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.delenv("NCBI_API_KEY", raising=False)
    monkeypatch.delenv("NCBI_EMAIL", raising=False)
    holder = {}

    def install(handler):
        client = FakeClient(handler)
        holder["client"] = client
        set_client(client)
        return client

    yield install
    set_client(None)


def given(references=None):
    return build_output({"references": SAMPLE if references is None else references}, UnresolvedInput)


def values(output):
    return [(item.kind.value, item.value) for item in output.unresolved]


def quoted(term, field):
    suffix = f'"[{field}]'
    if not (term.startswith('"') and term.endswith(suffix)):
        raise AssertionError(term)
    return term[1 : -len(suffix)]


def citation_status(fields):
    journal, year, volume, page, author = fields
    key = (journal.casefold(), year, volume.casefold(), page.casefold(), author.casefold())
    if key not in CITATIONS:
        raise AssertionError(fields)
    return CITATIONS[key]


def ecitmatch_response(bdata):
    lines = []
    for piece in bdata.split("\r"):
        fields = piece.split("|")
        if fields[-1] != "" or len(fields) != 7:
            raise AssertionError(piece)
        lines.append(piece + citation_status(fields[:5]))
    return "\n".join(lines) + "\n"


def catalog(url, params):
    if url == ECITMATCH_URL:
        assert params["db"] == "pubmed"
        assert params["retmode"] == "xml"
        assert params["rettype"] == "xml"
        return ecitmatch_response(params["bdata"])
    if url != ESEARCH_URL:
        raise AssertionError(url)
    assert params["retmax"] == "2"
    assert params["db"] == "pubmed"
    assert params["retmode"] == "json"
    doi = quoted(params["term"], "doi").casefold()
    if doi not in DOIS:
        raise AssertionError(doi)
    count, ids = DOIS[doi]
    shown = ids if count <= 2 else ids[:2]
    return {"esearchresult": {"count": str(count), "idlist": shown}}


def test_returns_the_unresolved_subset_and_writes_rows(fake, tmp_path: Path):
    client = fake(catalog)
    output = unresolved_citations(given(), tmp_path)
    assert values(output) == [
        ("doi", "10.1000/missing"),
        ("citation", "Notajournal|1999|1|1|Nobody"),
        ("doi", "10.1000/many"),
    ]
    assert [url for url, _params in client.calls] == [ESEARCH_URL, ESEARCH_URL, ESEARCH_URL, ECITMATCH_URL]
    saved = json.loads((tmp_path / RESOLUTION_FILE).read_text(encoding="utf-8"))
    assert saved == {"references": ROWS}


def test_pin_matches_the_tool_and_writes_nothing(fake, tmp_path: Path):
    fake(catalog)
    pinned = pin_unresolved(given(), tmp_path)
    assert not (tmp_path / RESOLUTION_FILE).exists()
    assert values(pinned) == values(unresolved_citations(given(), tmp_path))


def test_empty_list_writes_an_empty_file_and_does_not_call(fake, tmp_path: Path):
    client = fake(catalog)
    output = unresolved_citations(given([]), tmp_path)
    assert values(output) == []
    assert client.calls == []
    saved = json.loads((tmp_path / RESOLUTION_FILE).read_text(encoding="utf-8"))
    assert saved == {"references": []}


def test_every_resolved_reference_returns_an_empty_subset(fake, tmp_path: Path):
    fake(catalog)
    papers = [SAMPLE[0], SAMPLE[2]]
    output = unresolved_citations(given(papers), tmp_path)
    assert values(output) == []
    saved = json.loads((tmp_path / RESOLUTION_FILE).read_text(encoding="utf-8"))
    assert [row["status"] for row in saved["references"]] == ["resolved", "resolved"]


def test_a_repeated_missing_doi_is_looked_up_once(fake, tmp_path: Path):
    client = fake(catalog)
    papers = [
        {"kind": "doi", "value": "10.1000/Missing"},
        {"kind": "doi", "value": "10.1000/missing"},
    ]
    output = unresolved_citations(given(papers), tmp_path)
    assert values(output) == [("doi", "10.1000/Missing")]
    assert len(client.calls) == 1
    assert "10.1000/Missing" in client.calls[0][1]["term"]


def test_a_repeated_citation_is_sent_once_with_collapsed_fields(fake, tmp_path: Path):
    client = fake(catalog)
    papers = [
        {"kind": "citation", "value": "  Notajournal  | 1999 | 1 | 1 |  Nobody "},
        {"kind": "citation", "value": "notajournal|1999|1|1|nobody"},
    ]
    output = unresolved_citations(given(papers), tmp_path)
    assert values(output) == [("citation", papers[0]["value"])]
    assert [url for url, _params in client.calls] == [ECITMATCH_URL]
    assert client.calls[0][1]["bdata"] == "Notajournal|1999|1|1|Nobody|~0|"


def test_doi_only_skips_ecitmatch_and_citation_only_skips_esearch(fake, tmp_path: Path):
    client = fake(catalog)
    unresolved_citations(given([SAMPLE[0]]), tmp_path)
    assert [url for url, _params in client.calls] == [ESEARCH_URL]
    client.calls.clear()
    unresolved_citations(given([SAMPLE[3]]), tmp_path)
    assert [url for url, _params in client.calls] == [ECITMATCH_URL]


def test_ambiguous_citation_and_invalid_journal_are_unresolved(fake, tmp_path: Path):
    fake(catalog)
    papers = [
        {"kind": "citation", "value": "Nature|2020|1|1|Smith"},
        {"kind": "citation", "value": "Bogus|1993|12|22|Public"},
    ]
    output = unresolved_citations(given(papers), tmp_path)
    assert values(output) == [("citation", papers[0]["value"]), ("citation", papers[1]["value"])]
    saved = json.loads((tmp_path / RESOLUTION_FILE).read_text(encoding="utf-8"))
    assert [row["status"] for row in saved["references"]] == ["ambiguous", "not_found"]
    assert [row["pmid"] for row in saved["references"]] == [None, None]


def test_a_doi_with_three_hits_is_ambiguous(fake, tmp_path: Path):
    client = fake(catalog)
    paper = {"kind": "doi", "value": "10.1000/triple"}
    output = unresolved_citations(given([paper]), tmp_path)
    assert values(output) == [("doi", "10.1000/triple")]
    assert client.calls[0][1]["retmax"] == "2"
    saved = json.loads((tmp_path / RESOLUTION_FILE).read_text(encoding="utf-8"))
    assert saved["references"] == [{"kind": "doi", "value": "10.1000/triple", "status": "ambiguous", "pmid": None}]


def test_boundary_years_resolve(fake, tmp_path: Path):
    fake(catalog)
    papers = [
        {"kind": "citation", "value": "Annals|1700|1|1|Old"},
        {"kind": "citation", "value": "Annals|2100|1|1|New"},
    ]
    output = unresolved_citations(given(papers), tmp_path)
    assert values(output) == []


def test_thirty_copies_are_accepted_and_thirty_one_raises(fake, tmp_path: Path):
    client = fake(catalog)
    thirty = [{"kind": "doi", "value": "10.1000/missing"} for _number in range(30)]
    output = unresolved_citations(given(thirty), tmp_path)
    assert values(output) == [("doi", "10.1000/missing")]
    assert len(client.calls) == 1
    client.calls.clear()
    with pytest.raises(ValueError, match="more than 30"):
        unresolved_citations(given([*thirty, {"kind": "doi", "value": "10.1000/missing"}]), tmp_path)
    assert client.calls == []


def test_a_bad_doi_raises_before_any_call_or_file(fake, tmp_path: Path):
    client = fake(catalog)
    with pytest.raises(ValueError, match="not a DOI"):
        unresolved_citations(given([{"kind": "doi", "value": "10.1/x"}]), tmp_path)
    assert client.calls == []
    assert not (tmp_path / RESOLUTION_FILE).exists()


def test_a_failed_lookup_writes_no_file(fake, tmp_path: Path):
    def flaky(url, params):
        if "missing" in params.get("term", ""):
            raise RuntimeError("HTTP 500 from esearch")
        return catalog(url, params)

    fake(flaky)
    papers = [SAMPLE[0], SAMPLE[1]]
    with pytest.raises(RuntimeError, match="HTTP 500"):
        unresolved_citations(given(papers), tmp_path)
    assert not (tmp_path / RESOLUTION_FILE).exists()


def test_esearch_error_and_a_short_id_list_raise(fake, tmp_path: Path):
    def error(_url, _params):
        return {"error": "busy"}

    fake(error)
    with pytest.raises(RuntimeError, match="ESearch error"):
        unresolved_citations(given([SAMPLE[0]]), tmp_path)
    assert not (tmp_path / RESOLUTION_FILE).exists()

    def shapeless(_url, _params):
        return {}

    fake(shapeless)
    with pytest.raises(TypeError, match="esearchresult"):
        unresolved_citations(given([SAMPLE[0]]), tmp_path)

    def short(_url, _params):
        return {"esearchresult": {"count": "1", "idlist": []}}

    fake(short)
    with pytest.raises(RuntimeError, match="does not match"):
        unresolved_citations(given([SAMPLE[0]]), tmp_path)

    def not_a_list(_url, _params):
        return {"esearchresult": {"count": "1", "idlist": "100"}}

    fake(not_a_list)
    with pytest.raises(TypeError, match="id list"):
        unresolved_citations(given([SAMPLE[0]]), tmp_path)


def test_unexpected_and_incomplete_ecitmatch_bodies_raise(fake, tmp_path: Path):
    paper = [SAMPLE[2]]

    def unexpected(_url, _params):
        return "Science|1987|235|182|Palmenberg|~0|MAYBE\n"

    fake(unexpected)
    with pytest.raises(RuntimeError, match="unexpected status"):
        unresolved_citations(given(paper), tmp_path)
    assert not (tmp_path / RESOLUTION_FILE).exists()

    def missing(_url, _params):
        return "Science|1987|235|182|Palmenberg|~9|3026048\n"

    fake(missing)
    with pytest.raises(RuntimeError, match="does not identify"):
        unresolved_citations(given(paper), tmp_path)

    def repeated(_url, _params):
        line = "Science|1987|235|182|Palmenberg|~0|3026048\n"
        return line + line

    fake(repeated)
    with pytest.raises(RuntimeError, match="repeated"):
        unresolved_citations(given(paper), tmp_path)


def test_sends_the_tool_name_and_credentials(fake, monkeypatch, tmp_path: Path):
    monkeypatch.setenv("NCBI_API_KEY", "secret-key")
    monkeypatch.setenv("NCBI_EMAIL", "a@example.com")
    client = fake(catalog)
    unresolved_citations(given([SAMPLE[0]]), tmp_path)
    params = client.calls[0][1]
    assert params["tool"] == "citations-not-on-pubmed"
    assert params["api_key"] == "secret-key"
    assert params["email"] == "a@example.com"


def test_identity_matches_the_verifier():
    samples = [
        {"kind": "doi", "value": "10.1000/AbC"},
        {"kind": "citation", "value": "  Science  | 1987 | 12A | e12 |  O'Brien "},
    ]
    for sample in samples:
        reference = build_output(sample, Reference)
        assert tool_key(reference) == check_key(reference)


def test_client_rejects_transport_failures():
    def json_handler(_request):
        return httpx.Response(200, text="nope")

    client = HttpxClient(transport=httpx.MockTransport(json_handler), pause=0)
    with pytest.raises(RuntimeError, match="not JSON"):
        client.get_json(ESEARCH_URL, {})

    def list_handler(_request):
        return httpx.Response(200, json=["nope"])

    client = HttpxClient(transport=httpx.MockTransport(list_handler), pause=0)
    with pytest.raises(TypeError, match="not a JSON object"):
        client.get_json(ESEARCH_URL, {})

    def empty_handler(_request):
        return httpx.Response(200, text="  \n")

    client = HttpxClient(transport=httpx.MockTransport(empty_handler), pause=0)
    with pytest.raises(RuntimeError, match="empty"):
        client.get_text(ECITMATCH_URL, {})

    def down_handler(_request):
        return httpx.Response(503, text="no")

    client = HttpxClient(transport=httpx.MockTransport(down_handler), pause=0)
    with pytest.raises(RuntimeError, match="HTTP 503"):
        client.get_json(ESEARCH_URL, {})


def test_pause_follows_the_api_key(monkeypatch):
    slept = []
    monkeypatch.setattr("plugin.client.time.sleep", slept.append)

    def ok(_request):
        return httpx.Response(200, json={"ok": True})

    monkeypatch.setenv("NCBI_API_KEY", "secret-key")
    client = HttpxClient(transport=httpx.MockTransport(ok), pause=None)
    client.get_json(ESEARCH_URL, {})
    client.get_json(ESEARCH_URL, {})
    assert slept == [0.11]

    slept.clear()
    monkeypatch.delenv("NCBI_API_KEY", raising=False)
    client = HttpxClient(transport=httpx.MockTransport(ok), pause=None)
    client.get_json(ESEARCH_URL, {})
    client.get_json(ESEARCH_URL, {})
    assert slept == [0.34]
