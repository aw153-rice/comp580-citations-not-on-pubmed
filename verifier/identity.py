"""Reference checks and the same identity rule the tool uses to drop duplicates."""

import re

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
KINDS = ("doi", "citation")
UNRESOLVED = frozenset({"not_found", "ambiguous"})


def citation_fields(value):
    journal, year, volume, page, author = value.split("|")
    return (" ".join(journal.split()), year.strip(), volume.strip(), page.strip(), " ".join(author.split()))


def reference_key(reference):
    kind = reference.kind.value
    if kind == "doi":
        return (kind, reference.value.casefold())
    journal, year, volume, page, author = citation_fields(reference.value)
    return (kind, journal.casefold(), year, volume.casefold(), page.casefold(), author.casefold())


def input_problem(value):
    """A (kind, message) pair, or None when every reference can be looked up."""
    if len(value.references) > MAX_REFERENCES:
        return ("malformed", f"references has more than {MAX_REFERENCES} items")
    for reference in value.references:
        problem = reference_problem(reference)
        if problem:
            return problem
    return None


def output_problem(output, given=None):
    """A (kind, message) pair, or None when the unresolved list is well formed."""
    if len(output.unresolved) > MAX_REFERENCES:
        return ("malformed", f"unresolved has more than {MAX_REFERENCES} references")
    seen = set()
    known = None
    if given is not None:
        known = {(item.kind.value, item.value) for item in given.references}
    for reference in output.unresolved:
        problem = reference_problem(reference)
        if problem:
            return problem
        key = reference_key(reference)
        if key in seen:
            return ("wrong", "unresolved repeats a reference")
        seen.add(key)
        if known is not None and (reference.kind.value, reference.value) not in known:
            return ("wrong", "unresolved contains a reference that was not in the input")
    return None


def reference_problem(reference):
    kind = reference.kind.value
    raw = reference.value
    if kind not in KINDS:
        return ("malformed", "kind is not doi or citation")
    if kind == "doi":
        problem = doi_problem(raw)
    else:
        problem = citation_problem(raw)
    if problem is None:
        return None
    return problem


def doi_problem(raw):
    if raw.strip() == "":
        return ("missing", "doi is empty")
    if len(raw) > DOI_MAX:
        return ("malformed", f"doi is longer than {DOI_MAX} characters")
    if any(ord(char) < 32 or ord(char) == 127 or ord(char) > 127 for char in raw):
        return ("malformed", "doi contains a character a DOI cannot contain")
    if DOI.fullmatch(raw) is None or any(char in raw for char in "\"[]"):
        return ("malformed", "doi is not a DOI")
    return None


def citation_problem(raw):
    if raw.strip() == "":
        return ("missing", "citation is empty")
    if len(raw) > CITATION_MAX:
        return ("malformed", f"citation is longer than {CITATION_MAX} characters")
    if any(ord(char) < 32 or ord(char) == 127 or ord(char) > 127 for char in raw):
        return ("malformed", "citation contains a character the citation matcher cannot accept")
    pieces = raw.split("|")
    if len(pieces) != 5:
        return ("malformed", "citation is not journal|year|volume|first_page|author")
    journal, year, volume, page, author = citation_fields(raw)
    return (
        journal_problem(journal)
        or year_problem(year)
        or volume_problem(volume)
        or page_problem(page)
        or author_problem(author)
    )


def journal_problem(journal):
    if journal == "":
        return ("missing", "journal is empty")
    if not any(char.isalpha() for char in journal):
        return ("malformed", "journal has no letters")
    if len(journal) > JOURNAL_MAX:
        return ("malformed", f"journal is longer than {JOURNAL_MAX} characters")
    if JOURNAL.fullmatch(journal) is None:
        return ("malformed", "journal has a character the citation matcher cannot accept")
    return None


def year_problem(year):
    if year == "":
        return ("missing", "year is empty")
    if len(year) != 4 or not year.isdigit() or not YEAR_MIN <= int(year) <= YEAR_MAX:
        return ("malformed", f"year is not a year from {YEAR_MIN} through {YEAR_MAX}")
    return None


def volume_problem(volume):
    if volume == "":
        return ("missing", "volume is empty")
    if VOLUME.fullmatch(volume) is None:
        return ("malformed", "volume is not a volume")
    return None


def page_problem(page):
    if page == "":
        return ("missing", "first page is empty")
    if PAGE.fullmatch(page) is None:
        return ("malformed", "first page is not a page")
    return None


def author_problem(author):
    if author == "":
        return ("missing", "author is empty")
    if AUTHOR.fullmatch(author) is None:
        return ("malformed", "author is not an author name")
    return None


def same_references(left, right):
    if len(left) != len(right):
        return False
    for found, expected in zip(left, right):
        if found.kind != expected.kind or found.value != expected.value:
            return False
    return True


def subset_from_rows(references, rows):
    chosen = []
    seen = set()
    for reference, row in zip(references, rows):
        if row["status"] not in UNRESOLVED:
            continue
        key = reference_key(reference)
        if key in seen:
            continue
        seen.add(key)
        chosen.append(reference)
    return chosen
