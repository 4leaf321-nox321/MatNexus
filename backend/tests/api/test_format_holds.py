"""기본 제공 형식의 **사용 중단** — 틀린 것이 발견되면 배포까지 메뉴에서 내린다(ADR 0037).

코드로 만든 형식은 화면에서 못 고친다. 고쳐 배포하기까지의 공백에 사람들이 틀린 덱을 계속
받지 않게, 시스템 관리자가 형식을 내린다. 지키는 것:

    모든 길에서 빠진다       형식 목록 · 카드의 「낼 수 있는 형식」 · 내려받기 · 문헌 덱
    거절이 이유를 말한다      「모르는 형식」 이 아니라 누가 왜 내렸는지
    멈춘 것도 보인다         기본 형식 목록에는 남는다 — 다시 쓰려면 보여야 한다
    걸고 푼 것이 남는다       감사 기록 — 그때 받은 덱을 다시 받아야 하는지가 거기서 갈린다
    시스템 관리자만          일반 사용자는 403
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.audit.models import AuditEntry
from app.modules.fitting.models import PropertyCard
from app.shared import litdeck
from matcore import export

REASON = "*MAT_024 의 3·4번 카드가 빠졌다 — 고쳐 배포 전까지"


def _card(client: TestClient, db: Session, headers: dict[str, str]) -> str:
    material = client.post(
        "/api/materials",
        json={
            "family": "Metal",
            "category": "Steel",
            "grade": f"HOLD-{uuid.uuid4().hex[:6]}",
            "spec_thickness": 1.0,
        },
        headers=headers,
    ).json()
    item = PropertyCard(
        material_id=uuid.UUID(material["id"]),
        label="탄소성",
        status="draft",
        blocks={
            "elastic": {
                "values": {"youngs_modulus": 210e9, "poisson_ratio": 0.3, "density": 7850.0}
            },
            "table": {
                "rows": [
                    {"plastic_strain": 0.0, "true_stress": 350e6},
                    {"plastic_strain": 0.1, "true_stress": 560e6},
                ]
            },
        },
    )
    db.add(item)
    db.commit()
    return str(item.id)


def _hold(client: TestClient, headers: dict[str, str], key: str = "dyna") -> Any:
    return client.put(
        f"/api/fitting/builtin-formats/{key}/hold", json={"reason": REASON}, headers=headers
    )


def test_내리면_모든_길에서_빠지고_이유를_말한다(
    client: TestClient, db: Session, admin_headers: dict[str, str]
) -> None:
    card_id = _card(client, db, admin_headers)
    held = _hold(client, admin_headers)
    assert held.status_code == 200, held.text
    assert held.json()["hold"]["reason"] == REASON
    assert held.json()["hold"]["held_by_name"] == "시스템 관리자"

    formats = client.get("/api/fitting/formats", headers=admin_headers).json()
    assert "dyna" not in {one["key"] for one in formats}
    card = client.get(f"/api/fitting/cards/{card_id}", headers=admin_headers).json()
    assert "dyna" not in card["available_formats"]
    assert "openradioss" in card["available_formats"]  # 다른 형식은 그대로

    refused = client.get(
        f"/api/fitting/cards/{card_id}/export",
        params={"format": "dyna"},
        headers=admin_headers,
    )
    assert refused.status_code == 422
    assert "사용 중단" in refused.text and "3·4번 카드" in refused.text

    # 멈춘 것도 기본 형식 목록에는 남는다 — 다시 쓰려면 보여야 한다.
    builtin = client.get("/api/fitting/builtin-formats", headers=admin_headers).json()
    row = next(one for one in builtin if one["key"] == "dyna")
    assert row["hold"]["reason"] == REASON


def test_형식_key_를_바로_부르는_길도_막는다(
    client: TestClient, db: Session, admin_headers: dict[str, str]
) -> None:
    """문헌 덱은 형식 목록을 안 지난다 — 여기서 안 막으면 메뉴에서만 사라진다."""
    assert _hold(client, admin_headers, "dyna_elastic").status_code == 200
    try:
        litdeck.build(db, [], "dyna_elastic", None)
    except export.ExportError as refused:
        assert "사용 중단" in str(refused)
    else:
        raise AssertionError("멈춘 형식으로 문헌 덱이 나갔다")


def test_다시_쓰면_돌아오고_걸고_푼_것이_남는다(
    client: TestClient, db: Session, admin_headers: dict[str, str]
) -> None:
    _hold(client, admin_headers)
    released = client.delete("/api/fitting/builtin-formats/dyna/hold", headers=admin_headers)
    assert released.status_code == 204
    formats = client.get("/api/fitting/formats", headers=admin_headers).json()
    assert "dyna" in {one["key"] for one in formats}

    actions = [
        (row.action, row.reason)
        for row in db.scalars(
            select(AuditEntry)
            .where(AuditEntry.target_table == "export_format_holds")
            .order_by(AuditEntry.created_at)
        )
    ]
    assert actions[0] == ("export_format.held", REASON)
    assert actions[-1][0] == "export_format.released"


def test_시스템_관리자만(
    client: TestClient, db: Session, admin_headers: dict[str, str]
) -> None:
    from app.modules.accounts.models import User
    from app.modules.auth import security

    db.add(
        User(
            email="member@example.com",
            password_hash=security.hash_password("member-password-1"),
            display_name="일반",
            status="active",
        )
    )
    db.commit()
    token = client.post(
        "/api/auth/login",
        json={"email": "member@example.com", "password": "member-password-1"},
    ).json()["access_token"]
    member = {"Authorization": f"Bearer {token}"}
    assert _hold(client, member).status_code == 403
    # 보기는 누구나 — 「어제 있던 형식이 왜 없나」 를 쓰는 사람도 봐야 한다.
    assert client.get("/api/fitting/builtin-formats", headers=member).status_code == 200


def test_기본_형식이_아니면_404(client: TestClient, admin_headers: dict[str, str]) -> None:
    assert _hold(client, admin_headers, "no_such_format").status_code == 404
    assert (
        client.delete(
            "/api/fitting/builtin-formats/dyna/hold", headers=admin_headers
        ).status_code
        == 404
    )
