# HOAForecaster

A local app for homeowners association boards. Enter a building's reserve facts once, then build and compare funding plans – dues paths and special assessments – and see each plan's year-by-year reserve balance, percent funded and cost per owner.

It runs on your own computer only – nothing is sent anywhere – and exports the same Excel workbook a board already knows, with live formulas. See [the requirements](HOAForecaster_REQUIREMENTS.md), [how the figures are worked out](docs/engine.md) and [the exported workbook](docs/workbook.md).

## Run

Requires [uv](https://docs.astral.sh/uv/) and [Node.js](https://nodejs.org/) (for building the screens the first time).

```
uv sync
uv run hoaforecaster
```

The app opens in your browser at http://127.0.0.1:8765/. The first start builds the screens and adds a fictional demo project. Projects are saved in your user application-data folder (`%APPDATA%\HOAForecaster` on Windows), or wherever `HOA_DATA_DIR` points.

## Develop

[LibreOffice](https://www.libreoffice.org/) is needed for the tests that recalculate exported workbooks (they are skipped without it).

```
uv run pytest --cov                     # Python – engine, workbook, storage, server
cd web && npm ci && npm test            # the screens
git config core.hooksPath .githooks     # once – lint, types and tests before each commit
```

The demo project in `demo/` is fictional. To also run the acceptance tests against a private fixture set, set `HOA_PRIVATE_DIR` to the folder that holds it. `HOA_DATA_DIR` is something else – the app's own data folder.
