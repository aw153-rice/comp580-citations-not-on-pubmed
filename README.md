# Citations Not on PubMed

A `nanoagent.plugin/v0001` plugin, created by `nanoagent plugin new` with the
structure of NanoAgent's reference plugin,
[arxiv-source](https://github.com/zeyuyang8/arxiv-source).

Given a reference list of DOIs and bibliographic citations, it returns the
ones PubMed cannot match to a single record.

## Tools

| Tool | Does | Code |
|---|---|---|
| `unresolved_citations` | Resolves each reference and returns the ones PubMed cannot match to one record | `src/plugin/unresolved.py` |
| `pin_unresolved` | Computes the same unresolved list as the task's answer key, and writes no file | `src/plugin/pin.py` |

`unresolved_citations` writes `resolution.json` in the workspace: one row per input reference, with status `resolved`, `not_found`, or `ambiguous`, and the PMID when the status is `resolved`. A DOI is one ESearch on the DOI field. A citation is `journal|year|volume|first_page|author` and goes to ECitMatch in one batch. Zero hits, `NOT_FOUND` (including an invalid journal), and more than one hit are unresolved. The same kind and normalized value is kept once, at its first occurrence. At most 30 references are accepted.

### Tasks

| Task | Does | Runner |
|---|---|---|
| `citations-not-on-pubmed` | Returns the references PubMed cannot resolve | `tool`, with `unresolved_citations` and reference `pin_unresolved` |

The input is `references`, each with `kind` (`doi` or `citation`) and `value`. The output is `unresolved`, those input references in order.

## Layout

```text
.
├── nanoagent.yaml   # manifest (a slimconfig ManifestConfig): id, runtime, permissions, tools, tasks
├── contract.py      # each tool's and task's typed input and output: slimconfig Output classes
├── README.md
├── LICENSE
├── pyproject.toml
├── uv.lock
├── .gitignore
├── .env             # environment variable NAMEs this plugin needs, never values
├── src/plugin/      # the MCP server: __main__.py, its IMPLEMENTATIONS, and the plugin's own modules
├── tests/
├── ui/              # how the page draws the outputs: renderers.js and renderers.css
├── product/         # the product page a catalog shows: product.yaml and icon.svg
└── verifier/        # deterministic verifier package
```

`contract.py` is the one place a value's shape is declared. Its `Output`
classes are the JSON Schemas the server offers and the agent sees, and every
input and output is built into its class on the way in and out: the server,
NanoAgent and the verifier all get typed values, never loose dicts. A tool
that fails raises; NanoAgent sees an MCP error.

## Develop and run

```bash
uv sync --extra dev
uv run pytest
```

The tests use a fake HTTP client and do not call NCBI. A live run needs
network access to `eutils.ncbi.nlm.nih.gov`. `NCBI_API_KEY` and `NCBI_EMAIL`
are listed in `.env`. The client sends them on the E-utilities request when
they are non-empty, and still resolves references when they are empty. No
workspace file is required before a run; `unresolved_citations` creates
`resolution.json`.
