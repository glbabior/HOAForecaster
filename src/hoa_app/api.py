"""The local HTTP API the browser front end talks to (spec sections 7 and 8).

Single-user and local: the server binds to 127.0.0.1 only. Because any web page
the user visits could still send requests to a localhost port, every API call
must carry a random token generated at launch and handed only to the app's own
page, and the Host header must name this machine (blocking DNS rebinding).
Request bodies are capped before they are read. Errors are plain language and
never carry a traceback.
"""

from __future__ import annotations

import re
import secrets
import unicodedata
from collections.abc import Awaitable, Callable
from dataclasses import fields, is_dataclass, replace
from datetime import date
from decimal import Decimal
from importlib.metadata import version
from pathlib import Path
from typing import Any
from urllib.parse import quote as url_quote

from fastapi import FastAPI, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from starlette.background import BackgroundTask
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from hoa_app.template import blank_project
from hoa_engine import InvalidInputs, ProjectFormatError, ScenarioResult, run
from hoa_engine.model import (
    MAX_NOTE,
    Project,
    adoption_date,
    baseline_from_dict,
    project_from_dict,
    project_to_dict,
    scenario_from_dict,
)
from hoa_engine.validate import validate_baseline, validate_run
from hoa_store.store import (
    BadProjectFile,
    Conflict,
    NotFound,
    ProjectStore,
    ReadOnly,
    StoredProject,
    StoreError,
    Unusable,
)
from hoa_workbook.export import export_workbook
from hoa_workbook.read import MAX_FILE_BYTES, WorkbookFormatError, read_workbook

TOKEN_HEADER = "X-HOA-Token"
TOKEN_PLACEHOLDER = "__HOA_TOKEN__"  # in web/dist/index.html, replaced when served
MAX_JSON_BYTES = 5 * 1024 * 1024
MAX_BODY_BYTES = MAX_FILE_BYTES + 1024 * 1024  # a workbook upload plus multipart framing
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]
CSP = (
    "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
    "script-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; "
    "frame-ancestors 'none'; form-action 'none'"
)


class ApiError(Exception):
    def __init__(self, status: int, message: str, problems: list[str] | None = None) -> None:
        super().__init__(message)
        self.status, self.message, self.problems = status, message, problems or []


# ---------------------------------------------------------------- JSON shapes


def to_json(value: Any) -> Any:
    """Engine results as JSON – Decimals as exact strings, dataclasses as objects."""
    if isinstance(value, Decimal):
        return str(value)
    if is_dataclass(value) and not isinstance(value, type):
        return {f.name: to_json(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, tuple | list):
        return [to_json(v) for v in value]
    if isinstance(value, dict):
        return {str(k): to_json(v) for k, v in value.items()}
    return value


def result_json(result: ScenarioResult) -> dict[str, Any]:
    years = []
    for y in result.years:
        row = to_json(y)
        for key in ("expense_lines", "operating_lines"):
            row[key] = [
                {
                    "id": line.id,
                    "frequency": line.frequency.value,
                    "description": line.description,
                    "source": line.source,
                    "nominal": line.nominal,
                    "amount": str(amount),
                }
                for line, amount in getattr(y, key)
            ]
        years.append(row)
    return {"years": years, "summary": to_json(result.summary)}


def stored_json(stored: StoredProject) -> dict[str, Any]:
    return {
        "id": stored.id,
        "revision": stored.revision,
        "times": stored.times,
        "baseline_times": stored.baseline_times,
        "scenario_times": stored.scenario_times,
        "project": project_to_dict(stored.project),
    }


def _results(project: Project) -> dict[str, Any]:
    """Every scenario's results, or its problems when its inputs are invalid."""
    out: dict[str, Any] = {}
    for s in project.scenarios:
        try:
            out[s.name] = {"result": result_json(run(project.baseline, s))}
        except InvalidInputs as e:
            out[s.name] = {"problems": e.problems}
    return out


def figures(result: ScenarioResult) -> Any:
    """A result's numbers only – an expense's description or source is not a change."""
    years = [
        (
            replace(y, expense_lines=(), operating_lines=()),
            [amount for _, amount in y.expense_lines],
            [amount for _, amount in y.operating_lines],
        )
        for y in result.years
    ]
    return years, result.summary


def dollar_axis(project: Project, names: list[str]) -> tuple[Decimal, Decimal] | None:
    """The shared dollar range for the Charts sheet – expenses, collections and balances."""
    values: list[Decimal] = []
    for s in project.scenarios:
        if s.name in names:
            try:
                for y in run(project.baseline, s).years:
                    values += [y.expenses, y.total_from_owners, y.ending_balance]
            except InvalidInputs:
                return None
    return (min(values), max(values)) if values else None


def _download_name(name: str, suffix: str) -> str:
    """Content-Disposition for a download named after the project, safe in any header."""
    ascii_name = re.sub(r"[^A-Za-z0-9 ._()-]", "", name).strip() or "project"
    visible = "".join(ch for ch in name if unicodedata.category(ch) not in ("Cc", "Cf"))
    utf8 = url_quote(re.sub(r"[/\\\"]", "", visible) or "project")
    return f"attachment; filename=\"{ascii_name}{suffix}\"; filename*=UTF-8''{utf8}{suffix}"


# ---------------------------------------------------------------- middleware


class BodyLimit:
    """Refuse a request body over the limit – by Content-Length up front, and by counting
    while it streams, so nothing larger is ever held in memory."""

    def __init__(self, app: ASGIApp, limit: int) -> None:
        self.app, self.limit = app, limit

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        length = dict(scope["headers"]).get(b"content-length")
        if length is not None and (not length.isdigit() or int(length) > self.limit):
            await _too_large(send)
            return
        seen, over = 0, False

        async def counted() -> Message:
            nonlocal seen, over
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b""))
                if seen > self.limit:
                    # end the body here – the app sees a dropped connection and stops reading
                    over = True
                    return {"type": "http.disconnect"}
            return message

        async def unless_over(message: Message) -> None:
            if not over:  # the app's reply to a cut-off body is replaced by the 413 below
                await send(message)

        try:
            await self.app(scope, counted, unless_over)
        except Exception:
            if not over:
                raise
        if over:  # a chunked upload that grew past the limit
            await _too_large(send)


async def _too_large(send: Send) -> None:
    body = b'{"message": "the upload is larger than this app accepts", "problems": []}'
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [(b"content-type", b"application/json")],
        }
    )
    await send({"type": "http.response.body", "body": body})


# ---------------------------------------------------------------- the app


def create_app(
    store: ProjectStore,
    token: str,
    static_dir: Path | None,
    on_restart: Callable[[], None] | None = None,
) -> FastAPI:
    """The app. `on_restart`, given by the launcher, stops this server so the launcher starts a
    fresh one; without it the app cannot restart itself."""
    app = FastAPI(title="HOAForecaster", docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def guard(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.url.path.startswith("/api/"):
            sent = request.headers.get(TOKEN_HEADER, "")
            if not secrets.compare_digest(sent.encode(), token.encode()):
                return JSONResponse(
                    {"message": "this request did not come from HOAForecaster", "problems": []},
                    status_code=403,
                )
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        else:
            response.headers["Content-Security-Policy"] = CSP
        return response

    app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)
    app.add_middleware(BodyLimit, limit=MAX_BODY_BYTES)

    @app.exception_handler(ApiError)
    async def api_error(_: Request, e: ApiError) -> JSONResponse:
        return JSONResponse({"message": e.message, "problems": e.problems}, status_code=e.status)

    @app.exception_handler(StoreError)
    async def store_error(_: Request, e: StoreError) -> JSONResponse:
        statuses = {NotFound: 404, Conflict: 409, ReadOnly: 409, BadProjectFile: 422, Unusable: 422}
        status = statuses.get(type(e), 503)
        return JSONResponse({"message": str(e), "problems": []}, status_code=status)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, e: StarletteHTTPException) -> JSONResponse:
        messages = {404: "no such address", 405: "that action is not available here"}
        message = messages.get(e.status_code, "the request could not be handled")
        return JSONResponse({"message": message, "problems": []}, status_code=e.status_code)

    @app.exception_handler(Exception)
    async def unexpected(_: Request, __: Exception) -> JSONResponse:
        return JSONResponse(
            {"message": "something went wrong – the details are in the server log", "problems": []},
            status_code=500,
        )

    async def body_json(request: Request) -> dict[str, Any]:
        data = await request.body()
        if len(data) > MAX_JSON_BYTES:
            raise ApiError(413, "the request is larger than 5 MB")
        if request.headers.get("content-type", "").split(";")[0].strip() != "application/json":
            raise ApiError(415, "send the request as JSON")
        try:
            body = await request.json()
        except (ValueError, RecursionError):
            raise ApiError(400, "the request is not readable JSON") from None
        if not isinstance(body, dict):
            raise ApiError(400, "the request should be a JSON object")
        return body

    def parse_project(raw: Any) -> Project:
        if not isinstance(raw, dict):
            raise ApiError(422, "the project is missing")
        try:
            return project_from_dict(raw)
        except ProjectFormatError as e:
            raise ApiError(422, str(e)) from None

    def revision(raw: Any) -> int:
        if not isinstance(raw, int) or isinstance(raw, bool) or raw < 1:
            raise ApiError(422, "the request must say which revision it started from")
        return raw

    # ------------------------------------------------------------ projects

    @app.get("/api/projects")
    def list_projects() -> dict[str, Any]:
        summaries, unreadable = store.list_projects()
        return {"projects": to_json(summaries), "unreadable": unreadable}

    @app.post("/api/projects", status_code=201)
    async def create_project(request: Request) -> dict[str, Any]:
        """A project as sent, or – given only a name – a blank one with the spec's defaults."""
        body = await body_json(request)
        if "project" in body:
            return stored_json(store.create(parse_project(body.get("project"))))
        name = body.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ApiError(422, "a new project needs a name")
        try:
            project = blank_project(name.strip(), date.today())
        except ProjectFormatError as e:
            raise ApiError(422, str(e)) from None
        return stored_json(store.create(project))

    @app.get("/api/about")
    def about() -> dict[str, Any]:
        return {
            "data_folder": str(store.root),
            "version": version("hoaforecaster"),
            "can_restart": on_restart is not None,
        }

    @app.post("/api/restart", status_code=202)
    def restart() -> JSONResponse:
        """Stop this server so the launcher starts a fresh one – after this answer is sent."""
        if on_restart is None:
            raise ApiError(409, "this copy of the app cannot restart itself – start it again")
        return JSONResponse(
            {"restarting": True}, status_code=202, background=BackgroundTask(on_restart)
        )

    @app.get("/api/projects/{project_id}")
    def get_project(project_id: str) -> dict[str, Any]:
        return stored_json(store.get(project_id))

    @app.put("/api/projects/{project_id}")
    async def save_project(project_id: str, request: Request) -> dict[str, Any]:
        body = await body_json(request)
        project = parse_project(body.get("project"))
        return stored_json(store.save(project_id, project, revision(body.get("base_revision"))))

    @app.post("/api/projects/{project_id}/adopt")
    async def adopt(project_id: str, request: Request) -> dict[str, Any]:
        """Adopt a saved scenario as the board's plan (spec 5.2)."""
        body = await body_json(request)
        name, note, when = body.get("name"), body.get("note", ""), body.get("date")
        if not isinstance(name, str) or not isinstance(note, str) or not isinstance(when, str):
            raise ApiError(422, "an adoption needs the scenario's name, a date and a note")
        try:
            adopted_on = adoption_date(when)
        except ValueError:
            raise ApiError(422, "the adoption date is not a date") from None
        if len(note) > MAX_NOTE or any(ord(c) < 32 and c not in "\t\n\r" for c in note):
            raise ApiError(422, "the adoption note is too long or holds control characters")
        stored = store.adopt(
            project_id, name, adopted_on, note, revision(body.get("base_revision"))
        )
        return stored_json(stored)

    @app.post("/api/projects/{project_id}/unadopt")
    async def unadopt(project_id: str, request: Request) -> dict[str, Any]:
        """Un-adopt the current adopted plan (spec 5.2)."""
        body = await body_json(request)
        return stored_json(store.unadopt(project_id, revision(body.get("base_revision"))))

    @app.delete("/api/projects/{project_id}", status_code=204)
    def delete_project(project_id: str) -> Response:
        store.delete(project_id)
        return Response(status_code=204)

    @app.get("/api/projects/{project_id}/results")
    def project_results(project_id: str) -> dict[str, Any]:
        stored = store.get(project_id)
        # every scenario still gets its own outcome – an adopted plan runs on its frozen
        # baseline, whatever is wrong with today's
        problems = validate_baseline(stored.project.baseline)
        return {"baseline_problems": problems, "scenarios": _results(stored.project)}

    @app.post("/api/projects/{project_id}/baseline-impact")
    async def baseline_impact(project_id: str, request: Request) -> dict[str, Any]:
        """Which saved scenarios a baseline edit would change (spec 7.1), before saving it.

        `scenarios`, when sent, are the scenarios exactly as the save will store them (for
        example with typed dues stretched to a new horizon); each is compared with the saved
        scenario of the same name against the saved baseline."""
        body = await body_json(request)
        stored = store.get(project_id)
        try:
            baseline = baseline_from_dict(body.get("baseline") or {})
            sent = body.get("scenarios")
            proposed = (
                [scenario_from_dict(s) for s in sent]
                if isinstance(sent, list)
                else list(stored.project.scenarios)
            )
        except ProjectFormatError as e:
            raise ApiError(422, str(e)) from None
        problems = validate_baseline(baseline)
        if problems:
            raise ApiError(422, "the baseline has problems", problems)
        saved = {s.name: s for s in stored.project.scenarios}
        changed: list[str] = []
        unchanged: list[str] = []
        invalid: list[str] = []
        for s in proposed:
            if validate_run(baseline, s):
                invalid.append(s.name)
                continue
            after = run(baseline, s)
            try:
                before = run(stored.project.baseline, saved[s.name])
            except (InvalidInputs, KeyError):
                changed.append(s.name)  # it could not be worked out before, or is new
                continue
            (unchanged if figures(before) == figures(after) else changed).append(s.name)
        return {"changed": changed, "unchanged": unchanged, "invalid": invalid}

    # ------------------------------------------------------------ live results

    @app.post("/api/run")
    async def run_scenario(request: Request) -> dict[str, Any]:
        """One scenario against a baseline, for the editors' live results (spec 7.2)."""
        body = await body_json(request)
        try:
            baseline = baseline_from_dict(body.get("baseline") or {})
            scenario = scenario_from_dict(body.get("scenario") or {})
        except ProjectFormatError as e:
            raise ApiError(422, str(e)) from None
        try:
            return result_json(run(baseline, scenario))
        except InvalidInputs as e:
            raise ApiError(422, "the inputs have problems", e.problems) from None

    # ------------------------------------------------------------ drafts

    @app.get("/api/projects/{project_id}/drafts")
    def get_drafts(project_id: str) -> dict[str, Any]:
        store.get(project_id)
        return {"drafts": to_json(store.get_drafts(project_id))}

    @app.put("/api/projects/{project_id}/drafts", status_code=204)
    async def save_draft(project_id: str, request: Request) -> Response:
        body = await body_json(request)
        edits, screen = body.get("edits"), body.get("screen")
        if not isinstance(edits, dict) or not isinstance(screen, str):
            raise ApiError(422, "a draft must name its screen and hold a set of edits")
        store.save_draft(project_id, screen, edits, revision(body.get("base_revision")))
        return Response(status_code=204)

    @app.delete("/api/projects/{project_id}/drafts", status_code=204)
    def discard_draft(project_id: str, screen: str | None = None) -> Response:
        """One screen's draft with `?screen=`, otherwise every draft of the project."""
        store.get(project_id)
        store.discard_draft(project_id, screen)
        return Response(status_code=204)

    # ------------------------------------------------------------ export and import

    @app.get("/api/projects/{project_id}/export.json")
    def export_project(project_id: str) -> Response:
        stored = store.get(project_id)
        return Response(
            store.export_bytes(project_id),
            media_type="application/json",
            headers={"Content-Disposition": _download_name(stored.project.name, ".json")},
        )

    @app.get("/api/projects/{project_id}/export.xlsx")
    def export_xlsx(project_id: str, scenario: list[str] = Query(default=[])) -> Response:  # noqa: B008
        stored = store.get(project_id)
        project = stored.project
        problems = validate_baseline(project.baseline)
        if problems:
            raise ApiError(422, "fix the baseline before exporting", problems)
        names = scenario or [s.name for s in project.scenarios]
        try:
            data = export_workbook(project, None, names, dollar_axis(project, names))
        except ValueError as e:
            raise ApiError(422, str(e)) from None
        return Response(
            data,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": _download_name(project.name, ".xlsx")},
        )

    @app.post("/api/import/project", status_code=201)
    async def import_project(request: Request) -> dict[str, Any]:
        data = await request.body()
        return stored_json(store.import_bytes(data))

    @app.post("/api/import/workbook", status_code=201)
    async def import_workbook(request: Request) -> dict[str, Any]:
        data = await request.body()  # held in memory only; BodyLimit has capped it
        try:
            project = read_workbook(data)
        except WorkbookFormatError as e:
            raise ApiError(422, str(e)) from None
        return stored_json(store.create(project))

    # ------------------------------------------------------------ the front end

    if static_dir is not None:
        page = (
            (static_dir / "index.html")
            .read_text(encoding="utf-8")
            .replace(TOKEN_PLACEHOLDER, token)
        )
        # Every file of the build, listed once at start-up. A request is served only on an
        # exact match, so no text from a request ever reaches the file system – not "..",
        # not a drive letter, not a Windows network path.
        files = {
            f.relative_to(static_dir).as_posix(): f
            for f in static_dir.rglob("*")
            if f.is_file() and f.name != "index.html"
        }

        @app.get("/{path:path}", include_in_schema=False)
        def front_end(path: str) -> Response:
            if path.startswith("api/"):
                raise ApiError(404, "no such address")
            if path in files:
                return FileResponse(files[path])
            # every other address is a screen of the single-page app – serve it the token
            return HTMLResponse(page, headers={"Cache-Control": "no-store"})

    return app
