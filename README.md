# HOAForecaster

A local app for homeowners association boards. Enter a building's reserve facts once, then build and compare funding plans – dues paths, special assessments and any assumption changed for one plan – and see each plan's year-by-year reserve balance, percent funded and cost per owner. When the board decides, adopt a plan and keep it as a frozen record, and export the same Excel workbook a board already knows, with live formulas.

It runs on your own computer only – nothing is sent anywhere. See [the user guide](docs/user-guide.md), [the requirements](HOAForecaster_REQUIREMENTS.md), [how the figures are worked out](docs/engine.md) and [the exported workbook](docs/workbook.md).

## Install

Requires [git](https://git-scm.com/), [uv](https://docs.astral.sh/uv/) (it fetches Python 3.12 or later if needed) and [Node.js](https://nodejs.org/) (for building the screens the first time). The same commands work on Windows and macOS.

```
git clone <this repository's URL> HOAForecaster
cd HOAForecaster
uv sync
```

## Run

```
uv run hoaforecaster
```

The app opens in your browser at http://127.0.0.1:8765/. The first start builds the screens, which takes a minute, and adds a fictional demo project, Maple Row Condominiums. Press Ctrl+C in the same window to stop it.

`--port 8766` uses another port, and `--no-browser` starts it without opening a browser.

On Windows you can double-click **`HOAForecaster.bat`** in the project folder instead (or a shortcut to it on your desktop). It starts the same app, opens the browser once it is ready, and keeps its window open if the app stops with a problem, so the message stays readable. Close the window or press Ctrl+C to stop the app. It passes options on, so `HOAForecaster.bat --port 8766` works from a terminal too.

Starting the app while it is already running – double-clicking `HOAForecaster.bat` again, say – first stops the running copy cleanly (its window closes by itself), waits until it has ended, and then starts as usual. A copy started before this version cannot be stopped this way; close its window first.

The **Restart** button at the top right of every screen stops the server and starts a fresh one, rebuilding the screens first if they changed, then reloads the page – use it after updating the code. It appears only when the app was started this way, through `uv run hoaforecaster` or `HOAForecaster.bat`. Save your edits first; unsaved ones are kept only as a draft.

### Where projects are kept

Projects are saved in your user application-data folder – `%APPDATA%\HOAForecaster` on Windows, `~/Library/Application Support/HOAForecaster` on macOS. To keep them somewhere else, such as a private folder of your own, set `HOA_DATA_DIR` before starting.

```
# Windows (PowerShell)
$env:HOA_DATA_DIR = "C:\path\to\my-hoa-data"
uv run hoaforecaster

# macOS (Terminal)
HOA_DATA_DIR=~/my-hoa-data uv run hoaforecaster
```

The folder is created if it does not exist, and the demo project is copied into it the first time. Only one copy of the app can use a data folder at a time.

## Test

[LibreOffice](https://www.libreoffice.org/) is needed for the tests that recalculate exported workbooks (they are skipped without it).

```
uv run pytest --cov                     # Python – engine, workbook, storage, server
cd web && npm ci && npm test            # the screens
git config core.hooksPath .githooks     # once – lint, types and tests before each commit
```

The demo project in `demo/` is fictional. To also run the acceptance tests against a private fixture set, set `HOA_PRIVATE_DIR` to the folder that holds it. `HOA_DATA_DIR` is something else – the app's own data folder – and the two are never interchangeable.

See [CHANGELOG.md](CHANGELOG.md) for what has changed.
