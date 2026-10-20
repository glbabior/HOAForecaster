# HOAForecaster

The specification is [HOAForecaster_REQUIREMENTS.md](HOAForecaster_REQUIREMENTS.md). Read it before changing behaviour; cite its section numbers in reviews and commit bodies.

## Public code, private data

This repository is public. Never commit a real association's name, figures, people, documents or workbook – not in code, tests, fixtures, comments, commit messages or docs. Real data lives in the private sibling repository `HOAForecaster-data` (section 8.1). Public tests use the fictional demo project in `demo/`.

## Layout

- `src/hoa_engine/` – the calculation engine (section 6). Pure Python, no I/O, `Decimal` throughout. `run(baseline, scenario)` is the only entry point. `model.py` also holds `Project` and the JSON project format.
- `src/hoa_workbook/` – Excel export and re-import (sections 7.1, 7.6). `layout.py` is the single source for sheet names, rows and labels, shared by `export.py` (writer) and `read.py` (reader); `charts.py` builds the native charts. It imports only `hoa_engine.model` and `hoa_engine.validate` – never the engine – so its formulas stay an independent check on the engine (enforced by `tests/workbook/test_independence.py`).
- `src/hoa_store/` – project storage (section 8): one JSON file per project in the data folder, drafts, trash, export/import of project files, first-run demo seeding. Every error is a `StoreError` with a plain-language message.
- `tests/engine/` – unit tests and the section 9 acceptance tests; 100% coverage of `hoa_engine` is enforced. `tests/workbook/` – export recalculates in LibreOffice to the engine's figures, export → import round trip, Excel open check (Windows with Excel), bad-file handling. `tests/store/` – storage, including concurrent saves and hostile files. `tests/compare.py` – the engine-vs-workbook comparison.
- `demo/fixtures/` – the fictional project (`project.json`), its exported workbook (`reference.xlsx`) and the figures LibreOffice computed from it (`expected.json`). Regenerate with `uv run python demo/build_reference_workbook.py` after changing the demo project or the exporter's formulas; `expected.json` changing means a formula changed.
- `tools/recalc.py` – LibreOffice headless recalculation and formula-error scan. `tools/extract_expected.py` – reads expected figures out of any workbook in the reference layout. `tools/excel_check.ps1` – opens a workbook in real Excel and reports any repair.

## Commands

```
uv sync                                     # install
uv run pytest --cov                         # tests; add HOA_PRIVATE_DIR=../HOAForecaster-data for the private set
uv run ruff check . && uv run ruff format --check .
uv run mypy
```

`git config core.hooksPath .githooks` once per clone turns on the pre-commit lint, format and type checks.

## Stack decisions

- Python FastAPI backend + React/TypeScript front end (section 11, decided in v1.2). Engine and Excel exporter are both Python.
- `uv` for the Python environment; Python ≥ 3.12.
- Money and rates are `Decimal` in memory and decimal strings in JSON; floats are refused on load.
- Dues rounding applies only to grown dues, each year rounded half-up from the unrounded growth; typed and pinned values are used as typed.
- Expected figures always come from a spreadsheet recalculated by Excel or LibreOffice, never from the engine.
- Export – sheets in the reference order (Method, Inputs, Compare, Charts, Expenses, then one per scenario). Scenario sheets are named from the scenario, cleaned to a legal, unique name (31 UTF-16 units, no trailing apostrophe); the full name is in cell A1. Dues settings sit below the table; the rounding cell drives the dues formulas (a dropdown), while the dues mode is set in the app because it decides which cells hold formulas. Special assessments are a list, one row each with spare rows, summed into the year row by SUMIF – so installments and notes survive a re-import.
- User text is always written as text, and text starting with = + - @ also gets Excel's quote prefix so it stays text when edited or saved as CSV. Control characters (other than tab, newline and return) are refused in every text field when a project is read.
- Import (`read.py`) reads only the export layout. Section 7.1a (CSV of expenses and FFB) and 7.1b (the original reference workbook, with its partial first year) are still open; the private repo's `fixtures/make_project.py` does 7.1b as a one-off. A re-import is identical to the exported project except that numbers pass through Excel's doubles (about 15 significant digits). An expense row without its year formulas is refused rather than read, because the workbook's own totals would leave it out.
- Import limits – 20 MB file, 20 MB unpacked, 100:1 compression per part, 2,000 rows by 200 columns per sheet; defusedxml must be active. Imported projects are validated before they are returned.
- Two environment variables, never interchangeable – `HOA_DATA_DIR` is the app's own data folder (default the per-user application data folder, `%APPDATA%\HOAForecaster` on Windows); `HOA_PRIVATE_DIR` is the private data repository, used only by the private acceptance tests and the commit guard. The spec's "bundled demo folder" default became the app data folder with the demo copied in on first run, so the app never writes into the repo.
- Storage – `<data>/projects/<id>.json`, `<data>/drafts/<id>.json`, `<data>/trash/<id>.json`. Ids are 12 hex characters made by the server; user text never becomes a file name. Saves are atomic, serialised by a lock and carry a `revision`; a save names the revision it started from and is refused if another save came first. Each draft records its base revision so the app can warn that it is stale. Delete moves to the trash folder (no restore in the app yet). The demo is copied in only when the projects folder does not yet exist, so a deleted demo stays deleted.
- Timestamps – the project, its baseline and each scenario have created and modified times (spec section 3). A scenario is identified by its name, so a rename starts a new history. Export carries the timestamps, not the id or revision; import keeps valid timestamps.
- The Charts sheet's shared dollar scale is passed in by the caller from the engine's results, snapped to a grid whose lines coincide with 0–100% in 20% steps.

### Engine choices the spec leaves open

- Dues modes – the UI offers the spec's three (section 5); the engine has two. `EXPLICIT` is mode a; `RATE` is mode b, and mode c when `overrides` is non-empty.
- `needs_vote` compares the first year's dues with the baseline's current dues. The dues-jump rule is skipped when the prior year's dues are 0 (no percentage exists). A rise of exactly the limit needs no vote.
- Percent funded is 0 when next year's FFB is 0, matching the reference workbook's `IF(FFB=0,0,…)` guard.
- `shortfall_years` (count of operating-shortfall years) is an extra summary measure alongside the section 6 list, feeding the Compare view.
- `dues_y9`, `balance_y9` and `pf_y9` are `None` when the horizon is shorter than 9 years.
- Expense lines and explicit dues outside the horizon are kept and ignored, not errors – shortening the horizon must never discard data. Pinned dues and assessments outside the horizon are errors, since they belong to a scenario's intent for those years.
- The expense base year must fall between 50 years before the start year and the end year; a line dated before the base year is deflated by the same formula.
- The percent-funded target must be above 0% and at most 100%.
- A governance limit that is missing or `null` in a project file means no limit, and is written back as `null`. The spec's 20% / 5% defaults are what a new project starts with.
- The engine runs under its own decimal context (28 digits, half-even); a caller's context cannot change its figures.

## Agents – when to invoke

- **code-reviewer** – before every commit to `main`. Blocking findings must be fixed first.
- **security-reviewer** – before each release, and on any change touching file I/O, import/export, dependencies, the local server, or anything that could carry real data into this repo.
- **documentation-writer** – when a feature is complete and before each release. A release is not done until it passes.

## Working method

Engine first (done), then the exporter, then the UI (section 10.3). Write the failing test first. Commit after each green test run; one concern per commit.
