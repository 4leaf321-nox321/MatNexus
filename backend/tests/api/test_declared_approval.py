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
from app.shared import audit, dataset_export, declared_approval, declared_card, tiers
from matcore import export
from matcore.export.systems import SI

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


class Test할선_기준_온도:
    """선팽창계수 표의 θ₀(2026-10-04) — 덱의 Abaqus ZERO · ANSYS REFT · Nastran TREF 가 된다.

    **승인 지문에는 있을 때만 든다**(사용자 결정). 늘 넣으면 θ₀ 가 없는 옛 줄도 지문이 바뀌어
    배포하는 순간 승인이 전부 풀린다.
    """

    CTE = "선팽창계수(CTE)"

    def _table(self, **extra: Any) -> dict[str, Any]:
        return {
            "item": self.CTE,
            "points": [
                {"value": 1.2e-5, "temperature_k": 293.15},
                {"value": 1.4e-5, "temperature_k": 573.15},
            ],
            "input_unit": "1/K",
            "source": "literature",
            "reference": "ASM Handbook Vol.1 p.120",
            **extra,
        }

    def test_θ0_가_없는_옛_줄의_지문은_그대로다(self) -> None:
        """이 값은 θ₀ 를 들이기 전 판(4f1a865)의 지문 함수로 셈한 것이다 — 바뀌면 운영의 승인이
        배포와 함께 전부 풀린다."""
        row = {
            "item": self.CTE,
            "points": [
                {"value_si": 1.2e-5, "temperature_k": 293.15},
                {"value_si": 1.4e-5, "temperature_k": 573.15},
            ],
            "si_unit": "1/K",
            "scale": None,
            "source": "literature",
            "reference": "ASM Handbook Vol.1 p.120",
            "input_unit": "1/K",
            "note": None,
        }
        assert declared_approval.digest(row) == "364c3db6a58b847e72b7"
        assert declared_approval.digest({**row, "secant_reference_k": None}) == (
            "364c3db6a58b847e72b7"
        )
        # θ₀ 가 있으면 다른 값이다.
        assert declared_approval.digest({**row, "secant_reference_k": 293.15}) != (
            "364c3db6a58b847e72b7"
        )

    def test_선팽창계수에만_받고_θ0_를_고치면_승인이_풀린다(
        self, client: TestClient, steward: dict[str, str], material: Material
    ) -> None:
        def save(*rows: dict[str, Any]) -> Any:
            return client.patch(
                f"/api/materials/{material.id}",
                json={"declared_properties": [modulus(), *rows]},
                headers=steward,
            )

        saved = save(self._table(secant_reference_k=293.15))
        assert saved.status_code == 200, saved.text
        rows = {one["item"]: one for one in saved.json()["declared_properties"]}
        assert rows[self.CTE]["secant_reference_k"] == pytest.approx(293.15)
        assert rows[E]["secant_reference_k"] is None

        approved = client.post(
            f"/api/materials/{material.id}/declared/approve",
            json={"item": self.CTE},
            headers=steward,
        )
        assert approved.status_code == 200, approved.text
        # 같은 θ₀ 로 되보내면 승인은 그대로 — 화면이 저장할 때마다 되보낸다.
        again = {
            one["item"]: one
            for one in save(self._table(secant_reference_k=293.15)).json()[
                "declared_properties"
            ]
        }
        assert again[self.CTE]["approval"] is not None
        # θ₀ 가 바뀌면 다른 값이다.
        moved = {
            one["item"]: one
            for one in save(self._table(secant_reference_k=300.0)).json()[
                "declared_properties"
            ]
        }
        assert moved[self.CTE]["approval"] is None

        # MCP 는 θ₀ 가 없는 줄에도 `null` 을 실어 되보낸다 — 없는 것과 같다.
        plain = client.patch(
            f"/api/materials/{material.id}",
            json={"declared_properties": [modulus(secant_reference_k=None)]},
            headers=steward,
        )
        assert plain.status_code == 200, plain.text
        assert plain.json()["declared_properties"][0]["secant_reference_k"] is None

        wrong = client.patch(
            f"/api/materials/{material.id}",
            json={"declared_properties": [modulus(secant_reference_k=293.15)]},
            headers=steward,
        )
        assert wrong.status_code == 422, wrong.text
        assert wrong.json()["error"]["code"] == "MNX-MATERIALS-0049"

    def test_θ0_가_덱의_ZERO_가_된다(
        self, client: TestClient, steward: dict[str, str], db: Session, material: Material
    ) -> None:
        saved = client.patch(
            f"/api/materials/{material.id}",
            json={
                "declared_properties": [
                    self._table(secant_reference_k=293.15),
                ]
            },
            headers=steward,
        )
        assert saved.status_code == 200, saved.text
        db.refresh(material)

        values = declared_card.thermal_block(material)
        assert values["thermal_expansion_temperature"] == pytest.approx(293.15)

        rows = declared_card.declared_table(material, declared_card.declared_items("thermal"))
        # 열팽창은 구조 덱에 실린다(열전달 덱 `abaqus_thermal` 은 안 싣는다).
        deck = export.Deck(
            name="SECC",
            solver_id=1,
            blocks={
                "elastic": {"values": {"youngs_modulus": 2.05e11, "poisson_ratio": 0.3}},
                "thermal": {"values": values, "rows": rows},
            },
        )
        text = export.render("abaqus_elastic", deck, SI).text
        assert "ZERO=2.931500000000E+02" in text  # *EXPANSION, TYPE=ISO, ZERO=θ₀
        assert "ZERO not on the card" not in text


class Test승인_대기_목록:
    """재료마다 열어 봐야 알던 「승인하면 오를 값」 을 한 목록으로(2026-10-04, ADR 0049).

    큐가 아니다 — 승인은 그 값이 사는 화면에서 한다(결정 5).
    """

    def test_오를_값만_서고_승인하면_빠진다(
        self, client: TestClient, steward: dict[str, str], material: Material
    ) -> None:
        made = client.post(f"/api/materials/{material.id}/samples", json={}, headers=steward)
        assert made.status_code == 201, made.text
        sample_id = made.json()["id"]
        saved = client.patch(
            f"/api/samples/{sample_id}",
            json={
                "declared_properties": [
                    # 밀시트는 1 이라 승인해도 안 오른다 — 목록에 안 선다.
                    {
                        "item": "항복강도",
                        "points": [{"value": 310}],
                        "input_unit": "MPa",
                        "source": "millsheet",
                        "reference": "성적서 24-0815",
                    },
                    # 추정 4 → 3 — 선다.
                    {
                        "item": "인장강도",
                        "points": [
                            {"value": 420, "temperature_k": 296.15},
                            {"value": 400, "temperature_k": 373.15},
                        ],
                        "input_unit": "MPa",
                        "source": "estimate",
                        "reference": "사내 추정",
                    },
                ]
            },
            headers=steward,
        )
        assert saved.status_code == 200, saved.text

        def listed() -> list[tuple[str, str, int, int]]:
            got = client.get("/api/materials/declared-review", headers=steward)
            assert got.status_code == 200, got.text
            return [
                (one["level"], one["item"], one["quality_tier"], one["tier_if_approved"])
                for one in got.json()["items"]
            ]

        assert listed() == [("시료", "인장강도", 4, 3), ("재료", E, 3, 2)]
        got = client.get("/api/materials/declared-review", headers=steward).json()
        estimate = next(one for one in got["items"] if one["item"] == "인장강도")
        assert estimate["point_count"] == 2
        assert estimate["first_value_si"] == pytest.approx(420e6)
        assert estimate["sample_id"] == sample_id

        assert _approve(client, steward, material).status_code == 200
        assert listed() == [("시료", "인장강도", 4, 3)]

    def test_보기는_누구나다(
        self,
        client: TestClient,
        db: Session,
        workspace: Workspace,
        material: Material,
    ) -> None:
        """적은 사람도 「내 값이 아직 확인 전」 임을 안다(ADR 0035 — 보기는 모두에게)."""
        _user(db, workspace, "plain@example.com")
        got = client.get(
            "/api/materials/declared-review", headers=_headers(client, "plain@example.com")
        )
        assert got.status_code == 200, got.text
        assert [one["item"] for one in got.json()["items"]] == [E]


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
