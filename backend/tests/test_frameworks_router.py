import io

import pytest
from openpyxl import Workbook

from app.iam.models import User
from app.iam.permissions import Role
from app.iam.security import hash_password


async def _seed(db_session, role: Role, email: str) -> User:
    user = User(email=email, name=email, role=role, password_hash=hash_password("pw123456"))
    db_session.add(user)
    await db_session.flush()
    return user


async def _auth(client, email: str) -> dict[str, str]:
    resp = await client.post("/api/auth/login", json={"email": email, "password": "pw123456"})
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _workbook(rows) -> bytes:
    book = Workbook()
    sheet = book.active
    sheet.append(["code", "title", "description", "parent_code", "attributes_json"])
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


GOOD = [["PR", "Protect", "", "", ""], ["PR.AA-01", "Identities", "Body.", "PR", ""]]
BAD = [["PR.AA-01", "Identities", "Body.", "MISSING", ""]]


@pytest.mark.asyncio
async def test_validate_reports_problems_without_writing(client, db_session):
    await _seed(db_session, Role.GRC_LEAD, "lead@example.com")
    headers = await _auth(client, "lead@example.com")
    resp = await client.post(
        "/api/frameworks/validate",
        headers=headers,
        files={"file": ("f.xlsx", _workbook(BAD),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False and body["report"]

    listing = await client.get("/api/frameworks", headers=headers)
    assert listing.json() == []


@pytest.mark.asyncio
async def test_import_then_browse_tree_coverage_and_gaps(client, db_session):
    await _seed(db_session, Role.GRC_LEAD, "lead@example.com")
    headers = await _auth(client, "lead@example.com")
    resp = await client.post(
        "/api/frameworks/import",
        headers=headers,
        data={"key": "csf", "name_zh": "CSF", "name_en": "CSF",
              "version": "2.0", "source": "nist.gov"},
        files={"file": ("f.xlsx", _workbook(GOOD),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert resp.status_code == 200
    framework_id = resp.json()["id"]

    tree = await client.get(f"/api/frameworks/{framework_id}/tree", headers=headers)
    assert [item["code"] for item in tree.json()] == ["PR", "PR.AA-01"]

    coverage = await client.get(f"/api/frameworks/{framework_id}/coverage", headers=headers)
    root = next(row for row in coverage.json() if row["code"] == "PR")
    assert root["requirements"] == 1 and root["covered"] == 0

    gaps = await client.get(f"/api/frameworks/{framework_id}/gaps", headers=headers)
    assert [gap["code"] for gap in gaps.json()] == ["PR.AA-01"]


@pytest.mark.asyncio
async def test_contributor_can_read_but_not_import(client, db_session):
    await _seed(db_session, Role.CONTRIBUTOR, "contrib@example.com")
    headers = await _auth(client, "contrib@example.com")
    assert (await client.get("/api/frameworks", headers=headers)).status_code == 200
    resp = await client.post(
        "/api/frameworks/import",
        headers=headers,
        data={"key": "csf", "name_zh": "CSF", "name_en": "CSF",
              "version": "2.0", "source": "nist.gov"},
        files={"file": ("f.xlsx", _workbook(GOOD),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_contributor_cannot_trigger_mapping(client, db_session):
    await _seed(db_session, Role.CONTRIBUTOR, "contrib@example.com")
    headers = await _auth(client, "contrib@example.com")
    resp = await client.post("/api/mapping/frameworks/1", headers=headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_mapping_an_unknown_framework_is_404(client, db_session):
    await _seed(db_session, Role.GRC_LEAD, "lead@example.com")
    headers = await _auth(client, "lead@example.com")
    resp = await client.post("/api/mapping/frameworks/999999", headers=headers)
    assert resp.status_code == 404
