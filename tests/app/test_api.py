"""The local HTTP API (spec sections 7, 8 and the security review's server rules)."""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from io import BytesIO
from pathlib import Path
from typing import Any

import openpyxl
import pytest
from fastapi.testclient import TestClient

from hoa_app import api as api_module
from hoa_app.api import TOKEN_HEADER, TOKEN_PLACEHOLDER, create_app
from hoa_engine import project_from_dict, project_to_dict
from hoa_store.store import ProjectStore
from hoa_workbook.export import export_workbook

DEMO_FILE = Path(__file__).resolve().parents[2] / "demo" / "fixtures" / "project.json"
DEMO_RAW = json.loads(DEMO_FILE.read_text(encoding="utf-8"))
DEMO = project_from_dict(DEMO_RAW)
TOKEN = "test-token"


@pytest.fixture
def store(tmp_path: Path) -> ProjectStore:
    return ProjectStore(tmp_path / "data")


@pytest.fixture
def static(tmp_path: Path) -> Path:
    web = tmp_path / "dist"
    (web / "assets").mkdir(parents=True)
    (web / "index.html").write_text(
        f'<meta name="hoa-token" content="{TOKEN_PLACEHOLDER}"><div id="root"></div>',
        encoding="utf-8",
    )
    (web / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    return web


@pytest.fixture
def client(store: ProjectStore, static: Path) -> TestClient:
    app = create_app(store, TOKEN, static)
    return TestClient(app, base_url="http://127.0.0.1:8765", headers={TOKEN_HEADER: TOKEN})


@pytest.fixture
def demo_id(client: TestClient) -> str:
    response = client.post("/api/projects", json={"project": DEMO_RAW})
    assert response.status_code == 201
    return str(response.json()["id"])


# ---------------------------------------------------------------- protection


def test_api_calls_without_the_launch_token_are_refused(client: TestClient) -> None:
    for headers in ({}, {TOKEN_HEADER: "guess"}):
        response = client.get("/api/projects", headers={TOKEN_HEADER: ""} | headers)
        assert response.status_code == 403
        assert "did not come from HOAForecaster" in response.json()["message"]


def test_requests_for_other_host_names_are_refused(store: ProjectStore) -> None:
    rebound = TestClient(create_app(store, TOKEN, None), base_url="http://evil.example:8765")
    assert rebound.get("/api/projects", headers={TOKEN_HEADER: TOKEN}).status_code == 400


def test_api_responses_are_not_cached_or_sniffed(client: TestClient) -> None:
    response = client.get("/api/projects")
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_oversized_bodies_are_refused_before_they_are_read(
    store: ProjectStore, static: Path
) -> None:
    small = TestClient(
        api_module.BodyLimit(create_app(store, TOKEN, static), limit=100),
        base_url="http://127.0.0.1:8765",
        headers={TOKEN_HEADER: TOKEN},
    )
    response = small.post("/api/projects", json={"project": DEMO_RAW})
    assert response.status_code == 413
    response = small.post("/api/projects", content=b"x", headers={"Content-Length": "nope"})
    assert response.status_code == 413


def test_json_endpoints_need_json(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    assert (
        client.post("/api/run", content=b"{}", headers={"Content-Type": "text/plain"}).status_code
        == 415
    )
    response = client.post(
        "/api/run", content=b"{oops", headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 400
    assert client.post("/api/run", json=[1]).status_code == 400
    monkeypatch.setattr(api_module, "MAX_JSON_BYTES", 10)
    assert client.post("/api/run", json={"baseline": {}}).status_code == 413


def test_unexpected_failures_return_a_plain_message_not_a_traceback(
    store: ProjectStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_: object) -> None:
        raise RuntimeError("secret internals")

    monkeypatch.setattr(store, "list_projects", boom)
    app = create_app(store, TOKEN, None)
    client = TestClient(
        app,
        base_url="http://127.0.0.1",
        headers={TOKEN_HEADER: TOKEN},
        raise_server_exceptions=False,
    )
    response = client.get("/api/projects")
    assert response.status_code == 500
    assert "secret" not in response.text


# ---------------------------------------------------------------- projects


def test_project_lifecycle(client: TestClient, demo_id: str) -> None:
    listed = client.get("/api/projects").json()
    assert [p["id"] for p in listed["projects"]] == [demo_id]
    stored = client.get(f"/api/projects/{demo_id}").json()
    assert stored["revision"] == 1 and stored["project"]["name"] == DEMO.name

    edited = {**stored["project"], "notes": "Edited"}
    saved = client.put(f"/api/projects/{demo_id}", json={"project": edited, "base_revision": 1})
    assert saved.status_code == 200 and saved.json()["revision"] == 2

    stale = client.put(f"/api/projects/{demo_id}", json={"project": edited, "base_revision": 1})
    assert stale.status_code == 409 and "saved elsewhere" in stale.json()["message"]

    assert client.delete(f"/api/projects/{demo_id}").status_code == 204
    assert client.get(f"/api/projects/{demo_id}").status_code == 404


@pytest.mark.parametrize(
    ("body", "status", "message"),
    [
        ({}, 422, "a new project needs a name"),
        ({"project": None}, 422, "the project is missing"),
        ({"project": {"name": "x"}}, 422, "missing 'baseline'"),
    ],
)
def test_bad_projects_are_refused(client: TestClient, body: Any, status: int, message: str) -> None:
    response = client.post("/api/projects", json=body)
    assert response.status_code == status and message in response.json()["message"]


def test_a_save_must_name_its_revision(client: TestClient, demo_id: str) -> None:
    for base in (None, "1", True):
        response = client.put(
            f"/api/projects/{demo_id}", json={"project": DEMO_RAW, "base_revision": base}
        )
        assert response.status_code == 422 and "which revision" in response.json()["message"]


def test_ids_that_are_not_ours_are_not_found(client: TestClient) -> None:
    assert client.get("/api/projects/..%2F..%2Fsecret").status_code == 404
    assert client.get("/api/projects/0123456789ab").status_code == 404


# ---------------------------------------------------------------- results


def test_project_results_cover_every_scenario(client: TestClient, demo_id: str) -> None:
    body = client.get(f"/api/projects/{demo_id}/results").json()
    assert body["baseline_problems"] == []
    assert set(body["scenarios"]) == {s.name for s in DEMO.scenarios}
    first = body["scenarios"]["Dues only"]["result"]
    assert first["summary"]["low_years"] == 1
    assert isinstance(first["years"][0]["ending_balance"], str)  # exact decimal strings
    assert {"description", "amount", "nominal", "source"} <= set(
        first["years"][0]["expense_lines"][0]
    )


def test_results_report_problems_instead_of_failing(
    client: TestClient, store: ProjectStore
) -> None:
    raw = json.loads(json.dumps(DEMO_RAW))
    raw["scenarios"][0]["dues"]["overrides"] = {"2099": "5"}  # outside the horizon
    created = client.post("/api/projects", json={"project": raw}).json()
    body = client.get(f"/api/projects/{created['id']}/results").json()
    assert "outside" in body["scenarios"][raw["scenarios"][0]["name"]]["problems"][0]

    raw["baseline"]["units"] = 0
    bad = client.post("/api/projects", json={"project": raw}).json()
    assert client.get(f"/api/projects/{bad['id']}/results").json()["baseline_problems"]


def test_live_run_for_the_editors(client: TestClient) -> None:
    body = {"baseline": DEMO_RAW["baseline"], "scenario": DEMO_RAW["scenarios"][0]}
    result = client.post("/api/run", json=body).json()
    assert len(result["years"]) == DEMO.baseline.end_year - DEMO.baseline.start_year + 1

    bad = {**body, "baseline": {**DEMO_RAW["baseline"], "units": 0}}
    response = client.post("/api/run", json=bad)
    assert response.status_code == 422 and "at least one unit" in response.json()["problems"][0]
    assert client.post("/api/run", json={"baseline": {}}).status_code == 422


def test_baseline_impact_names_the_scenarios_that_would_change(
    client: TestClient, demo_id: str
) -> None:
    same = client.post(
        f"/api/projects/{demo_id}/baseline-impact", json={"baseline": DEMO_RAW["baseline"]}
    )
    assert same.json()["changed"] == [] and len(same.json()["unchanged"]) == len(DEMO.scenarios)

    more_units = {**DEMO_RAW["baseline"], "units": 30}
    moved = client.post(
        f"/api/projects/{demo_id}/baseline-impact", json={"baseline": more_units}
    ).json()
    # an adopted plan keeps its frozen baseline, so it never changes
    working = [s.name for s in DEMO.scenarios if s.adoption is None]
    assert sorted(moved["changed"]) == sorted(working)

    shorter = {**DEMO_RAW["baseline"], "end_year": DEMO.baseline.start_year + 4}
    cut = client.post(f"/api/projects/{demo_id}/baseline-impact", json={"baseline": shorter}).json()
    assert set(cut["changed"]) | set(cut["invalid"]) == set(working)


def test_baseline_impact_refuses_a_broken_baseline(client: TestClient, demo_id: str) -> None:
    bad = {**DEMO_RAW["baseline"], "units": 0}
    response = client.post(f"/api/projects/{demo_id}/baseline-impact", json={"baseline": bad})
    assert response.status_code == 422 and response.json()["problems"]
    unreadable = client.post(
        f"/api/projects/{demo_id}/baseline-impact", json={"baseline": {"x": 1}}
    )
    assert unreadable.status_code == 422


def test_baseline_impact_spares_a_scenario_with_its_own_value(client: TestClient) -> None:
    raw = json.loads(json.dumps(DEMO_RAW))
    raw["scenarios"][0]["changes"] = {"values": {"interest_rate": "0.03"}}
    raw["scenarios"][1]["changes"] = {"values": {"end_year": DEMO.baseline.end_year + 1}}
    created = client.post("/api/projects", json={"project": raw}).json()
    new_rate = {**DEMO_RAW["baseline"], "interest_rate": "0.02"}
    impact = client.post(
        f"/api/projects/{created['id']}/baseline-impact", json={"baseline": new_rate}
    ).json()
    first, second = (s["name"] for s in raw["scenarios"][:2])
    assert first in impact["unchanged"]  # it keeps its own rate
    # the second runs a year past the baseline and has no Fully Funded Balance for it
    assert second in impact["invalid"]


def test_baseline_impact_counts_a_scenario_that_now_runs_as_changed(client: TestClient) -> None:
    raw = json.loads(json.dumps(DEMO_RAW))
    raw["baseline"]["units"] = 0  # every scenario fails against the saved baseline
    created = client.post("/api/projects", json={"project": raw}).json()
    fixed = client.post(
        f"/api/projects/{created['id']}/baseline-impact", json={"baseline": DEMO_RAW["baseline"]}
    ).json()
    assert len(fixed["changed"]) == len([s for s in DEMO.scenarios if s.adoption is None])


# ---------------------------------------------------------------- drafts


def test_drafts_round_trip_per_screen_and_are_discarded(client: TestClient, demo_id: str) -> None:
    url = f"/api/projects/{demo_id}/drafts"
    assert client.get(url).json() == {"drafts": {}}
    body = {"screen": "baseline", "edits": {"name": ""}, "base_revision": 1}
    assert client.put(url, json=body).status_code == 204
    other = {"screen": "scenario:Dues only", "edits": {"x": 1}, "base_revision": 1}
    assert client.put(url, json=other).status_code == 204
    drafts = client.get(url).json()["drafts"]
    assert drafts["baseline"]["edits"] == {"name": ""} and drafts["baseline"]["base_revision"] == 1
    assert client.delete(url, params={"screen": "baseline"}).status_code == 204
    assert set(client.get(url).json()["drafts"]) == {"scenario:Dues only"}
    assert client.delete(url).status_code == 204
    assert client.get(url).json() == {"drafts": {}}


def test_bad_and_stale_drafts_are_refused(client: TestClient, demo_id: str) -> None:
    url = f"/api/projects/{demo_id}/drafts"
    bad = client.put(url, json={"screen": "baseline", "edits": [1], "base_revision": 1})
    assert bad.status_code == 422
    nameless = client.put(url, json={"edits": {}, "base_revision": 1})
    assert nameless.status_code == 422
    client.put(f"/api/projects/{demo_id}", json={"project": DEMO_RAW, "base_revision": 1})
    stale = client.put(url, json={"screen": "baseline", "edits": {}, "base_revision": 1})
    assert stale.status_code == 409
    assert client.get("/api/projects/0123456789ab/drafts").status_code == 404


def test_baseline_impact_judges_the_scenarios_as_they_will_be_saved(
    client: TestClient, demo_id: str
) -> None:
    longer = {**DEMO_RAW["baseline"], "end_year": DEMO.baseline.end_year + 2}
    longer["ffb"] = {
        **longer["ffb"],
        str(DEMO.baseline.end_year + 2): "1",
        str(DEMO.baseline.end_year + 3): "1",
    }
    url = f"/api/projects/{demo_id}/baseline-impact"
    as_saved = client.post(url, json={"baseline": longer}).json()
    assert "Hold then catch up" in as_saved["invalid"]  # typed dues stop short of the new end
    stretched = json.loads(json.dumps(DEMO_RAW["scenarios"]))
    hold = next(s for s in stretched if s["name"] == "Hold then catch up")
    last = hold["dues"]["explicit"][str(DEMO.baseline.end_year)]
    for y in (DEMO.baseline.end_year + 1, DEMO.baseline.end_year + 2):
        hold["dues"]["explicit"][str(y)] = last
    stretched.append({**stretched[0], "name": "Brand new"})
    proposed = client.post(url, json={"baseline": longer, "scenarios": stretched}).json()
    assert proposed["invalid"] == []
    assert "Hold then catch up" in proposed["changed"] and "Brand new" in proposed["changed"]
    bad = client.post(url, json={"baseline": longer, "scenarios": [{"name": "x"}]})
    assert bad.status_code == 422


# ---------------------------------------------------------------- export and import


def test_project_file_export_and_import(client: TestClient, demo_id: str) -> None:
    exported = client.get(f"/api/projects/{demo_id}/export.json")
    assert exported.status_code == 200
    assert (
        'filename="Maple Row Condominiums (fictional demo).json"'
        in exported.headers["Content-Disposition"]
    )
    imported = client.post("/api/import/project", content=exported.content)
    assert imported.status_code == 201 and imported.json()["project"] == project_to_dict(DEMO)
    bad = client.post("/api/import/project", content=b"{nope")
    assert bad.status_code == 422 and "not a readable project file" in bad.json()["message"]


def test_workbook_export_carries_the_chosen_scenarios_and_a_shared_scale(
    client: TestClient, demo_id: str
) -> None:
    response = client.get(
        f"/api/projects/{demo_id}/export.xlsx?scenario=Dues only&scenario=Steady increase"
    )
    assert response.status_code == 200
    wb = openpyxl.load_workbook(BytesIO(response.content))
    assert wb.sheetnames[-2:] == ["Dues only", "Steady increase"]
    assert "the same dollar scale" in str(wb["Charts"]["A2"].value)
    everything = client.get(f"/api/projects/{demo_id}/export.xlsx")
    assert len(openpyxl.load_workbook(BytesIO(everything.content)).sheetnames) == 5 + len(
        DEMO.scenarios
    )
    unknown = client.get(f"/api/projects/{demo_id}/export.xlsx?scenario=Nope")
    assert unknown.status_code == 422 and "no scenario named" in unknown.json()["message"]


def test_workbook_export_needs_a_valid_baseline_and_skips_the_scale_for_bad_scenarios(
    client: TestClient,
) -> None:
    raw = json.loads(json.dumps(DEMO_RAW))
    raw["scenarios"][0]["dues"]["overrides"] = {"2099": "5"}
    created = client.post("/api/projects", json={"project": raw}).json()
    response = client.get(f"/api/projects/{created['id']}/export.xlsx")
    assert response.status_code == 200
    wb = openpyxl.load_workbook(BytesIO(response.content))
    assert "each its own dollar scale" in str(wb["Charts"]["A2"].value)

    raw["baseline"]["units"] = 0
    bad = client.post("/api/projects", json={"project": raw}).json()
    assert client.get(f"/api/projects/{bad['id']}/export.xlsx").status_code == 422


def test_workbook_import(client: TestClient) -> None:
    response = client.post("/api/import/workbook", content=export_workbook(DEMO))
    assert response.status_code == 201
    assert project_from_dict(response.json()["project"]) == DEMO  # equal values, not text
    bad = client.post("/api/import/workbook", content=b"not a zip")
    assert bad.status_code == 422 and "not an Excel workbook" in bad.json()["message"]


def test_download_names_survive_any_project_name() -> None:
    header = api_module._download_name('Evil"\r\nName/../é', ".json")
    assert "\r" not in header and "\n" not in header
    assert 'filename="EvilName..' in header and "filename*=UTF-8''" in header
    assert api_module._download_name("???", ".json").startswith(
        'attachment; filename="project.json"'
    )


def test_dollar_axis_is_none_without_scenarios() -> None:
    assert api_module.dollar_axis(DEMO, []) is None


# ---------------------------------------------------------------- the front end


def test_the_page_carries_the_token_and_a_strict_policy(client: TestClient) -> None:
    for path in ("/", "/projects/abc", "/compare"):
        page = client.get(path, headers={TOKEN_HEADER: ""})
        assert page.status_code == 200
        assert f'content="{TOKEN}"' in page.text and TOKEN_PLACEHOLDER not in page.text
        assert "default-src 'self'" in page.headers["Content-Security-Policy"]


def test_static_files_are_served_but_nothing_outside_the_build(client: TestClient) -> None:
    assert client.get("/assets/app.js").text == "console.log(1)"
    escape = client.get("/..%2F..%2Fdata%2Fprojects")
    assert TOKEN_PLACEHOLDER not in escape.text and "console" not in escape.text
    assert client.get("/api/nothing-here").status_code == 404


def test_without_a_build_only_the_api_is_served(store: ProjectStore) -> None:
    client = TestClient(create_app(store, TOKEN, None), base_url="http://127.0.0.1")
    assert client.get("/").status_code == 404


# ---------------------------------------------------------------- review follow-ups


@pytest.mark.parametrize(
    "path",
    ["/%5c%5c192.0.2.1%5cshare%5cx", "//192.0.2.1/share/x", "/C:%5cWindows%5cwin.ini", "/../x"],
)
def test_no_request_reaches_the_file_system(client: TestClient, path: str) -> None:
    started = time.monotonic()
    page = client.get(path)
    assert time.monotonic() - started < 2  # no network share was contacted
    assert f'content="{TOKEN}"' in page.text  # just the app's page


def test_the_page_always_carries_the_token_and_is_never_cached(client: TestClient) -> None:
    page = client.get("/index.html")
    assert f'content="{TOKEN}"' in page.text and TOKEN_PLACEHOLDER not in page.text
    assert page.headers["Cache-Control"] == "no-store"


def test_framework_errors_use_the_apps_shape(client: TestClient, store: ProjectStore) -> None:
    wrong_method = client.patch("/api/projects")
    assert wrong_method.status_code == 405
    assert wrong_method.json() == {"message": "that action is not available here", "problems": []}
    api_only = TestClient(create_app(store, TOKEN, None), base_url="http://127.0.0.1")
    missing = api_only.get("/api/nothing", headers={TOKEN_HEADER: TOKEN})
    assert missing.json() == {"message": "no such address", "problems": []}


def test_a_blank_project_from_the_specs_defaults(client: TestClient) -> None:
    created = client.post("/api/projects", json={"name": "  New building  "})
    assert created.status_code == 201
    project = created.json()["project"]
    b = project["baseline"]
    assert project["name"] == "New building"
    assert b["end_year"] - b["start_year"] == 13
    assert (b["expense_inflation"], b["interest_rate"], b["target"]) == ("0.03", "0.02", "0.7")
    for name in (None, "", "   ", 5):
        assert client.post("/api/projects", json={"name": name}).status_code == 422
    bad = client.post("/api/projects", json={"name": "bell\u0007"})
    assert bad.status_code == 422 and "control characters" in bad.json()["message"]


def test_about_names_the_data_folder(client: TestClient, store: ProjectStore) -> None:
    about = client.get("/api/about").json()
    assert about["data_folder"] == str(store.root) and about["version"]


def test_revisions_are_positive(client: TestClient, demo_id: str) -> None:
    body = {"screen": "baseline", "edits": {}, "base_revision": 0}
    assert client.put(f"/api/projects/{demo_id}/drafts", json=body).status_code == 422


def test_editing_only_an_expense_description_changes_no_scenario(
    client: TestClient, demo_id: str
) -> None:
    baseline = json.loads(json.dumps(DEMO_RAW["baseline"]))
    baseline["expense_lines"][0]["description"] = "Renamed"
    baseline["expense_lines"][0]["source"] = "Another study"
    impact = client.post(f"/api/projects/{demo_id}/baseline-impact", json={"baseline": baseline})
    assert impact.json()["changed"] == []


def test_download_names_drop_invisible_direction_marks() -> None:
    header = api_module._download_name("invoice\u202egpj.exe", ".json")
    assert "%E2%80%AE" not in header  # U+202E right-to-left override


def test_a_streamed_upload_over_the_limit_is_cut_off(tmp_path: Path) -> None:
    app = api_module.BodyLimit(create_app(ProjectStore(tmp_path), "t", None), limit=100)
    client = TestClient(app, base_url="http://127.0.0.1", headers={TOKEN_HEADER: "t"})

    def chunks() -> Iterator[bytes]:  # no Content-Length – sent chunked
        for _ in range(10):
            yield b"x" * 50

    with client:  # also runs the app's startup and shutdown
        response = client.post("/api/import/project", content=chunks())
    assert response.status_code == 413


# ---------------------------------------------------------------- adopted plans (spec 5.2)


def test_adopting_and_un_adopting_a_plan(client: TestClient, demo_id: str) -> None:
    body = {"name": "Dues only", "date": "2026-11-03", "note": "Vote", "base_revision": 1}
    adopted = client.post(f"/api/projects/{demo_id}/adopt", json=body)
    assert adopted.status_code == 200
    plan = adopted.json()["project"]["scenarios"][0]["adoption"]
    # the demo already has an adopted plan, so this one is adopted second
    assert (plan["date"], plan["note"], plan["sequence"]) == ("2026-11-03", "Vote", 2)
    again = client.post(f"/api/projects/{demo_id}/adopt", json={**body, "base_revision": 2})
    assert again.status_code == 409 and "already an adopted plan" in again.json()["message"]
    project = adopted.json()["project"]
    project["scenarios"][0]["description"] = "changed"
    edit = client.put(f"/api/projects/{demo_id}", json={"project": project, "base_revision": 2})
    assert edit.status_code == 409 and "cannot be changed" in edit.json()["message"]
    back = client.post(f"/api/projects/{demo_id}/unadopt", json={"base_revision": 2})
    assert back.json()["project"]["scenarios"][0]["adoption"] is None


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"date": "the 3rd"}, "not a date"),
        ({"date": "2026-W45-2"}, "not a date"),
        ({"date": None}, "needs the scenario's name, a date and a note"),
        ({"note": "x" * 2001}, "too long or holds control characters"),
        ({"note": "bell\x07"}, "too long or holds control characters"),
    ],
)
def test_adoption_requests_are_checked(
    client: TestClient, demo_id: str, change: dict[str, object], message: str
) -> None:
    body = {"name": "Dues only", "date": "2026-11-03", "note": "", "base_revision": 1, **change}
    response = client.post(f"/api/projects/{demo_id}/adopt", json=body)
    assert response.status_code == 422 and message in response.json()["message"]


def test_an_adopted_plan_still_has_figures_when_the_baseline_has_problems(
    client: TestClient, demo_id: str
) -> None:
    body = {"name": "Dues only", "date": "2026-11-03", "note": "", "base_revision": 1}
    project = client.post(f"/api/projects/{demo_id}/adopt", json=body).json()["project"]
    project["baseline"]["units"] = 0
    client.put(f"/api/projects/{demo_id}", json={"project": project, "base_revision": 2})
    results = client.get(f"/api/projects/{demo_id}/results").json()
    assert results["baseline_problems"] == ["there must be at least one unit"]
    assert "result" in results["scenarios"]["Dues only"]
    assert "problems" in results["scenarios"]["Two-part assessment"]
