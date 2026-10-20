# HOAForecaster

A local app for homeowners association boards. Enter a building's reserve facts once, then build and compare funding plans – dues paths and special assessments – and see each plan's year-by-year reserve balance, percent funded and cost per owner.

Work in progress – the calculation engine and the Excel export and re-import are built and tested; the app's screens come next. See [the requirements](HOAForecaster_REQUIREMENTS.md).

## Develop

Requires [uv](https://docs.astral.sh/uv/) and, to regenerate the demo fixtures, [LibreOffice](https://www.libreoffice.org/).

```
uv sync
uv run pytest --cov
```

The demo project in `demo/` is fictional. To also run the acceptance tests against a private fixture set, set `HOA_PRIVATE_DIR` to the folder that holds it. `HOA_DATA_DIR` is something else – the app's own data folder.
