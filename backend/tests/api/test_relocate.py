"""시편을 **다른 두께의 같은 재료**로 옮긴다(2026-09-29).

두께가 다른 재료에 잘못 넣은 시편을 바로잡는 길이다. 무는 것:

    계획은 아무것도 안 바꾼다          미리보기가 쓰면 창을 닫아도 이미 옮겨져 있다
    새 재료는 원 재료의 복사본이다      두께만 다르다 — 분류·용도·밀도·선언 물성이 따라간다
    시료째 · 일부만                    전부 고르면 시료째, 일부면 같은 로트로 새 시료
    이름이 시험까지 따라간다            옮긴 뒤에도 옛 두께 이름이면 목록이 거짓말을 한다
    있는 재료로 합친다                 같은 이름이 둘이 되면 안 된다
    카드 — 옮기는 것은 막지 않는다      확정 카드에도 코멘트가 붙고, 정리(사용 중지)를 고른다
    정리 못 하는 카드면 아무것도 안 옮긴다   옮기다 만 상태가 남지 않게
    권한 밖의 시편은 이유와 함께 빠진다
    묶음·대표 곡선 기록은 알리기만 한다    옛 묶음으로 새 카드를 만드는 것은 막는다
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.audit.models import AuditEntry
from app.modules.fitting.models import PropertyCard
from app.modules.grouping.models import GroupResult
from app.modules.materials.models import Material, Sample, Specimen
from app.modules.statistics.models import EnsembleResult
from app.modules.tests.definitions import ensure_builtin_test_types
from app.modules.tests.models import TestRun, TestType
from app.modules.workspaces.models import Workspace

SECC = {
    "family": "Metal",
    "category": "Steel",
    "grade": "SECC",
    "details": "MDOI",
    "spec_thickness": 1.0,
    "spec_thickness_unit": "mm",
}


def _material(client: TestClient, headers: dict[str, str], **overrides: Any) -> dict[str, Any]:
    made = client.post("/api/materials", json={**SECC, **overrides}, headers=headers)
    assert made.status_code == 201, made.text
    body: dict[str, Any] = made.json()
    return body


def _sample(
    client: TestClient, headers: dict[str, str], material_id: str, **fields: Any
) -> dict[str, Any]:
    made = client.post(f"/api/materials/{material_id}/samples", json=fields, headers=headers)
    assert made.status_code == 201, made.text
    body: dict[str, Any] = made.json()
    return body


def _specimen(client: TestClient, headers: dict[str, str], sample_id: str) -> dict[str, Any]:
    made = client.post(
        f"/api/samples/{sample_id}/specimens", json={"orientation": "MD"}, headers=headers
    )
    assert made.status_code == 201, made.text
    body: dict[str, Any] = made.json()
    return body


def _run(db: Session, workspace: Workspace, specimen: dict[str, Any]) -> TestRun:
    ensure_builtin_test_types(db)
    tensile = db.scalar(select(TestType).where(TestType.key == "tensile"))
    assert tensile is not None
    run = TestRun(
        workspace_id=workspace.id,
        specimen_id=uuid.UUID(specimen["id"]),
        test_type_id=tensile.id,
        seq_no=1,
        record_name=f"{specimen['record_name']}__TEN_01",
        status="parsed",
    )
    db.add(run)
    db.commit()
    return run


def _card(db: Session, material_id: str, runs: list[TestRun], status: str) -> PropertyCard:
    card = PropertyCard(
        material_id=uuid.UUID(material_id),
        label=f"SECC 인장 {status}",
        status=status,
        source={"test_run_ids": [str(run.id) for run in runs], "sample_count": len(runs)},
    )
    db.add(card)
    db.commit()
    return card


def _ask(ids: list[str], **extra: Any) -> dict[str, Any]:
    return {
        "specimen_ids": ids,
        "spec_thickness": 1.2,
        "spec_thickness_unit": "mm",
        **extra,
    }


def _setup(
    client: TestClient, headers: dict[str, str], *, rich: bool = True
) -> tuple[
    dict[str, Any], dict[str, Any], list[dict[str, Any]], dict[str, Any], dict[str, Any]
]:
    """SECC_MDOI_1.0 — 시료 A(로트 L1: 시편 둘) · 시료 B(로트 L2: 시편 하나).

    `rich` 면 용도·제조사까지 — 새 기준정보 값을 만드는 일이라 관리자 계정으로만 쓴다.
    """
    material = _material(
        client,
        headers,
        alias="도어 이너",
        density=7850,
        density_unit="kg/m3",
        poisson_ratio=0.3,
        **({"applied_products": ["범퍼"]} if rich else {}),
    )
    first = _sample(
        client,
        headers,
        material["id"],
        lot_no="L1",
        **({"manufacturer": "포스코"} if rich else {}),
    )
    pair = [_specimen(client, headers, first["id"]), _specimen(client, headers, first["id"])]
    second = _sample(client, headers, material["id"], lot_no="L2")
    lone = _specimen(client, headers, second["id"])
    return material, first, pair, second, lone


class Test계획과_옮기기:
    def test_계획은_아무것도_안_바꾸고_무엇이_어디로_가는지_말한다(
        self, client: TestClient, admin_headers: dict[str, str], db: Session
    ) -> None:
        _, first, pair, _, _ = _setup(client, admin_headers)
        got = client.post(
            "/api/specimens/relocate-plan",
            json=_ask([one["id"] for one in pair]),
            headers=admin_headers,
        )
        assert got.status_code == 200, got.text
        plan = got.json()
        assert plan["specimens"] == 2
        assert plan["thickness"] == 1.2 and plan["thickness_unit"] == "mm"
        assert [
            (one["from_material_name"], one["to_material_name"], one["exists"])
            for one in plan["targets"]
        ] == [("SECC_MDOI_1.0", "SECC_MDOI_1.2", False)]
        assert [(one["sample_name"], one["whole"]) for one in plan["samples"]] == [
            (first["record_name"], True)
        ]
        assert plan["blocked"] == []
        # **쓰지 않았다.**
        assert (
            db.scalar(select(Material).where(Material.record_name == "SECC_MDOI_1.2")) is None
        )

    def test_시료째_옮기면_두께만_다른_재료가_생기고_이름이_시험까지_따라간다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        workspace: Workspace,
    ) -> None:
        material, first, pair, _, lone = _setup(client, admin_headers)
        run = _run(db, workspace, pair[0])

        done = client.post(
            "/api/specimens/relocate",
            json=_ask([one["id"] for one in pair]),
            headers=admin_headers,
        )
        assert done.status_code == 200, done.text
        body = done.json()
        assert body["moved"] == 2 and body["test_runs"] == 1
        assert body["created_materials"] == ["SECC_MDOI_1.2"]
        assert body["split_samples"] == 0

        made = client.get(
            "/api/materials", params={"q": "SECC_MDOI_1.2"}, headers=admin_headers
        )
        target = made.json()["items"][0]
        # **복사본이다 — 두께만 다르다.**
        for key in (
            "family",
            "category",
            "grade",
            "details",
            "alias",
            "density",
            "poisson_ratio",
        ):
            assert target[key] == material[key], key
        assert target["applied_products"] == ["범퍼"]
        assert target["spec_thickness"] == pytest.approx(0.0012)

        db.expire_all()
        sample = db.get(Sample, uuid.UUID(first["id"]))
        assert sample is not None
        assert sample.material_id == uuid.UUID(target["id"])
        assert sample.record_name == "SECC_MDOI_1.2__01"
        specimen = db.get(Specimen, uuid.UUID(pair[0]["id"]))
        assert specimen is not None and specimen.record_name == "SECC_MDOI_1.2__01__MD_01"
        moved_run = db.get(TestRun, run.id)
        assert moved_run is not None
        assert moved_run.record_name == "SECC_MDOI_1.2__01__MD_01__TEN_01"
        # 원 재료에는 제대로 들어간 시료만 남는다.
        still = db.get(Specimen, uuid.UUID(lone["id"]))
        assert still is not None and still.record_name.startswith("SECC_MDOI_1.0__02")
        assert (
            db.scalar(select(AuditEntry).where(AuditEntry.action == "specimens.relocated"))
            is not None
        )

    def test_일부만_옮기면_같은_로트로_새_시료를_만든다(
        self, client: TestClient, admin_headers: dict[str, str], db: Session
    ) -> None:
        _, first, pair, _, _ = _setup(client, admin_headers)
        done = client.post(
            "/api/specimens/relocate", json=_ask([pair[1]["id"]]), headers=admin_headers
        )
        assert done.status_code == 200, done.text
        assert done.json()["split_samples"] == 1

        db.expire_all()
        moved = db.get(Specimen, uuid.UUID(pair[1]["id"]))
        assert moved is not None
        fresh = db.get(Sample, moved.sample_id)
        assert fresh is not None and fresh.id != uuid.UUID(first["id"])
        # 로트 정보가 따라간다 — 어느 로트에서 잘랐는지는 시편의 정체성이다.
        assert (fresh.lot_no, fresh.manufacturer) == ("L1", "포스코")
        assert moved.record_name == "SECC_MDOI_1.2__01__MD_01"
        stayed = db.get(Specimen, uuid.UUID(pair[0]["id"]))
        assert stayed is not None and stayed.sample_id == uuid.UUID(first["id"])

    def test_같은_이름의_재료가_있으면_그리로_합친다(
        self, client: TestClient, admin_headers: dict[str, str], db: Session
    ) -> None:
        _, _, _, second, lone = _setup(client, admin_headers)
        existing = _material(client, admin_headers, spec_thickness=1.2)
        _sample(client, admin_headers, existing["id"], lot_no="L9")

        plan = client.post(
            "/api/specimens/relocate-plan", json=_ask([lone["id"]]), headers=admin_headers
        ).json()
        assert plan["targets"][0]["exists"] is True
        assert plan["targets"][0]["to_material_id"] == existing["id"]

        done = client.post(
            "/api/specimens/relocate", json=_ask([lone["id"]]), headers=admin_headers
        ).json()
        assert done["joined_materials"] == ["SECC_MDOI_1.2"]
        assert done["created_materials"] == []
        db.expire_all()
        sample = db.get(Sample, uuid.UUID(second["id"]))
        # 있던 시료 다음 번호를 받는다.
        assert sample is not None and sample.record_name == "SECC_MDOI_1.2__02"

    def test_이미_그_두께면_막고_이유를_준다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        _, _, pair, _, _ = _setup(client, admin_headers)
        ask = {**_ask([pair[0]["id"]]), "spec_thickness": 1.0}
        plan = client.post(
            "/api/specimens/relocate-plan", json=ask, headers=admin_headers
        ).json()
        assert plan["specimens"] == 0
        assert any("이미 1 mm" in one for one in plan["blocked"])
        refused = client.post("/api/specimens/relocate", json=ask, headers=admin_headers)
        assert refused.status_code == 422, refused.text
        assert refused.json()["error"]["code"] == "MNX-MATERIALS-0043"


class Test카드:
    def test_확정_카드에도_코멘트가_붙고_옮기는_것은_막지_않는다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        workspace: Workspace,
    ) -> None:
        material, _, pair, _, _ = _setup(client, admin_headers)
        run = _run(db, workspace, pair[0])
        card = _card(db, material["id"], [run], "published")

        plan = client.post(
            "/api/specimens/relocate-plan", json=_ask([pair[0]["id"]]), headers=admin_headers
        ).json()
        assert [(one["id"], one["status"], one["can_deprecate"]) for one in plan["cards"]] == [
            (str(card.id), "published", True)
        ]

        done = client.post(
            "/api/specimens/relocate",
            json=_ask([pair[0]["id"]], comment="두께 오기 — 실측 1.2 mm"),
            headers=admin_headers,
        )
        assert done.status_code == 200, done.text
        assert done.json()["cards_noted"] == 1 and done.json()["cards_deprecated"] == 0

        shown = client.get(f"/api/fitting/cards/{card.id}", headers=admin_headers).json()
        assert shown["status"] == "published", "코멘트만 고르면 카드는 그대로다"
        [remark] = shown["remarks"]
        assert remark["kind"] == "relocated"
        assert (
            "근거 시험 1건이 다른 두께의 재료 SECC_MDOI_1.2 로 옮겨졌습니다"
            in remark["message"]
        )
        assert remark["comment"] == "두께 오기 — 실측 1.2 mm"
        assert remark["created_by_name"] == "시스템 관리자"
        # 목록에도 실린다(한 번에 읽는다).
        listed = client.get(
            "/api/fitting/cards", params={"material_id": material["id"]}, headers=admin_headers
        ).json()
        assert [len(one["remarks"]) for one in listed["items"]] == [1]

    def test_정리를_고르면_사용_중지하고_코멘트도_남긴다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        workspace: Workspace,
    ) -> None:
        material, _, pair, _, _ = _setup(client, admin_headers)
        run = _run(db, workspace, pair[0])
        card = _card(db, material["id"], [run], "published")

        done = client.post(
            "/api/specimens/relocate",
            json=_ask([pair[0]["id"]], card_actions={str(card.id): "deprecate"}),
            headers=admin_headers,
        )
        assert done.status_code == 200, done.text
        assert done.json()["cards_deprecated"] == 1
        shown = client.get(f"/api/fitting/cards/{card.id}", headers=admin_headers).json()
        assert shown["status"] == "deprecated"
        assert len(shown["remarks"]) == 1

    def test_정리할_권한이_없으면_아무것도_안_옮기고_코멘트만이면_옮긴다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        workspace: Workspace,
    ) -> None:
        """확정 카드의 사용 중지는 자료 관리자만(ADR 0035). **옮기는 것은 막지 않는다** —
        코멘트만 고르면 간다. 다만 정리를 골랐는데 못 하면 옮기기 전에 멈춘다."""
        made = client.post(
            "/api/accounts",
            json={
                "email": "member@example.com",
                "display_name": "구성원",
                "workspace_slug": workspace.slug,
                "role": "member",
            },
            headers=admin_headers,
        )
        assert made.status_code in (200, 201), made.text
        token = client.post(
            "/api/auth/login",
            json={
                "email": "member@example.com",
                "password": made.json()["temporary_password"],
            },
        ).json()["access_token"]
        member = {"Authorization": f"Bearer {token}"}

        # 새 기준정보 값은 자료 관리자만 세운다 — 관리자가 먼저 같은 분류의 재료를 둔다.
        _material(client, admin_headers, spec_thickness=2.0)
        material, _, pair, _, _ = _setup(client, member, rich=False)
        run = _run(db, workspace, pair[0])
        card = _card(db, material["id"], [run], "published")

        plan = client.post(
            "/api/specimens/relocate-plan", json=_ask([pair[0]["id"]]), headers=member
        ).json()
        assert plan["cards"][0]["can_deprecate"] is False
        assert "자료 관리자" in plan["cards"][0]["reason"]

        refused = client.post(
            "/api/specimens/relocate",
            json=_ask([pair[0]["id"]], card_actions={str(card.id): "deprecate"}),
            headers=member,
        )
        assert refused.status_code == 403, refused.text
        assert refused.json()["error"]["code"] == "MNX-MATERIALS-0042"
        db.expire_all()
        untouched = db.get(Specimen, uuid.UUID(pair[0]["id"]))
        assert untouched is not None and untouched.record_name.startswith("SECC_MDOI_1.0")

        done = client.post(
            "/api/specimens/relocate", json=_ask([pair[0]["id"]]), headers=member
        )
        assert done.status_code == 200, done.text
        shown = client.get(f"/api/fitting/cards/{card.id}", headers=member).json()
        assert shown["status"] == "published"
        assert len(shown["remarks"]) == 1

    def test_권한_밖의_시편은_이유와_함께_빠지고_나머지는_간다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        workspace: Workspace,
    ) -> None:
        other = client.post(
            "/api/accounts",
            json={
                "email": "other@example.com",
                "display_name": "다른 사람",
                "workspace_slug": workspace.slug,
                "role": "member",
            },
            headers=admin_headers,
        )
        assert other.status_code in (200, 201), other.text
        token = client.post(
            "/api/auth/login",
            json={
                "email": "other@example.com",
                "password": other.json()["temporary_password"],
            },
        ).json()["access_token"]
        someone = {"Authorization": f"Bearer {token}"}

        _, _, pair, _, _ = _setup(client, admin_headers)  # 관리자가 등록한 시편
        _material(client, admin_headers, grade="SPCC", spec_thickness=2.0)  # 값을 먼저 세운다
        mine_material = _material(client, someone, grade="SPCC")
        mine = _specimen(client, someone, _sample(client, someone, mine_material["id"])["id"])

        plan = client.post(
            "/api/specimens/relocate-plan",
            json=_ask([pair[0]["id"], mine["id"]]),
            headers=someone,
        ).json()
        assert plan["specimens"] == 1
        assert len(plan["blocked"]) == 1 and pair[0]["record_name"] in plan["blocked"][0]


class Test기록:
    """묶음(글로벌 피팅)·저장한 대표 곡선 — 원 재료에 **그때의 기록으로 남는다.**"""

    def _records(
        self, db: Session, workspace: Workspace, material_id: str, runs: list[TestRun]
    ) -> GroupResult:
        group = GroupResult(
            workspace_id=workspace.id,
            material_id=uuid.UUID(material_id),
            plugin_id="tensile.rate_family",
            members=[{"test_run_id": str(run.id), "label": run.record_name} for run in runs],
            detail={"rates": [{"rate": 0.001}]},
        )
        ensemble = EnsembleResult(
            material_id=uuid.UUID(material_id),
            test_type_id=runs[0].test_type_id,
            orientation="MD",
            sample_count=len(runs),
            test_run_ids=[str(run.id) for run in runs],
        )
        db.add_all([group, ensemble])
        db.commit()
        return group

    def test_계획이_옮기는_시험을_쓴_기록을_알린다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        workspace: Workspace,
    ) -> None:
        material, _, pair, _, _ = _setup(client, admin_headers)
        runs = [_run(db, workspace, one) for one in pair]
        self._records(db, workspace, material["id"], runs)

        plan = client.post(
            "/api/specimens/relocate-plan", json=_ask([pair[0]["id"]]), headers=admin_headers
        ).json()
        assert len(plan["records"]) == 2, plan["records"]
        grouped, ensemble = plan["records"]
        assert "구성원 1/2개" in grouped and "새 카드를 만들 수 없습니다" in grouped
        assert "대표 곡선(MD)" in ensemble and "시험 1/2건" in ensemble

    def test_옮겨진_시험이_든_묶음으로는_카드를_새로_만들지_않는다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        workspace: Workspace,
    ) -> None:
        """**두께가 다른 근거가 조용히 섞인 카드**가 원 재료에 서는 길을 막는다."""
        material, _, pair, _, _ = _setup(client, admin_headers)
        runs = [_run(db, workspace, one) for one in pair]
        group = self._records(db, workspace, material["id"], runs)
        done = client.post(
            "/api/specimens/relocate", json=_ask([pair[0]["id"]]), headers=admin_headers
        )
        assert done.status_code == 200, done.text

        refused = client.post(
            "/api/fitting/cards/rate-dependent",
            json={"group_result_id": str(group.id), "label": "옛 묶음"},
            headers=admin_headers,
        )
        assert refused.status_code == 422, refused.text
        assert refused.json()["error"]["code"] == "MNX-FITTING-0044"
        assert "SECC_MDOI_1.2__01__MD_01__TEN_01" in refused.json()["error"]["message"]
