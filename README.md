# HOAForecaster

A local app for homeowners association boards. Enter a building's reserve facts once, then build and compare funding plans – dues paths and special assessments – and see each plan's year-by-year reserve balance, percent funded and cost per owner.

Work in progress – the calculation engine is built and tested; the Excel exporter and the user interface come next. See [the requirements](HOAForecaster_REQUIREMENTS.md).

## Develop

Requires [uv](https://docs.astral.sh/uv/) and, to regenerate the demo fixtures, [LibreOffice](https://www.libreoffice.org/).

```
uv sync
uv run pytest --cov
```

The demo project in `demo/` is fictional. To also run the acceptance tests against a private data folder, set `HOA_DATA_DIR` to its path.
