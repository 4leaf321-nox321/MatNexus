"""물성 분류 — **분야 ⊃ 물성군 ⊃ 물성** (ADR 0054, 2026-10-03).

요청: 「물성군을 만드는 기능을 만들어서 이 안에 만들자. 물성 분야 - 물성군 - 물성 세 레벨로,
분야 · 군 · 물성 순서로 포함관계가 있는 형태야. 그 데이터 정보가 있으니까, 그걸 밀어 넣을 수
있게.」
그리고 물성 목록(문헌 + 사내)을 Standard Platform(SP)이 읽어 가게 한다.

이 시험이 지키는 것:

    씨앗      키 앞머리 열둘이 분야로 선다. 고친 이름 · 폐기한 분야를 배포가 되돌리지 않는다
    포함      물성은 한 군에만, 군은 한 분야에만 든다. 비우지 않은 군 · 분야는 폐기 못 한다
    판정      고치기 · 밀어 넣기는 자료 관리자만. 보기는 누구나
    밀어 넣기  미리 보기는 아무것도 안 바꾼다. 오류가 한 줄이라도 있으면 하나도 안 넣는다.
              물성은 키 · 이름 · 별칭이 정확히 하나에 맞을 때만 — 비슷한 것을 골라 주지 않는다
    바깥 목록  SP 연동 지침 §3.1 의 모양 — 평평한 행, 키 차례, 폐기도 행으로, 깎지 않고 거절
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.accounts.models import User
from app.modules.audit.models import AuditEntry
from app.modules.auth import security
from app.modules.catalog import taxonomy
from app.modules.catalog.models import CatalogDefinition
from app.modules.catalog.ontology_models import PropertyAlias
from app.modules.catalog.taxonomy_models import (
    PropertyField,
    PropertyGroup,
    PropertyGroupMember,
)
from app.modules.workspaces.models import Workspace, WorkspaceMember
from app.shared import audit
from app.shared.text import compare_key

PASSWORD = "Passw0rd!taxonomy"
YIELD = "mechanical.yield_strength"
UTS = "mechanical.tensile_strength"
MODULUS = "mechanical.youngs_modulus"
PASTE = "rheological.yield_stress"
CTE = "thermal.cte_linear"
LOCAL = "local.mechanical.flexural_modulus_wet"

API = "/api/catalog/taxonomy"


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


@pytest.fixture()
def defined(db: Session) -> dict[str, CatalogDefinition]:
    """문헌 다섯 + 사내 하나. 「항복」 이 붙은 이름 둘은 뜻이 다르다."""
    rows = {
        YIELD: CatalogDefinition(
            key=YIELD, domain="mechanical", name="항복강도", si_unit="Pa", value_type="numeric"
        ),
        UTS: CatalogDefinition(
            key=UTS, domain="mechanical", name="인장강도", si_unit="Pa", value_type="numeric"
        ),
        MODULUS: CatalogDefinition(
            key=MODULUS, domain="mechanical", name="영률", si_unit="Pa", value_type="numeric"
        ),
        PASTE: CatalogDefinition(
            key=PASTE,
            domain="rheological",
            name="항복응력",
            si_unit="Pa",
            value_type="numeric",
        ),
        CTE: CatalogDefinition(
            key=CTE,
            domain="thermal",
            name="선팽창계수",
            si_unit="1/K",
            value_type="numeric",
            condition_axes=["temperature_k"],
        ),
        LOCAL: CatalogDefinition(
            key=LOCAL,
            domain="mechanical",
            name="흡습 굴곡탄성률",
            si_unit="Pa",
            value_type="numeric",
        ),
    }
    db.add_all(rows.values())
    db.add(
        PropertyAlias(
            property_key=UTS, alias="UTS", normalized=compare_key("UTS"), source="manual"
        )
    )
    db.add(
        PropertyAlias(
            property_key=UTS,
            alias="Rm",
            normalized=compare_key("Rm"),
            source="standard",
        )
    )
    db.commit()
    taxonomy.ensure_builtin_property_fields(db)
    db.commit()
    return rows


@pytest.fixture()
def steward(client: TestClient, db: Session, workspace: Workspace) -> dict[str, str]:
    _user(db, workspace, "steward", is_data_manager=True)
    return _headers(client, "steward")


@pytest.fixture()
def member(client: TestClient, db: Session, workspace: Workspace) -> dict[str, str]:
    _user(db, workspace, "member")
    return _headers(client, "member")


def _tree(client: TestClient, headers: dict[str, str]) -> dict[str, Any]:
    got = client.get(API, headers=headers)
    assert got.status_code == 200, got.text
    body: dict[str, Any] = got.json()
    return body


def _group_of(tree: dict[str, Any], key: str) -> str | None:
    found: str | None = next(
        one["group_key"] for one in tree["properties"] if one["key"] == key
    )
    return found


def _new_group(
    client: TestClient, headers: dict[str, str], field_key: str, name: str, **extra: Any
) -> dict[str, Any]:
    got = client.post(
        f"{API}/groups", headers=headers, json={"field_key": field_key, "name": name, **extra}
    )
    assert got.status_code == 201, got.text
    body: dict[str, Any] = got.json()
    return body


class Test씨앗:
    def test_키_앞머리_열둘이_분야로_서고_두_번째는_할_일이_없다(
        self, db: Session, defined: dict[str, CatalogDefinition]
    ) -> None:
        keys = set(db.scalars(select(PropertyField.key)))
        assert keys == set(taxonomy.SEED_FIELDS)
        assert taxonomy.ensure_builtin_property_fields(db) == []

    def test_고친_이름과_폐기한_분야를_배포가_되돌리지_않는다(
        self, db: Session, defined: dict[str, CatalogDefinition]
    ) -> None:
        mechanical = db.scalar(select(PropertyField).where(PropertyField.key == "mechanical"))
        acoustic = db.scalar(select(PropertyField).where(PropertyField.key == "acoustic"))
        assert mechanical is not None and acoustic is not None
        mechanical.name = "기계적 물성"
        acoustic.retired_at = taxonomy._now()
        db.commit()

        assert taxonomy.ensure_builtin_property_fields(db) == []
        db.refresh(mechanical)
        db.refresh(acoustic)
        assert mechanical.name == "기계적 물성"
        assert acoustic.retired_at is not None


class Test판정:
    def test_보기는_누구나_고치기는_자료_관리자만(
        self,
        client: TestClient,
        defined: dict[str, CatalogDefinition],
        member: dict[str, str],
    ) -> None:
        tree = _tree(client, member)
        assert {one["key"] for one in tree["properties"]} == set(defined)
        assert all(one["group_key"] is None for one in tree["properties"])

        for method, path, body in (
            ("post", f"{API}/fields", {"name": "새 분야"}),
            ("patch", f"{API}/fields/mechanical", {"name": "기계 2"}),
            ("post", f"{API}/groups", {"field_key": "mechanical", "name": "강도"}),
            ("put", f"{API}/members", {"group_key": None, "property_keys": [YIELD]}),
            ("post", f"{API}/import", {"rows": [{"field": "기계", "group": "강도"}]}),
        ):
            got = client.request(method, path, headers=member, json=body)
            assert got.status_code == 403, (path, got.text)
            assert got.json()["error"]["code"] == "MNX-CATALOG-0055"


class Test고치기:
    def test_군을_만들면_키를_지어_주고_준_키는_그대로_쓴다(
        self,
        client: TestClient,
        defined: dict[str, CatalogDefinition],
        steward: dict[str, str],
    ) -> None:
        first = _new_group(client, steward, "mechanical", "강도")
        assert first["key"] == "pg-0001" and first["field_key"] == "mechanical"
        given = _new_group(client, steward, "mechanical", "탄성", key="SP-PG-7")
        assert given["key"] == "SP-PG-7"
        # 사람이 준 키가 지어 줄 차례와 겹치면 건너뛴다.
        _new_group(client, steward, "thermal", "팽창", key="pg-0002")
        assert _new_group(client, steward, "thermal", "전도")["key"] == "pg-0003"

    def test_같은_이름은_한_분야_안에서만_막는다(
        self,
        client: TestClient,
        defined: dict[str, CatalogDefinition],
        steward: dict[str, str],
    ) -> None:
        _new_group(client, steward, "mechanical", "강도")
        again = client.post(
            f"{API}/groups",
            headers=steward,
            json={"field_key": "mechanical", "name": " 강도 "},
        )
        assert again.status_code == 409
        assert again.json()["error"]["code"] == "MNX-CATALOG-0058"
        # 다른 분야면 같은 이름이어도 된다.
        _new_group(client, steward, "thermal", "강도")

        same_field = client.post(f"{API}/fields", headers=steward, json={"name": "기계"})
        assert same_field.status_code == 409

    def test_쓸_수_없는_키는_거절한다(
        self,
        client: TestClient,
        defined: dict[str, CatalogDefinition],
        steward: dict[str, str],
    ) -> None:
        for bad in ("a b", "a/b", "a?b"):
            got = client.post(
                f"{API}/fields", headers=steward, json={"name": "새", "key": bad}
            )
            assert got.status_code == 422, bad
            assert got.json()["error"]["code"] == "MNX-CATALOG-0056"

    def test_부분_수정은_안_보낸_칸을_안_건드리고_null_은_비운다(
        self,
        client: TestClient,
        defined: dict[str, CatalogDefinition],
        steward: dict[str, str],
    ) -> None:
        made = client.post(
            f"{API}/fields",
            headers=steward,
            json={"name": "구조재", "description": "구조용 물성"},
        ).json()
        assert made["key"] == "pf-0001"

        renamed = client.patch(
            f"{API}/fields/pf-0001", headers=steward, json={"name": "구조 재료"}
        )
        assert renamed.json()["description"] == "구조용 물성"  # 안 보낸 칸은 그대로
        cleared = client.patch(
            f"{API}/fields/pf-0001", headers=steward, json={"description": None}
        )
        assert cleared.json()["description"] is None
        assert cleared.json()["name"] == "구조 재료"

    def test_비우지_않은_군과_분야는_폐기하지_못한다(
        self,
        client: TestClient,
        defined: dict[str, CatalogDefinition],
        steward: dict[str, str],
    ) -> None:
        group = _new_group(client, steward, "mechanical", "강도")
        client.put(
            f"{API}/members",
            headers=steward,
            json={"group_key": group["key"], "property_keys": [YIELD]},
        )
        refused = client.patch(
            f"{API}/groups/{group['key']}", headers=steward, json={"retired": True}
        )
        assert refused.status_code == 409
        assert refused.json()["error"]["code"] == "MNX-CATALOG-0062"
        field_refused = client.patch(
            f"{API}/fields/mechanical", headers=steward, json={"retired": True}
        )
        assert field_refused.status_code == 409

        client.put(
            f"{API}/members",
            headers=steward,
            json={"group_key": None, "property_keys": [YIELD]},
        )
        retired = client.patch(
            f"{API}/groups/{group['key']}", headers=steward, json={"retired": True}
        )
        assert retired.status_code == 200 and retired.json()["retired"] is True
        # 폐기한 군에는 못 넣는다.
        blocked = client.put(
            f"{API}/members",
            headers=steward,
            json={"group_key": group["key"], "property_keys": [UTS]},
        )
        assert blocked.status_code == 409
        restored = client.patch(
            f"{API}/groups/{group['key']}", headers=steward, json={"retired": False}
        )
        assert restored.json()["retired"] is False

    def test_군을_다른_분야로_옮기면_키는_그대로고_물성이_함께_간다(
        self,
        client: TestClient,
        defined: dict[str, CatalogDefinition],
        steward: dict[str, str],
    ) -> None:
        group = _new_group(client, steward, "mechanical", "팽창")
        client.put(
            f"{API}/members",
            headers=steward,
            json={"group_key": group["key"], "property_keys": [CTE]},
        )
        moved = client.patch(
            f"{API}/groups/{group['key']}", headers=steward, json={"field_key": "thermal"}
        )
        assert moved.status_code == 200
        assert moved.json()["key"] == group["key"] and moved.json()["field_key"] == "thermal"
        tree = _tree(client, steward)
        assert _group_of(tree, CTE) == group["key"]
        thermal = next(one for one in tree["fields"] if one["key"] == "thermal")
        assert thermal["property_count"] == 1 and thermal["group_count"] == 1


class Test소속:
    def test_넣고_옮기고_빼며_물성_하나는_한_군에만_든다(
        self,
        client: TestClient,
        db: Session,
        defined: dict[str, CatalogDefinition],
        steward: dict[str, str],
    ) -> None:
        strength = _new_group(client, steward, "mechanical", "강도")
        elastic = _new_group(client, steward, "mechanical", "탄성")
        before = defined[YIELD].updated_at

        got = client.put(
            f"{API}/members",
            headers=steward,
            json={"group_key": strength["key"], "property_keys": [YIELD, UTS, LOCAL]},
        )
        assert got.status_code == 200
        assert sorted(got.json()["changed"]) == sorted([YIELD, UTS, LOCAL])

        again = client.put(
            f"{API}/members",
            headers=steward,
            json={"group_key": elastic["key"], "property_keys": [YIELD, MODULUS]},
        ).json()
        assert sorted(again["changed"]) == sorted([YIELD, MODULUS])
        rows = db.scalars(
            select(PropertyGroupMember).where(PropertyGroupMember.property_key == YIELD)
        ).all()
        assert len(rows) == 1  # 옮겨졌지, 둘이 되지 않았다

        out = client.put(
            f"{API}/members", headers=steward, json={"group_key": None, "property_keys": [UTS]}
        ).json()
        assert out["changed"] == [UTS]
        tree = _tree(client, steward)
        assert _group_of(tree, YIELD) == elastic["key"]
        assert _group_of(tree, UTS) is None
        assert _group_of(tree, LOCAL) == strength["key"]

        # 바깥이 읽는 물성 행에 군이 실리므로 정의의 `updated_at` 이 움직인다.
        db.expire_all()
        assert db.get(CatalogDefinition, defined[YIELD].id).updated_at > before  # type: ignore[union-attr]

        entries = db.scalars(
            select(AuditEntry).where(AuditEntry.action == audit.PROPERTY_TAXONOMY_ASSIGNED)
        ).all()
        assert len(entries) == 3

    def test_없는_물성은_하나도_안_넣는다(
        self,
        client: TestClient,
        db: Session,
        defined: dict[str, CatalogDefinition],
        steward: dict[str, str],
    ) -> None:
        group = _new_group(client, steward, "mechanical", "강도")
        got = client.put(
            f"{API}/members",
            headers=steward,
            json={"group_key": group["key"], "property_keys": [YIELD, "mechanical.nope"]},
        )
        assert got.status_code == 404
        assert got.json()["error"]["code"] == "MNX-CATALOG-0063"
        assert db.scalars(select(PropertyGroupMember)).all() == []


def _import(
    client: TestClient, headers: dict[str, str], rows: list[dict[str, Any]], *, dry_run: bool
) -> Any:
    return client.post(
        f"{API}/import", headers=headers, json={"rows": rows, "dry_run": dry_run}
    )


class Test밀어_넣기:
    ROWS: list[dict[str, Any]] = [  # noqa: RUF012
        {"field": "기계", "group": "강도", "property": YIELD},  # 키로
        {"field": "기계", "group": "강도", "property": "인장강도"},  # 이름으로
        {"field": "mechanical", "group": "탄성", "property": "영률"},  # 분야 칸에 키
        {"field": "열 · 물리", "group": "팽창", "property": CTE},  # 새 분야
        {"field": "기계", "group": "흡습", "group_key": "SP-PG-9", "property": LOCAL},
        {"field": "기계", "group": "피로"},  # 물성 없이 — 빈 군
        {},  # 빈 줄은 건너뛴다
    ]

    def test_미리_보기는_아무것도_안_바꾸고_무엇이_생기는지_말한다(
        self,
        client: TestClient,
        db: Session,
        defined: dict[str, CatalogDefinition],
        steward: dict[str, str],
    ) -> None:
        got = _import(client, steward, self.ROWS, dry_run=True)
        assert got.status_code == 200, got.text
        plan = got.json()
        assert plan["applied"] is False and plan["errors"] == []

        fields = {one["name"]: one for one in plan["fields"]}
        assert (
            fields["기계"]["action"] == "unchanged" and fields["기계"]["key"] == "mechanical"
        )
        assert fields["열 · 물리"]["action"] == "create"
        assert fields["열 · 물리"]["key"] == "pf-0001"
        groups = {one["name"]: one for one in plan["groups"]}
        assert {one["action"] for one in groups.values()} == {"create"}
        assert groups["흡습"]["key"] == "SP-PG-9"
        # 사람이 준 키와 안 겹치게 차례로 지어 준다.
        assert sorted(one["key"] for one in plan["groups"]) == sorted(
            ["pg-0001", "pg-0002", "pg-0003", "pg-0004", "SP-PG-9"]
        )
        members = {one["property_key"]: one for one in plan["members"]}
        assert set(members) == {YIELD, UTS, MODULUS, CTE, LOCAL}
        assert {one["action"] for one in members.values()} == {"assign"}

        assert db.scalars(select(PropertyGroup)).all() == []
        assert db.scalars(select(PropertyGroupMember)).all() == []
        assert len(db.scalars(select(PropertyField)).all()) == len(taxonomy.SEED_FIELDS)

    def test_넣고_나면_트리가_그대로고_다시_넣으면_바뀌는_것이_없다(
        self,
        client: TestClient,
        db: Session,
        defined: dict[str, CatalogDefinition],
        steward: dict[str, str],
    ) -> None:
        got = _import(client, steward, self.ROWS, dry_run=False)
        assert got.status_code == 200, got.text
        assert got.json()["applied"] is True

        tree = _tree(client, steward)
        groups = {one["key"]: one for one in tree["groups"]}
        assert groups[_group_of(tree, YIELD)]["name"] == "강도"
        assert _group_of(tree, YIELD) == _group_of(tree, UTS)
        assert groups["SP-PG-9"]["field_key"] == "mechanical"
        assert _group_of(tree, LOCAL) == "SP-PG-9"
        assert _group_of(tree, PASTE) is None  # 안 적은 것은 그대로
        empty = next(one for one in tree["groups"] if one["name"] == "피로")
        assert empty["property_count"] == 0

        again = _import(client, steward, self.ROWS, dry_run=True).json()
        assert {one["action"] for one in again["fields"]} == {"unchanged"}
        assert {one["action"] for one in again["groups"]} == {"unchanged"}
        assert {one["action"] for one in again["members"]} == {"unchanged"}

        entry = db.scalar(
            select(AuditEntry).where(AuditEntry.action == audit.PROPERTY_TAXONOMY_IMPORTED)
        )
        assert entry is not None
        assert entry.changes["members"]["after"]["assign"] == 5

    @pytest.mark.parametrize(
        ("row", "message"),
        [
            ({"field": "기계", "group": "강도", "property": "없는 물성"}, "찾을 수 없습니다"),
            # 이름만 맞춰 고르지 않는다 — 「항복」 은 두 물성에 걸친다(부분 일치는 안 본다).
            ({"field": "기계", "group": "강도", "property": "항복"}, "찾을 수 없습니다"),
            ({"field": "기계", "property": YIELD}, "물성군이 비었습니다"),
            ({"group": "강도", "property": YIELD}, "분야가 비었습니다"),
            ({"field_key": "SP-F-1", "group": "강도"}, "이름이 필요합니다"),
            ({"field": "기계", "group": "강도", "group_key": "a b"}, "쓸 수 없습니다"),
        ],
    )
    def test_오류가_한_줄이라도_있으면_하나도_안_넣는다(
        self,
        client: TestClient,
        db: Session,
        defined: dict[str, CatalogDefinition],
        steward: dict[str, str],
        row: dict[str, Any],
        message: str,
    ) -> None:
        rows = [{"field": "기계", "group": "탄성", "property": MODULUS}, row]
        plan = _import(client, steward, rows, dry_run=True).json()
        assert [one["row"] for one in plan["errors"]] == [2]
        assert message in plan["errors"][0]["message"]

        refused = _import(client, steward, rows, dry_run=False)
        assert refused.status_code == 422
        assert refused.json()["error"]["code"] == "MNX-CATALOG-0064"
        # 성한 첫 줄도 안 들어갔다 — 분류가 반만 들어가지 않는다.
        assert db.scalars(select(PropertyGroup)).all() == []
        assert db.scalars(select(PropertyGroupMember)).all() == []

    def test_같은_물성을_두_군에_적으면_오류다(
        self,
        client: TestClient,
        defined: dict[str, CatalogDefinition],
        steward: dict[str, str],
    ) -> None:
        rows = [
            {"field": "기계", "group": "강도", "property": UTS},
            {"field": "기계", "group": "탄성", "property": "UTS"},  # 별칭으로 같은 물성
        ]
        plan = _import(client, steward, rows, dry_run=True).json()
        assert len(plan["errors"]) == 1
        assert "두 물성군" in plan["errors"][0]["message"]

    def test_이름이_맞아도_다른_분야의_물성이면_미리_보기에_세운다(
        self,
        client: TestClient,
        defined: dict[str, CatalogDefinition],
        steward: dict[str, str],
    ) -> None:
        """「항복응력」 은 유변학 물성이다 — 기계 > 강도에 적으면 금속의 항복강도가 아니라
        페이스트가 흐르는 응력이 들어간다. 정확히 맞는 이름이라 오류는 아니지만 세워 보인다."""
        rows = [
            {"field": "기계", "group": "강도", "property": "항복응력"},
            {"field": "기계", "group": "강도", "property": "항복강도"},
            {"field": "구조재", "group": "강도", "property": CTE},  # 새 분야 — 견줄 수 없다
        ]
        plan = _import(client, steward, rows, dry_run=True).json()
        assert plan["errors"] == []
        flags = {one["property_key"]: one["cross_domain"] for one in plan["members"]}
        assert flags == {PASTE: True, YIELD: False, CTE: False}
        paste = next(one for one in plan["members"] if one["property_key"] == PASTE)
        assert paste["domain"] == "rheological"

    def test_이름이_같은_물성이_둘이면_키로_적으라고_한다(
        self,
        client: TestClient,
        db: Session,
        defined: dict[str, CatalogDefinition],
        steward: dict[str, str],
    ) -> None:
        db.add(
            CatalogDefinition(
                key="local.mechanical.yield_strength_copy",
                domain="mechanical",
                name="항복강도",
                value_type="numeric",
            )
        )
        db.commit()
        plan = _import(
            client,
            steward,
            [{"field": "기계", "group": "강도", "property": "항복강도"}],
            dry_run=True,
        ).json()
        assert "2개입니다" in plan["errors"][0]["message"]

    def test_키를_주면_이름을_맞추고_다른_분야의_군은_옮긴다(
        self,
        client: TestClient,
        defined: dict[str, CatalogDefinition],
        steward: dict[str, str],
    ) -> None:
        group = _new_group(client, steward, "mechanical", "팽창", key="SP-PG-1")
        rows = [
            {
                "field": "기계적 물성",
                "field_key": "mechanical",
                "group": "강도",
                "property": YIELD,
            },
            {"field": "열", "group": "열팽창", "group_key": "SP-PG-1", "property": CTE},
        ]
        plan = _import(client, steward, rows, dry_run=True).json()
        assert plan["errors"] == []
        mechanical = next(one for one in plan["fields"] if one["key"] == "mechanical")
        assert mechanical["action"] == "update" and mechanical["before_name"] == "기계"
        moved = next(one for one in plan["groups"] if one["key"] == group["key"])
        assert moved["action"] == "move"
        assert moved["before_field_key"] == "mechanical" and moved["field_key"] == "thermal"
        assert moved["before_name"] == "팽창"

        assert _import(client, steward, rows, dry_run=False).status_code == 200
        tree = _tree(client, steward)
        assert next(one for one in tree["fields"] if one["key"] == "mechanical")["name"] == (
            "기계적 물성"
        )
        thermal_group = next(one for one in tree["groups"] if one["key"] == "SP-PG-1")
        assert thermal_group["field_key"] == "thermal" and thermal_group["name"] == "열팽창"


def _flat(item: dict[str, Any]) -> bool:
    return all(
        isinstance(value, str | int | float | bool) or value is None for value in item.values()
    )


class Test바깥_목록:
    def test_물성_행은_평평하고_군_분야_별칭이_실린다(
        self,
        client: TestClient,
        db: Session,
        defined: dict[str, CatalogDefinition],
        steward: dict[str, str],
        member: dict[str, str],
    ) -> None:
        group = _new_group(client, steward, "mechanical", "강도")
        client.put(
            f"{API}/members",
            headers=steward,
            json={"group_key": group["key"], "property_keys": [UTS]},
        )
        defined[PASTE].deprecated_at = taxonomy._now()
        defined[PASTE].superseded_by = YIELD
        db.commit()

        got = client.get("/api/catalog/feed/properties", headers=member)
        assert got.status_code == 200, got.text
        body = got.json()
        assert set(body) == {"items", "total", "page", "page_size"}
        assert body["total"] == len(defined) and body["page"] == 1 and body["page_size"] == 500
        items = {one["key"]: one for one in body["items"]}
        assert [one["key"] for one in body["items"]] == sorted(items)  # 키 차례
        assert all(_flat(one) for one in body["items"])

        uts = items[UTS]
        assert uts["group_key"] == group["key"] and uts["group_name"] == "강도"
        assert uts["field_key"] == "mechanical" and uts["field_name"] == "기계"
        assert uts["aliases"] == "Rm;UTS"  # SP 가 `;` 로 가른다
        assert uts["origin"] == "literature" and uts["is_active"] is True
        assert uts["deleted"] is False
        assert items[LOCAL]["origin"] == "local"
        assert items[CTE]["condition_axes"] == "temperature_k"
        assert items[YIELD]["group_key"] is None and items[YIELD]["field_key"] is None

        paste = items[PASTE]
        assert paste["is_active"] is False and paste["status"] == "deprecated"
        # SP 의 데이터 소스는 `deleted` 만 읽고 사용 중지로 바꾼다(`status` 는 대응 대상이
        # 아니다).
        assert paste["deleted"] is True
        assert paste["superseded_by"] == YIELD

        stamp = datetime.fromisoformat(uts["updated_at"].replace("Z", "+00:00"))
        assert stamp.utcoffset() is not None and stamp.utcoffset().total_seconds() == 0  # type: ignore[union-attr]

    def test_쪽을_넘기면_빠지거나_겹치는_행이_없다(
        self,
        client: TestClient,
        defined: dict[str, CatalogDefinition],
        member: dict[str, str],
    ) -> None:
        seen: list[str] = []
        page = 1
        while True:
            body = client.get(
                "/api/catalog/feed/properties",
                headers=member,
                params={"page": page, "page_size": 4},
            ).json()
            seen += [one["key"] for one in body["items"]]
            if len(body["items"]) < 4:
                break
            page += 1
        assert seen == sorted(defined)

    def test_상한을_넘게_달라면_깎지_않고_거절한다(
        self,
        client: TestClient,
        defined: dict[str, CatalogDefinition],
        member: dict[str, str],
    ) -> None:
        got = client.get(
            "/api/catalog/feed/properties",
            headers=member,
            params={"page_size": taxonomy.FEED_PAGE_MAX + 1},
        )
        assert got.status_code == 422
        assert got.json()["error"]["code"] == "MNX-CATALOG-0065"

    def test_폐기한_분야와_군도_행으로_남는다(
        self,
        client: TestClient,
        defined: dict[str, CatalogDefinition],
        steward: dict[str, str],
        member: dict[str, str],
    ) -> None:
        group = _new_group(client, steward, "acoustic", "흡음")
        client.patch(f"{API}/groups/{group['key']}", headers=steward, json={"retired": True})
        client.patch(f"{API}/fields/acoustic", headers=steward, json={"retired": True})

        fields = client.get("/api/catalog/feed/fields", headers=member).json()
        assert fields["total"] == len(taxonomy.SEED_FIELDS)
        acoustic = next(one for one in fields["items"] if one["key"] == "acoustic")
        assert acoustic["is_active"] is False and _flat(acoustic)
        assert acoustic["status"] == "deprecated"  # 연동 지침 §12-A ④
        assert acoustic["deleted"] is True  # SP 데이터 소스가 읽는 칸

        groups = client.get("/api/catalog/feed/groups", headers=member).json()
        row = next(one for one in groups["items"] if one["key"] == group["key"])
        assert row["is_active"] is False and row["field_key"] == "acoustic"
        assert row["status"] == "deprecated" and row["deleted"] is True
        assert _flat(row)

    def test_로그인_없이는_못_읽는다(
        self, client: TestClient, defined: dict[str, CatalogDefinition]
    ) -> None:
        for path in ("fields", "groups", "properties"):
            assert client.get(f"/api/catalog/feed/{path}").status_code == 401
