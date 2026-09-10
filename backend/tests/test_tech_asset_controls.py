import pytest

from app.controls.models import Control
from app.environment.models import (
    HowEnforced,
    Implementation,
    ImplementationStatus,
    TechAsset,
    TechAssetCategory,
    TechAssetEnvironment,
    TechAssetStatus,
)
from app.iam.models import User
from app.iam.permissions import Role
from app.iam.security import hash_password


@pytest.mark.asyncio
async def test_asset_controls_reverse_lookup_excludes_not_applicable(client, db_session):
    user = User(
        email="viewer@example.com",
        name="Viewer",
        role=Role.VIEWER,
        password_hash=hash_password("pw123456"),
    )
    asset = TechAsset(
        name="VaultKeeper",
        category=TechAssetCategory.PAM,
        vendor="VaultKeeper",
        environment=TechAssetEnvironment.PROD,
        status=TechAssetStatus.ACTIVE,
    )
    first = Control(code="C-0001", title="Review access", statement="Review access.")
    second = Control(code="C-0002", title="Rotate secrets", statement="Rotate secrets.")
    db_session.add_all([user, asset, first, second])
    await db_session.flush()
    db_session.add_all(
        [
            Implementation(
                control_id=first.id,
                tech_asset_id=asset.id,
                how_enforced=HowEnforced.AUTOMATED,
                status=ImplementationStatus.IMPLEMENTED,
                description="Reviews.",
            ),
            Implementation(
                control_id=second.id,
                tech_asset_id=asset.id,
                how_enforced=HowEnforced.MANUAL,
                status=ImplementationStatus.NOT_APPLICABLE,
                na_justification="Out of scope.",
                description="",
            ),
        ]
    )
    await db_session.flush()
    login = await client.post("/api/auth/login", json={"email": user.email, "password": "pw123456"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    response = await client.get(f"/api/tech-assets/{asset.id}/controls", headers=headers)
    assert response.status_code == 200
    assert [row["control_code"] for row in response.json()] == ["C-0001"]
