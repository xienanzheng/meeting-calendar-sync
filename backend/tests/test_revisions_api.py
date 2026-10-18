import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from mcs import service
from mcs.api.app import create_app
from mcs.config import REPO_ROOT

SAMPLES = REPO_ROOT / "samples"
PDF_A = (SAMPLES / "broker_a_grid.pdf").read_bytes()
PDF_A2 = (SAMPLES / "broker_a_grid_v2.pdf").read_bytes()


@pytest.fixture
def client(settings, tmp_path):
    settings.frontend_dist = tmp_path / "no-dist"
    app = create_app(settings)
    with Session(app.state.engine) as s:
        service.seed_roster(s, SAMPLES / "roster.sample.json")
    with TestClient(app) as c:
        yield c


def upload(client, data=PDF_A, name="broker_a_grid.pdf", **form):
    return client.post("/api/conferences", files={"file": (name, data, "application/pdf")}, data=form)


def pdfs(settings):
    return sorted(p.name for p in settings.uploads_dir.glob("*.pdf"))


def company(detail, name):
    return next(m for m in detail["meetings"] if m["company"] == name)


def test_revised_upload_becomes_a_pending_revision(client, settings):
    a = upload(client).json()
    r = upload(client, PDF_A2, "broker_a_grid_v2.pdf")
    assert r.status_code == 201
    d = r.json()
    assert d["id"] == a["id"] and d["revision_number"] == 1
    rev = d["pending_revision"]
    assert rev["number"] == 2 and rev["pdf_filename"] == "broker_a_grid_v2.pdf"
    assert [c["kind"] for c in rev["changes"]] == ["changed", "changed", "changed", "removed", "added"]
    assert rev["unchanged_count"] == 8
    assert len(pdfs(settings)) == 2
    rev_pdf = client.get(f"/api/revisions/{rev['id']}/pdf")
    assert rev_pdf.content == PDF_A2 and rev_pdf.headers["cache-control"] == "no-cache"


def test_mode_new_forces_a_new_conference(client):
    a = upload(client).json()
    assert upload(client, PDF_A2, "v2.pdf", mode="new").json()["id"] != a["id"]
    assert upload(client, PDF_A2, "v2.pdf", mode="sideways").status_code == 400


def test_apply_all_syncs_and_switches_the_pdf(client, settings):
    a = upload(client).json()
    client.post(f"/api/conferences/{a['id']}/confirm-ready", json={})
    rev = upload(client, PDF_A2, "broker_a_grid_v2.pdf").json()["pending_revision"]
    r = client.post(f"/api/revisions/{rev['id']}/apply", json={})
    assert r.status_code == 200
    d = r.json()
    assert d["pending_revision"] is None and d["revision_number"] == 2
    assert d["last_sync"]["failed"] == 0 and d["last_sync"]["ok"] == 6
    cobalt = company(d, "Cobalt Freight Lines")
    assert (cobalt["start"], cobalt["end"], cobalt["review_state"]) == ("14:30", "15:15", "sent")
    assert company(d, "Atlas Rail Systems")["review_state"] == "sent"
    assert client.get(f"/api/conferences/{a['id']}/pdf").content == PDF_A2
    assert len(pdfs(settings)) == 1
    assert client.post(f"/api/revisions/{rev['id']}/apply", json={}).status_code == 409


def test_apply_some_changes(client):
    a = upload(client).json()
    rev = upload(client, PDF_A2, "v2.pdf").json()["pending_revision"]
    d = client.post(f"/api/revisions/{rev['id']}/apply", json={"accepted": ["c1"]}).json()
    assert company(d, "Cobalt Freight Lines")["start"] == "14:30"
    assert company(d, "Meridian Rail Holdings")["room"] == "TBD"
    assert client.post(f"/api/revisions/{rev['id']}/apply", json={"accepted": ["zz"]}).status_code == 409


def test_discard_keeps_the_original(client, settings):
    a = upload(client).json()
    rev = upload(client, PDF_A2, "v2.pdf").json()["pending_revision"]
    d = client.post(f"/api/revisions/{rev['id']}/discard").json()
    assert d["pending_revision"] is None and d["revision_number"] == 1
    assert len(pdfs(settings)) == 1
    assert client.get(f"/api/conferences/{a['id']}/pdf").content == PDF_A


def test_explicit_revision_upload(client):
    a = upload(client).json()
    r = client.post(f"/api/conferences/{a['id']}/revisions",
                    files={"file": ("v2.pdf", PDF_A2, "application/pdf")})
    assert r.status_code == 201 and r.json()["pending_revision"]["number"] == 2
    bad = client.post(f"/api/conferences/{a['id']}/revisions", files={"file": ("x.pdf", b"", "application/pdf")})
    assert bad.status_code == 400


def test_revision_as_new_conference(client, settings):
    a = upload(client).json()
    rev = upload(client, PDF_A2, "v2.pdf").json()["pending_revision"]
    r = client.post(f"/api/revisions/{rev['id']}/as-new-conference")
    assert r.status_code == 201
    new = r.json()
    assert new["id"] != a["id"] and len(new["meetings"]) == 12
    assert len(client.get("/api/conferences").json()) == 2
    assert len(pdfs(settings)) == 2


def test_delete_conference_removes_revision_pdfs(client, settings):
    a = upload(client).json()
    upload(client, PDF_A2, "v2.pdf")
    assert client.delete(f"/api/conferences/{a['id']}").status_code == 204
    assert pdfs(settings) == []
    assert client.get("/api/revisions/1/pdf").status_code == 404
