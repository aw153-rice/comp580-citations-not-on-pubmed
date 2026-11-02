"""Each tool's and task's typed input and output (see nanoagent.plugin.v0001.contract): declarations only."""

from dataclasses import dataclass
from enum import Enum
from typing import Annotated

from slimconfig import Output


class Tool(Enum):
    UNRESOLVED_CITATIONS = "unresolved_citations"
    PIN_UNRESOLVED = "pin_unresolved"


class Task(Enum):
    CITATIONS_NOT_ON_PUBMED = "citations-not-on-pubmed"


class ReferenceKind(Enum):
    DOI = "doi"
    CITATION = "citation"


@dataclass
class Reference(Output):
    kind: Annotated[ReferenceKind, "Whether value is a DOI or a bibliographic citation"]
    value: Annotated[str, "The DOI, or a citation as journal|year|volume|first_page|author"]


@dataclass
class UnresolvedInput(Output):
    references: Annotated[list[Reference], "Reference-list entries to resolve, in caller order, at most 30"]


@dataclass
class UnresolvedOutput(Output):
    unresolved: Annotated[
        list[Reference],
        "Input references PubMed cannot match to one record, in input order, duplicates removed",
    ]


TOOLS = {
    Tool.UNRESOLVED_CITATIONS: (UnresolvedInput, UnresolvedOutput),
    Tool.PIN_UNRESOLVED: (UnresolvedInput, UnresolvedOutput),
}
TASKS = {Task.CITATIONS_NOT_ON_PUBMED: (UnresolvedInput, UnresolvedOutput)}
