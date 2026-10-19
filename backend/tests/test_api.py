import io
import zipfile

import pytest
from fastapi.testclient import TestClient
from icalendar import Calendar
from sqlmodel import Session

from mcs import service
from mcs.api.app import create_app
from mcs.config import REPO_ROOT

SAMPLES = REPO_ROOT / "samples"
PDF_A = (SAMPLES / "broker_a_grid.pdf").read_bytes()


@pytest.fixture
def app(settings, tmp_path):
    settings.frontend_dist = tmp_path / "no-dist"
    application = create_app(settings)
    with Session(application.state.engine) as s:
        service.seed_roster(s, SAMPLES / "roster.sample.json")
    return application


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


def upload(client, data=PDF_A, name="broker_a_grid.pdf", **form):
    return client.post("/api/conferences", files={"file": (name, data, "application/pdf")}, data=form)


def people(client):
    return {a["name"]: a["id"] for a in client.get("/api/roster").json()}


def company(detail, name):
    return next(m for m in detail["meetings"] if m["company"] == name)


def test_health_and_config(client):
    assert client.get("/api/health").json() == {"ok": True}
    cfg = client.get("/api/config").json()
    assert (cfg["extractor"], cfg["calendar_sink"], cfg["ephemeral"]) == ("fake", "ics", False)
    assert cfg["graph"]["configured"] is False


def test_upload_review_and_pdf(client, settings):
    r = upload(client, default_attendee_ids="")
    assert r.status_code == 201, r.text
    d = r.json()
    assert len(d["meetings"]) == 12 and d["skipped_items"] == 0 and d["extractor"] == "fake"
    pdf = client.get(f"/api/conferences/{d['id']}/pdf")
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf"
    assert pdf.headers["cache-control"] == "no-cache"  # an applied revision swaps the file behind this URL
    assert pdf.content.startswith(b"%PDF")
    assert len(list(settings.uploads_dir.glob("*.pdf"))) == 1
    assert [c["name"] for c in client.get("/api/conferences").json()] == ["Industrials Conference 2026"]


@pytest.mark.parametrize("data,name,match", [
    (b"", "a.pdf", "empty"),
    (b"hello, not a pdf", "a.pdf", "PDF"),
    (PDF_A, "a.txt", "PDF"),
])
def test_bad_uploads_store_nothing(client, settings, data, name, match):
    r = upload(client, data=data, name=name)
    assert r.status_code == 400 and match in r.json()["detail"]
    assert list(settings.uploads_dir.glob("*")) == []
    assert client.get("/api/conferences").json() == []


def test_oversized_upload(client, settings):
    settings.max_upload_mb = 1
    r = upload(client, data=b"%PDF" + b"0" * (1024 * 1024))
    assert r.status_code == 400 and "larger than 1 MB" in r.json()["detail"]
    assert list(settings.uploads_dir.glob("*")) == []


def test_extraction_failure_is_502_and_stores_nothing(client, settings):
    r = upload(client, data=b"%PDF-1.4 unknown")
    assert r.status_code == 502 and "sample PDFs" in r.json()["detail"]
    assert list(settings.uploads_dir.glob("*")) == []


@pytest.mark.parametrize("ids", ["abc", "999"])
def test_bad_default_attendees(client, ids):
    assert upload(client, default_attendee_ids=ids).status_code == 400


def test_default_attendees_are_applied(client):
    d = upload(client, default_attendee_ids=str(people(client)["Morgan Diaz"])).json()
    assert all("Morgan Diaz" in [a["name"] for a in m["attendees"]] for m in d["meetings"])


def test_review_verify_send_and_download(settings, tmp_path):
    # Manual send path: auto-sync off so confirm-ready doesn't already send (Task 10A).
    settings.auto_sync = False
    settings.frontend_dist = tmp_path / "no-dist"
    application = create_app(settings)
    with Session(application.state.engine) as s:
        service.seed_roster(s, SAMPLES / "roster.sample.json")
    with TestClient(application) as client:
        d = upload(client).json()
        cid = d["id"]
        tide = company(d, "Tidewater Pumps")
        r = client.post(f"/api/meetings/{tide['id']}/confirm")
        assert r.status_code == 409 and {"no_attendee"} <= {f["code"] for f in r.json()["flags"]}
        d = client.patch(f"/api/meetings/{tide['id']}", json={"attendee_ids": [people(client)["Jordan Lee"]],
                                                              "ignored_names": ["Chris Wong"]}).json()
        assert company(d, "Tidewater Pumps")["flags"] == []
        d = client.post(f"/api/conferences/{cid}/confirm-ready", json={}).json()
        assert d["counts"]["verified"] == 12
        preview = client.post(f"/api/conferences/{cid}/send?dry_run=true").json()
        assert preview["dry_run"] is True and {a["kind"] for a in preview["actions"]} == {"create"}
        done = client.post(f"/api/conferences/{cid}/send?dry_run=false").json()
        assert done["failed_count"] == 0 and done["ok_count"] == len(preview["actions"])
        avery = people(client)["Avery Kim"]
        ics = client.get(f"/api/conferences/{cid}/ics/{avery}")
        assert ics.status_code == 200 and ics.headers["content-type"].startswith("text/calendar")
        assert "attachment" in ics.headers["content-disposition"] and "avery-kim" in ics.headers["content-disposition"]
        assert len(Calendar.from_ical(ics.content).walk("VEVENT")) == 4  # Avery: NWRB, CBFL, KSVC, SMFI
        z = client.get(f"/api/conferences/{cid}/ics.zip")
        assert z.headers["content-type"] == "application/zip"
        assert "avery-kim.ics" in zipfile.ZipFile(io.BytesIO(z.content)).namelist()
        assert client.get(f"/api/conferences/{cid}/send?dry_run=true").status_code == 405
        assert client.post(f"/api/conferences/{cid}/send?dry_run=true").json()["actions"] == []


def test_ics_for_unsent_colleague_is_404(client):
    cid = upload(client).json()["id"]
    assert client.get(f"/api/conferences/{cid}/ics/{people(client)['Avery Kim']}").status_code == 404
    assert client.get(f"/api/conferences/{cid}/ics.zip").status_code == 404


def test_conference_edit_add_delete_meeting(client, settings):
    cid = upload(client).json()["id"]
    assert client.patch(f"/api/conferences/{cid}", json={"timezone": "Eastern"}).status_code == 400
    d = client.patch(f"/api/conferences/{cid}", json={"timezone": "America/Chicago", "name": "Renamed"}).json()
    assert (d["timezone"], d["name"]) == ("America/Chicago", "Renamed")
    r = client.post(f"/api/conferences/{cid}/meetings", json={"company": "Atlas Rail Systems", "date": "2026-11-10",
                                                              "start": "16:00"})
    assert r.status_code == 201 and company(r.json(), "Atlas Rail Systems")["end"] == "16:45"
    mid = company(r.json(), "Atlas Rail Systems")["id"]
    assert client.patch(f"/api/meetings/{mid}", json={"start": "nonsense"}).status_code == 400
    d = client.delete(f"/api/meetings/{mid}").json()
    assert all(m["company"] != "Atlas Rail Systems" for m in d["meetings"])
    assert client.delete(f"/api/conferences/{cid}").status_code == 204
    assert client.get(f"/api/conferences/{cid}").status_code == 404
    assert list(settings.uploads_dir.glob("*")) == []


def test_deleting_an_unsent_broker_meeting_removes_it_from_the_detail(client):
    d = upload(client).json()
    north = company(d, "Northwind Robotics")
    r = client.delete(f"/api/meetings/{north['id']}")
    assert r.status_code == 200
    d = r.json()
    assert all(m["id"] != north["id"] for m in d["meetings"]) and d["counts"]["total"] == 11
    assert all(m["id"] != north["id"] for m in client.get(f"/api/conferences/{d['id']}").json()["meetings"])
    assert client.patch(f"/api/meetings/{north['id']}", json={"room": "X"}).status_code == 404
    assert client.delete(f"/api/meetings/{north['id']}").status_code == 404


def test_meeting_times_accept_the_review_tables_format(client):
    # The source panel's Start/End fields show and send times as the table prints them ("2:30 PM").
    d = upload(client).json()
    mid = d["meetings"][0]["id"]
    for typed, stored in [("2:30 PM", "14:30"), ("2pm", "14:00"), ("9:05 am", "09:05"), ("16:15", "16:15")]:
        d = client.patch(f"/api/meetings/{mid}", json={"start": typed}).json()
        assert next(m for m in d["meetings"] if m["id"] == mid)["start"] == stored
    r = client.patch(f"/api/meetings/{mid}", json={"end": "25:00"})
    assert r.status_code == 400 and "2:30 PM" in r.json()["detail"]


def test_unconfirm(client):
    d = upload(client).json()
    mid = d["meetings"][0]["id"]
    client.post(f"/api/meetings/{mid}/confirm")
    d = client.post(f"/api/meetings/{mid}/unconfirm").json()
    assert d["meetings"][0]["status"] == "draft"


def test_roster_api(client):
    assert client.post("/api/roster", json={"name": "Dup", "email": "avery.kim@example.com"}).status_code == 400
    r = client.post("/api/roster", json={"name": "Casey Fox", "email": "Casey.Fox@example.com", "aliases": ["C. Fox"]})
    assert r.status_code == 201 and r.json()["email"] == "casey.fox@example.com"
    cid = r.json()["id"]
    assert client.patch(f"/api/roster/{cid}", json={"active": False}).json()["active"] is False
    assert client.delete(f"/api/roster/{cid}").status_code == 204
    upload(client)
    assert client.delete(f"/api/roster/{people(client)['Avery Kim']}").status_code == 409


def test_not_found_and_graph_errors(client):
    assert client.get("/api/conferences/999").status_code == 404
    assert client.patch("/api/meetings/999", json={"room": "x"}).status_code == 404
    r = client.post("/api/graph/login")
    assert r.status_code == 400 and "not configured" in r.json()["detail"]
    assert client.get("/api/graph/status").json()["configured"] is False


def test_send_with_unconfigured_graph(settings, tmp_path):
    settings.calendar_sink = "graph"
    settings.frontend_dist = tmp_path / "no-dist"
    with TestClient(create_app(settings)) as c:
        cid = upload(c).json()["id"]
        r = c.post(f"/api/conferences/{cid}/send?dry_run=false")
        assert r.status_code == 400 and "not configured" in r.json()["detail"]


def test_spa_fallback(settings, tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>app</html>")
    (dist / "assets" / "app.js").write_text("console.log(1)")
    settings.frontend_dist = dist
    with TestClient(create_app(settings)) as c:
        assert c.get("/").text == "<html>app</html>"
        assert c.get("/conferences/1").text == "<html>app</html>"
        assert c.get("/assets/app.js").text == "console.log(1)"
        r = c.get("/api/nope")
        assert r.status_code == 404 and "detail" in r.json()
