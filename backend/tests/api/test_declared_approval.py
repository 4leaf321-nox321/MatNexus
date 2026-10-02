"""선언 물성 **승인** — 자료 관리자가 근거 문서와 대조해 확인한 값(ADR 0049, 2026-10-02).

요청: 「선언한 것도 관리자 승인 같은 것을 통해 높은 등급의 물성이 되도록 하면 좋겠다.」

등급은 사람이 매기지 않는다(`shared/tiers`) — 승인은 「누가 언제 근거를 확인했다」 는 사실을
근거에 더하고, 등급은 여전히 거기서 산출한다. 이 시험이 지키는 것:

    등급      승인하면 한 단계 — 문헌 3 → 2 · 추정 4 → 3, 2 위로는 안 간다(1 은 실측의 자리)
    누가      자료 관리자 · 시스템 관리자만. 등록자도 못 한다
    묶임      값 · 단위 · 조건 · 출처 · 근거 문서를 고치면 풀린다
              (비고 · 표시 단위 · 그대로 되보내기는 아니다)
    위조      고치는 길(PATCH)로 승인을 적어 넣을 수 없다
    흔적      승인 · 거둠 · 풀림이 감사에 남는다
    퍼짐      카드 칸의 출처 표지 · 덱 각주 등급 · 근거 말 · CSV 가 승인을 안다
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.accounts.models import User
from app.modules.audit.models import AuditEntry
from app.modules.auth import security
from app.modules.fitting import card_tiers
from app.modules.fitting.models import PropertyCard
from app.modules.fitting.routes import _origin
from app.modules.materials import declared
from app.modules.materials.models import Material
from app.modules.vocabulary.definitions import ensure_builtin_property_items
from app.modules.workspaces.models import Workspace, WorkspaceMember
from app.shared import audit, dataset_export, declared_approval, tiers

PASSWORD = "Passw0rd!approve"
E = "탄성계수"


def _user(db: Session, workspace: Workspace, email: str, **roles: bool) -> User:
    user = User(
        email=email,
        password_hash=security.hash_password(PASSWORD),
        display_name=email,
        status="active",
        home_workspace_id=workspace.id,
        **roles,
    )
    db.add(user)
    db.flush()
    db.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="member"))
    db.commit()
    return user


def _headers(client: TestClient, email: str) -> dict[str, str]:
    got = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert got.status_code == 200, got.text
    return {"Authorization": f"Bearer {got.json()['access_token']}"}


def modulus(**over: Any) -> dict[str, Any]:
    return {
        "item": E,
        "points": [{"value": 200}],
        "input_unit": "GPa",
        "source": "literature",
        "reference": "ASM Handbook Vol.1 p.120",
        **over,
    }


@pytest.fixture()
def material(db: Session) -> Material:
    ensure_builtin_property_items(db)
    one = Material(record_name="SECC_-_-", family="Metal", category="Steel", grade="SECC")
    db.add(one)
    db.flush()
    one.declared_properties = declared.check(db, [modulus()])
    db.commit()
    return one


@pytest.fixture()
def steward(client: TestClient, db: Session, workspace: Workspace) -> dict[str, str]:
    _user(db, workspace, "steward@example.com", is_data_manager=True)
    return _headers(client, "steward@example.com")


def _approve(
    client: TestClient, headers: dict[str, str], material: Material, **body: Any
) -> Any:
    return client.post(
        f"/api/materials/{material.id}/declared/approve",
        json={"item": E, **body},
        headers=headers,
    )


def _row(response: Any) -> dict[str, Any]:
    assert response.status_code == 200, response.text
    rows: dict[str, dict[str, Any]] = {
        one["item"]: one for one in response.json()["declared_properties"]
    }
    return rows[E]


def _actions(db: Session, material: Material) -> list[str]:
    db.expire_all()
    return list(
        db.scalars(
            select(AuditEntry.action)
            .where(AuditEntry.target_id == material.id)
            .order_by(AuditEntry.created_at)
        )
    )


class Test등급_규칙:
    def test_승인하면_한_단계_오르되_2_위로는_안_간다(self) -> None:
        assert tiers.declared_tier("literature", approved=True) == 2
        assert tiers.declared_tier("estimate", approved=True) == 3
        # 1 은 「그 제품 문서에 인쇄된 실측」 — 승인은 실측을 만들지 않는다.
        assert tiers.declared_tier("standard", approved=True) == 2
        assert tiers.declared_tier("datasheet", approved=True) == 1
        assert tiers.declared_tier("literature") == 3

    def test_카드_출처_표지를_되읽는다(self) -> None:
        token = tiers.declared_origin("literature", approved=True)
        assert token == "declared:literature+approved"
        assert tiers.split_declared(token.removeprefix("declared:")) == ("literature", True)
        assert tiers.split_declared("literature") == ("literature", False)


class Test지문:
    def test_값을_고치면_승인이_풀린다(self, db: Session, material: Material) -> None:
        row = declared_approval.stamp(
            material.declared_properties[0], user_id="x", name="관리자", note=None
        )
        assert declared_approval.of(row) is not None

        for changed in (
            modulus(points=[{"value": 210}]),
            modulus(source="estimate"),
            modulus(reference="다른 핸드북"),
            modulus(points=[{"value": 200, "temperature_k": 373.15}]),
        ):
            moved = {**declared.check(db, [changed])[0], "approval": row["approval"]}
            assert declared_approval.of(moved) is None, changed

    def test_비고_표시_단위_되보내기는_값을_바꾸지_않는다(
        self, db: Session, material: Material
    ) -> None:
        """화면은 값을 12자리로 되보낸다 — 고치지 않고 다시 저장해도 승인이 남아야 한다."""
        row = declared_approval.stamp(
            material.declared_properties[0], user_id="x", name="관리자", note=None
        )
        for same in (
            modulus(note="표 3 의 상온 값"),
            modulus(points=[{"value": 200000}], input_unit="MPa"),
            modulus(points=[{"value": 200.0000000001}]),
        ):
            moved = {**declared.check(db, [same])[0], "approval": row["approval"]}
            assert declared_approval.of(moved) is not None, same

    def test_옮기기는_그대로인_줄만_풀린_줄은_이름으로(self, db: Session) -> None:
        ensure_builtin_property_items(db)
        before = [
            declared_approval.stamp(row, user_id="x", name="관리자", note=None)
            for row in declared.check(
                db,
                [
                    modulus(),
                    {
                        "item": "비열",
                        "points": [{"value": 460}],
                        "input_unit": "J/(kg.K)",
                        "source": "literature",
                        "reference": "핸드북",
                    },
                ],
            )
        ]
        after = declared.check(
            db,
            [
                modulus(note="비고만 바꿈"),
                {
                    "item": "비열",
                    "points": [{"value": 470}],
                    "input_unit": "J/(kg.K)",
                    "source": "literature",
                    "reference": "핸드북",
                },
            ],
        )

        carried, lapsed = declared_approval.carry(before, after)

        by_item = {row["item"]: row for row in carried}
        assert declared_approval.of(by_item[E]) is not None
        assert declared_approval.of(by_item["비열"]) is None
        assert lapsed == ["비열"]

    def test_받은_줄에_적힌_승인은_옮기기가_버린다(
        self, db: Session, material: Material
    ) -> None:
        """입력 스키마 · `check` 가 칸을 받아 주기 시작해도 마지막 문은 여기다."""
        forged = declared_approval.stamp(
            material.declared_properties[0], user_id="x", name="위조", note=None
        )

        carried, lapsed = declared_approval.carry([], [forged])

        assert declared_approval.of(carried[0]) is None
        assert lapsed == []


class Test승인:
    def test_자료_관리자가_승인하면_등급이_오른다(
        self,
        client: TestClient,
        db: Session,
        steward: dict[str, str],
        material: Material,
    ) -> None:
        listed = client.get(f"/api/materials/{material.id}", headers=steward)
        assert _row(listed)["quality_tier"] == 3
        assert _row(listed)["approval"] is None

        row = _row(_approve(client, steward, material, note="원문 대조"))

        assert row["quality_tier"] == 2
        assert row["approval"]["by"] == "steward@example.com"
        assert row["approval"]["note"] == "원문 대조"
        assert audit.DECLARED_APPROVED in _actions(db, material)

    def test_등록자라도_자료_관리자가_아니면_못_한다(
        self, client: TestClient, db: Session, workspace: Workspace, material: Material
    ) -> None:
        """고칠 수 있는 사람과 승인하는 사람은 다르다 — 카드 확정과 같다(ADR 0035 D4)."""
        owner = _user(db, workspace, "owner@example.com")
        material.registered_by_id = owner.id
        db.commit()

        refused = _approve(client, _headers(client, "owner@example.com"), material)

        assert refused.status_code == 403, refused.text
        assert refused.json()["error"]["code"] == "MNX-MATERIALS-0044"

    def test_두_번_승인_없는_값_승인_안_된_값_거두기(
        self, client: TestClient, steward: dict[str, str], material: Material
    ) -> None:
        assert _approve(client, steward, material).status_code == 200
        again = _approve(client, steward, material)
        assert again.status_code == 409, again.text
        assert "이미" in again.json()["error"]["message"]

        missing = client.post(
            f"/api/materials/{material.id}/declared/approve",
            json={"item": "비열"},
            headers=steward,
        )
        assert missing.status_code == 404, missing.text

        assert (
            client.post(
                f"/api/materials/{material.id}/declared/unapprove",
                json={"item": E},
                headers=steward,
            ).status_code
            == 200
        )
        twice = client.post(
            f"/api/materials/{material.id}/declared/unapprove",
            json={"item": E},
            headers=steward,
        )
        assert twice.status_code == 409, twice.text

    def test_거두면_출처의_등급으로_돌아가고_남는다(
        self,
        client: TestClient,
        db: Session,
        steward: dict[str, str],
        material: Material,
    ) -> None:
        _approve(client, steward, material)

        row = _row(
            client.post(
                f"/api/materials/{material.id}/declared/unapprove",
                json={"item": E},
                headers=steward,
            )
        )

        assert row["approval"] is None
        assert row["quality_tier"] == 3
        assert audit.DECLARED_UNAPPROVED in _actions(db, material)


class Test고치는_길:
    def test_그대로_되보내면_승인이_남는다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        steward: dict[str, str],
        material: Material,
    ) -> None:
        """화면 · MCP 는 선언 물성을 통째로 되보낸다 — 다른 항목을 고칠 때마다 풀리면
        못 쓴다."""
        approved = _row(_approve(client, steward, material))

        resent = client.patch(
            f"/api/materials/{material.id}",
            json={
                "declared_properties": [
                    modulus(
                        points=[{"value": point["value"]} for point in approved["points"]],
                        input_unit=approved["input_unit"],
                        note="비고만 고침",
                    )
                ]
            },
            headers=admin_headers,
        )

        assert _row(resent)["approval"] is not None
        assert _row(resent)["quality_tier"] == 2

    def test_값을_고치면_풀리고_감사에_남는다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        steward: dict[str, str],
        material: Material,
    ) -> None:
        _approve(client, steward, material)

        changed = client.patch(
            f"/api/materials/{material.id}",
            json={"declared_properties": [modulus(points=[{"value": 205}])]},
            headers=admin_headers,
        )

        assert _row(changed)["approval"] is None
        assert _row(changed)["quality_tier"] == 3
        assert audit.DECLARED_APPROVAL_LAPSED in _actions(db, material)

    def test_고치는_길로는_승인을_적어_넣지_못한다(
        self, client: TestClient, db: Session, workspace: Workspace, material: Material
    ) -> None:
        """지문은 누구나 셈할 수 있다 — 받은 줄의 승인을 믿으면 아무나 승인을 적는다."""
        owner = _user(db, workspace, "owner2@example.com")
        material.registered_by_id = owner.id
        db.commit()
        forged = declared_approval.stamp(
            material.declared_properties[0], user_id=str(owner.id), name="위조", note=None
        )["approval"]

        sent = client.patch(
            f"/api/materials/{material.id}",
            json={"declared_properties": [{**modulus(), "approval": forged}]},
            headers=_headers(client, "owner2@example.com"),
        )

        assert _row(sent)["approval"] is None
        assert _row(sent)["quality_tier"] == 3


class Test시료:
    def test_밀시트_값도_승인하되_등급은_1_그대로(
        self, client: TestClient, steward: dict[str, str], material: Material
    ) -> None:
        made = client.post(f"/api/materials/{material.id}/samples", json={}, headers=steward)
        assert made.status_code == 201, made.text
        sample_id = made.json()["id"]
        saved = client.patch(
            f"/api/samples/{sample_id}",
            json={
                "declared_properties": [
                    {
                        "item": "항복강도",
                        "points": [{"value": 310}],
                        "input_unit": "MPa",
                        "source": "millsheet",
                        "reference": "성적서 24-0815",
                    }
                ]
            },
            headers=steward,
        )
        assert saved.status_code == 200, saved.text

        approved = client.post(
            f"/api/samples/{sample_id}/declared/approve",
            json={"item": "항복강도"},
            headers=steward,
        )

        assert approved.status_code == 200, approved.text
        row = approved.json()["declared_properties"][0]
        assert row["approval"] is not None
        assert row["quality_tier"] == 1


class Test퍼짐:
    def test_카드_칸과_덱_각주가_승인을_안다(self, db: Session, material: Material) -> None:
        """카드는 만들 때의 승인을 칸의 출처 표지로 든다 — 덱 각주는 그것으로 등급을 센다."""
        material.declared_properties = [
            declared_approval.stamp(row, user_id="x", name="관리자", note=None)
            for row in material.declared_properties
        ]
        db.commit()
        row = material.declared_properties[0]
        assert declared_approval.origin(row) == "declared:literature+approved"

        card = PropertyCard(
            label="t",
            blocks={
                "thermal": {
                    "values": {
                        "specific_heat": 460.0,
                        "specific_heat_source": "declared:literature+approved",
                        "thermal_conductivity": 50.0,
                        "thermal_conductivity_source": "declared:literature",
                    }
                }
            },
            source={},
        )
        graded = card_tiers.value_tiers(card)
        assert graded["thermal.specific_heat"] == 2
        assert graded["thermal.thermal_conductivity"] == 3

    def test_근거_말에_승인이_적힌다(self) -> None:
        assert (
            _origin("declared:literature+approved")
            == "사람이 적은 값 (문헌 · 자료 관리자 승인)"
        )
        assert _origin("declared:literature") == "사람이 적은 값 (문헌)"

    def test_CSV_에_등급과_승인_때가_실린다(
        self, db: Session, material: Material, tmp_path: Path
    ) -> None:
        material.declared_properties = [
            declared_approval.stamp(row, user_id="x", name="관리자", note=None)
            for row in material.declared_properties
        ]
        db.commit()

        dataset_export.export(
            tmp_path, db=db, workspace=None, with_curves=False, with_catalog=False
        )

        with (tmp_path / "declared_properties.csv").open(encoding="utf-8-sig") as handle:
            rows = {row["item"]: row for row in csv.DictReader(handle)}
        assert rows[E]["quality_tier"] == "2"
        assert rows[E]["approved_at"]
        # 이 묶음은 사람을 일부러 뺀다 — 승인한 사람 이름은 안 싣는다.
        assert "approved_by" not in rows[E]
