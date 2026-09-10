import pytest

from app.evidence.models import EvidenceCadence


@pytest.mark.asyncio
async def test_evidence_type_crud_is_available_to_contributors(client, db_session):
    from app.iam.models import User
    from app.iam.permissions import Role
    from app.iam.security import hash_password

    user = User(
        email="contributor@example.com",
        name="Contributor",
        role=Role.CONTRIBUTOR,
        password_hash=hash_password("pw123456"),
    )
    db_session.add(user)
    await db_session.flush()
    login = await client.post("/api/auth/login", json={"email": user.email, "password": "pw123456"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    response = await client.post(
        "/api/evidence-types",
        headers=headers,
        json={
            "name_zh": "PAM 季度抽样",
            "name_en": "PAM quarterly sample",
            "format": "mp4",
            "cadence": EvidenceCadence.QUARTERLY.value,
            "typical_source": "VaultKeeper",
            "description": "Session recordings.",
        },
    )
    assert response.status_code == 201
    assert response.json()["cadence"] == "quarterly"
    assert (await client.get("/api/evidence-types", headers=headers)).json()[0][
        "name_en"
    ] == "PAM quarterly sample"
