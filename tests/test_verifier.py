"""Verifier cases: correct, wrong, missing, malformed, and boundary."""

import json
from pathlib import Path

from slimconfig import build_output

import verifier
from contract import UnresolvedInput, UnresolvedOutput

SAMPLE = [
    {"kind": "doi", "value": "10.1000/found"},
    {"kind": "doi", "value": "10.1000/missing"},
    {"kind": "citation", "value": "Science|1987|235|182|Palmenberg"},
    {"kind": "citation", "value": "Notajournal|1999|1|1|Nobody"},
    {"kind": "doi", "value": "10.1000/many"},
]
KEPT = [SAMPLE[1], SAMPLE[3], SAMPLE[4]]
ROWS = [
    {"kind": "doi", "value": "10.1000/found", "status": "resolved", "pmid": "100"},
    {"kind": "doi", "value": "10.1000/missing", "status": "not_found", "pmid": None},
    {"kind": "citation", "value": "Science|1987|235|182|Palmenberg", "status": "resolved", "pmid": "3026048"},
    {"kind": "citation", "value": "Notajournal|1999|1|1|Nobody", "status": "not_found", "pmid": None},
    {"kind": "doi", "value": "10.1000/many", "status": "ambiguous", "pmid": None},
]


def given(references=None):
    return build_output({"references": SAMPLE if references is None else references}, UnresolvedInput)


def made(references):
    return build_output({"unresolved": references}, UnresolvedOutput)


def write_rows(workspace: Path, rows) -> None:
    (workspace / "resolution.json").write_text(json.dumps({"references": rows}), encoding="utf-8")


def test_verify_input_accepts_the_sample():
    assert verifier.verify_input("unresolved_citations", given())["valid"] is True
    assert verifier.verify_input("pin_unresolved", given())["valid"] is True


def test_verify_input_rejects_a_blank_value():
    blank_doi = verifier.verify_input("unresolved_citations", given([{"kind": "doi", "value": "   "}]))
    assert blank_doi["valid"] is False
    assert "empty" in blank_doi["message"]
    blank_citation = verifier.verify_input("pin_unresolved", given([{"kind": "citation", "value": "  "}]))
    assert blank_citation["valid"] is False
    assert "empty" in blank_citation["message"]
    missing_author = verifier.verify_input(
        "unresolved_citations",
        given([{"kind": "citation", "value": "Science|1987|235|182|"}]),
    )
    assert missing_author["valid"] is False
    assert "author" in missing_author["message"]


def test_verify_input_rejects_malformed_references():
    short_doi = verifier.verify_input("unresolved_citations", given([{"kind": "doi", "value": "10.1/x"}]))
    assert short_doi["valid"] is False
    assert "doi" in short_doi["message"]
    early = verifier.verify_input("pin_unresolved", given([{"kind": "citation", "value": "Science|1699|1|1|Smith"}]))
    assert early["valid"] is False
    assert "year" in early["message"]
    late = verifier.verify_input("unresolved_citations", given([{"kind": "citation", "value": "Science|2101|1|1|Smith"}]))
    assert late["valid"] is False
    slash = verifier.verify_input(
        "unresolved_citations",
        given([{"kind": "citation", "value": "Science|2020/01|1|1|Smith"}]),
    )
    assert slash["valid"] is False
    assert "year" in slash["message"]
    page_range = verifier.verify_input(
        "pin_unresolved",
        given([{"kind": "citation", "value": "Science|2020|1|10-15|Smith"}]),
    )
    assert page_range["valid"] is False
    assert "page" in page_range["message"]
    fields = verifier.verify_input("unresolved_citations", given([{"kind": "citation", "value": "Science|2020|1|1"}]))
    assert fields["valid"] is False
    assert "journal|year|volume|first_page|author" in fields["message"]
    too_many = [{"kind": "doi", "value": "10.1000/found"} for _number in range(31)]
    oversized = verifier.verify_input("unresolved_citations", given(too_many))
    assert oversized["valid"] is False
    assert "more than 30" in oversized["message"]


def test_verify_input_accepts_boundary_years_pages_and_a_full_list():
    papers = [
        {"kind": "citation", "value": "Annals|1700|1|1|Old"},
        {"kind": "citation", "value": "Annals|2100|12A|e12|O'Brien"},
        {"kind": "citation", "value": "Proc. Natl. Acad. Sci. U. S. A.|1991|88|3248|Mann"},
    ]
    assert verifier.verify_input("pin_unresolved", given(papers))["valid"] is True
    thirty = [{"kind": "doi", "value": "10.1000/found"} for _number in range(30)]
    assert verifier.verify_input("unresolved_citations", given(thirty))["valid"] is True
    long_journal = "A" * 150
    accepted = verifier.verify_input(
        "unresolved_citations",
        given([{"kind": "citation", "value": f"{long_journal}|2020|1|1|Smith"}]),
    )
    assert accepted["valid"] is True
    longer = verifier.verify_input(
        "unresolved_citations",
        given([{"kind": "citation", "value": f"{'A' * 151}|2020|1|1|Smith"}]),
    )
    assert longer["valid"] is False
    assert "150" in longer["message"]


def test_verify_output_accepts_the_subset(tmp_path: Path):
    write_rows(tmp_path, ROWS)
    verdict = verifier.verify_output("unresolved_citations", given(), made(KEPT), str(tmp_path))
    assert verdict["valid"] is True
    assert verdict["score"] == 1.0


def test_verify_output_rejects_an_included_hit_a_drop_and_a_swap(tmp_path: Path):
    write_rows(tmp_path, ROWS)
    included = verifier.verify_output("unresolved_citations", given(), made([*KEPT, SAMPLE[0]]), str(tmp_path))
    assert included["valid"] is False
    assert included["score"] == 0.0
    assert "resolution.json" in included["message"]
    dropped = verifier.verify_output("unresolved_citations", given(), made([SAMPLE[3], SAMPLE[4]]), str(tmp_path))
    assert dropped["valid"] is False
    swapped = verifier.verify_output("unresolved_citations", given(), made([SAMPLE[4], SAMPLE[1], SAMPLE[3]]), str(tmp_path))
    assert swapped["valid"] is False
    assert "resolution.json" in swapped["message"]


def test_verify_output_rejects_a_missing_file(tmp_path: Path):
    verdict = verifier.verify_output("unresolved_citations", given(), made(KEPT), str(tmp_path))
    assert verdict["valid"] is False
    assert "missing" in verdict["message"]


def test_verify_output_rejects_malformed_json(tmp_path: Path):
    (tmp_path / "resolution.json").write_text("{", encoding="utf-8")
    verdict = verifier.verify_output("unresolved_citations", given(), made(KEPT), str(tmp_path))
    assert verdict["valid"] is False
    assert "JSON" in verdict["message"]
    (tmp_path / "resolution.json").write_text("[]", encoding="utf-8")
    verdict = verifier.verify_output("unresolved_citations", given(), made(KEPT), str(tmp_path))
    assert verdict["valid"] is False
    assert "references list" in verdict["message"]


def test_verify_output_rejects_a_resolved_row_without_a_pmid(tmp_path: Path):
    rows = [{"kind": "doi", "value": "10.1000/found", "status": "resolved", "pmid": None}]
    write_rows(tmp_path, rows)
    verdict = verifier.verify_output("unresolved_citations", given([SAMPLE[0]]), made([]), str(tmp_path))
    assert verdict["valid"] is False
    assert "without a pmid" in verdict["message"]
    rows[0]["pmid"] = "0100"
    write_rows(tmp_path, rows)
    leading = verifier.verify_output("unresolved_citations", given([SAMPLE[0]]), made([]), str(tmp_path))
    assert leading["valid"] is False
    assert "pmid" in leading["message"]


def test_verify_output_rejects_a_pmid_on_an_unresolved_row(tmp_path: Path):
    rows = [{"kind": "doi", "value": "10.1000/missing", "status": "not_found", "pmid": "100"}]
    write_rows(tmp_path, rows)
    verdict = verifier.verify_output("unresolved_citations", given([SAMPLE[1]]), made([SAMPLE[1]]), str(tmp_path))
    assert verdict["valid"] is False
    assert "pmid" in verdict["message"]
    rows[0]["status"] = "gone"
    rows[0]["pmid"] = None
    write_rows(tmp_path, rows)
    unknown = verifier.verify_output("unresolved_citations", given([SAMPLE[1]]), made([SAMPLE[1]]), str(tmp_path))
    assert unknown["valid"] is False
    assert "status" in unknown["message"]


def test_verify_output_rejects_a_repeated_output(tmp_path: Path):
    papers = [SAMPLE[1], SAMPLE[1]]
    rows = [
        {"kind": "doi", "value": "10.1000/missing", "status": "not_found", "pmid": None},
        {"kind": "doi", "value": "10.1000/missing", "status": "not_found", "pmid": None},
    ]
    write_rows(tmp_path, rows)
    verdict = verifier.verify_output("unresolved_citations", given(papers), made(papers), str(tmp_path))
    assert verdict["valid"] is False
    assert "repeats" in verdict["message"]


def test_verify_output_rejects_rows_that_disagree(tmp_path: Path):
    papers = [SAMPLE[1], {"kind": "doi", "value": "10.1000/missing"}]
    rows = [
        {"kind": "doi", "value": "10.1000/missing", "status": "not_found", "pmid": None},
        {"kind": "doi", "value": "10.1000/missing", "status": "resolved", "pmid": "100"},
    ]
    write_rows(tmp_path, rows)
    verdict = verifier.verify_output("unresolved_citations", given(papers), made([SAMPLE[1]]), str(tmp_path))
    assert verdict["valid"] is False
    assert "disagrees" in verdict["message"]


def test_verify_output_rejects_a_reference_that_was_not_in_the_input(tmp_path: Path):
    write_rows(tmp_path, ROWS)
    extra = {"kind": "doi", "value": "10.1000/other"}
    verdict = verifier.verify_output("unresolved_citations", given(), made([*KEPT, extra]), str(tmp_path))
    assert verdict["valid"] is False
    assert "not in the input" in verdict["message"]


def test_pin_output_does_not_need_a_file(tmp_path: Path):
    verdict = verifier.verify_output("pin_unresolved", given(), made(KEPT), str(tmp_path))
    assert verdict["valid"] is True


def test_pin_output_rejects_a_malformed_doi_and_a_stranger(tmp_path: Path):
    malformed = verifier.verify_output("pin_unresolved", given(), made([{"kind": "doi", "value": "10.1/x"}]), str(tmp_path))
    assert malformed["valid"] is False
    assert "doi" in malformed["message"]
    stranger = verifier.verify_output(
        "pin_unresolved",
        given(),
        made([{"kind": "doi", "value": "10.1000/other"}]),
        str(tmp_path),
    )
    assert stranger["valid"] is False
    assert "not in the input" in stranger["message"]


def test_verify_task_accepts_the_reference(tmp_path: Path):
    write_rows(tmp_path, ROWS)
    verdict = verifier.verify_task("citations-not-on-pubmed", given(), made(KEPT), made(KEPT), str(tmp_path))
    assert verdict["valid"] is True
    assert verdict["score"] == 1.0


def test_verify_task_rejects_a_wrong_list_and_a_missing_reference(tmp_path: Path):
    write_rows(tmp_path, ROWS)
    wrong = verifier.verify_task("citations-not-on-pubmed", given(), made([SAMPLE[0]]), made(KEPT), str(tmp_path))
    assert wrong["valid"] is False
    assert "reference" in wrong["message"]
    missing = verifier.verify_task("citations-not-on-pubmed", given(), made(KEPT), None, str(tmp_path))
    assert missing["valid"] is False
    assert "missing" in missing["message"]


def test_verify_task_rejects_a_file_that_does_not_support_the_reference(tmp_path: Path):
    write_rows(tmp_path, ROWS)
    verdict = verifier.verify_task("citations-not-on-pubmed", given(), made(KEPT), made(KEPT), str(tmp_path))
    assert verdict["valid"] is True
    (tmp_path / "resolution.json").unlink()
    missing = verifier.verify_task("citations-not-on-pubmed", given(), made(KEPT), made(KEPT), str(tmp_path))
    assert missing["valid"] is False
    assert "resolution.json is missing" in missing["message"]
    write_rows(tmp_path, [ROWS[0], ROWS[1], ROWS[2], ROWS[3], {**ROWS[4], "status": "resolved", "pmid": "200"}])
    unsupported = verifier.verify_task("citations-not-on-pubmed", given(), made(KEPT), made(KEPT), str(tmp_path))
    assert unsupported["valid"] is False
    assert "does not support" in unsupported["message"]


def test_verify_task_rejects_a_malformed_reference(tmp_path: Path):
    write_rows(tmp_path, ROWS)
    verdict = verifier.verify_task(
        "citations-not-on-pubmed",
        given(),
        made(KEPT),
        made([{"kind": "doi", "value": "10.1/x"}]),
        str(tmp_path),
    )
    assert verdict["valid"] is False
    assert "doi" in verdict["message"]


def test_boundary_empty_input_and_all_resolved_are_valid(tmp_path: Path):
    write_rows(tmp_path, [])
    empty = verifier.verify_task("citations-not-on-pubmed", given([]), made([]), made([]), str(tmp_path))
    assert empty["valid"] is True
    papers = [SAMPLE[0], SAMPLE[2]]
    rows = [ROWS[0], ROWS[2]]
    write_rows(tmp_path, rows)
    resolved = verifier.verify_task("citations-not-on-pubmed", given(papers), made([]), made([]), str(tmp_path))
    assert resolved["valid"] is True
    kept_once = [SAMPLE[1], SAMPLE[1]]
    repeat_rows = [
        {"kind": "doi", "value": "10.1000/missing", "status": "not_found", "pmid": None},
        {"kind": "doi", "value": "10.1000/missing", "status": "not_found", "pmid": None},
    ]
    write_rows(tmp_path, repeat_rows)
    repeated = verifier.verify_task(
        "citations-not-on-pubmed",
        given(kept_once),
        made([SAMPLE[1]]),
        made([SAMPLE[1]]),
        str(tmp_path),
    )
    assert repeated["valid"] is True


def test_invalid_journal_and_ambiguous_rows_stay_in_the_subset(tmp_path: Path):
    papers = [
        {"kind": "citation", "value": "Nature|2020|1|1|Smith"},
        {"kind": "citation", "value": "Bogus|1993|12|22|Public"},
        {"kind": "doi", "value": "10.1000/found"},
    ]
    rows = [
        {"kind": "citation", "value": "Nature|2020|1|1|Smith", "status": "ambiguous", "pmid": None},
        {"kind": "citation", "value": "Bogus|1993|12|22|Public", "status": "not_found", "pmid": None},
        {"kind": "doi", "value": "10.1000/found", "status": "resolved", "pmid": "100"},
    ]
    kept = papers[:2]
    write_rows(tmp_path, rows)
    verdict = verifier.verify_task("citations-not-on-pubmed", given(papers), made(kept), made(kept), str(tmp_path))
    assert verdict["valid"] is True
