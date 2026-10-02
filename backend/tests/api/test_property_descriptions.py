"""물성 **정의문** — 조회가 물성의 뜻을 돌려준다(ADR 0050, 2026-10-02).

요청: 「물성 설명칸은 있지만 조회 도구가 이름 · 단위 · 기호만 돌려주고 설명을 안 준다. 물성의
정의문을 받을 필요가 있다.」 실측: 정의문 칸은 271종 전부 비어 있었다 — 원본부터 비었다.

이 시험이 지키는 것:

    조회      이름 풀기 · 물성 키 사전 · 사내 물성 항목 · 매핑 화면이 정의문을 싣는다
    한 곳     사내 항목은 같은 물성으로 이어진 키의 정의문을 낸다 — 따로 적지 않는다
    씨앗      비었거나 아무도 안 고친 정의문만 채운다 — 자료 관리자가 고친 것은 안 덮는다
    이관      원본의 빈 정의문이 사내 정의문을 지우지 않는다(배포마다 이관이 다시 돈다)
    고치기    자료 관리자만, 감사에 남는다
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.accounts.models import User
from app.modules.audit.models import AuditEntry
from app.modules.auth import security
from app.modules.catalog import descriptions, importer
from app.modules.catalog.links import ensure_builtin_property_links
from app.modules.catalog.models import CatalogDefinition
from app.modules.catalog.ontology_models import PropertyLink
from app.modules.vocabulary.definitions import ensure_builtin_property_items
from app.modules.vocabulary.models import VocabularyTerm
from app.modules.workspaces.models import Workspace, WorkspaceMember
from app.shared import audit, property_names, semantic

PASSWORD = "Passw0rd!describe"
YIELD = "mechanical.yield_strength"
PASTE = "rheological.yield_stress"


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
    """이름이 비슷한 두 물성 — 이름만으로는 못 가르고 뜻으로 가른다."""
    rows = {
        YIELD: CatalogDefinition(
            key=YIELD,
            domain="mechanical",
            name="항복강도",
            symbol="Rp0.2",
            si_unit="Pa",
            value_type="numeric",
            test_standard="ISO 6892",
        ),
        PASTE: CatalogDefinition(
            key=PASTE,
            domain="rheological",
            name="항복응력",
            symbol="tau_0",
            si_unit="Pa",
            value_type="numeric",
        ),
    }
    db.add_all(rows.values())
    db.commit()
    return rows


SEED = {
    YIELD: "금속 인장시험에서 0.2 % 소성 변형이 생기는 응력이다.",
    PASTE: "페이스트 · 젤이 흐르기 시작하는 최소 전단응력이다.",
}


class Test씨앗:
    def test_빈_정의문을_채우고_두_번째는_할_일이_없다(
        self, db: Session, defined: dict[str, CatalogDefinition]
    ) -> None:
        filled, kept = descriptions.refresh_property_descriptions(db, SEED)
        assert sorted(filled) == sorted(SEED) and kept == []
        assert defined[YIELD].description == SEED[YIELD]

        again = descriptions.refresh_property_descriptions(db, SEED)
        assert again == ([], [])

    def test_자료_관리자가_고친_것은_안_덮는다(
        self, db: Session, defined: dict[str, CatalogDefinition]
    ) -> None:
        descriptions.refresh_property_descriptions(db, SEED)
        defined[YIELD].description = "사내 정의: 0.2 % 오프셋 내력(Rp0.2)."
        db.flush()

        newer = {**SEED, YIELD: "새 씨앗 문장."}
        filled, kept = descriptions.refresh_property_descriptions(db, newer)

        assert defined[YIELD].description == "사내 정의: 0.2 % 오프셋 내력(Rp0.2)."
        assert kept == [YIELD] and filled == []

    def test_아무도_안_고쳤으면_새_씨앗을_따른다(
        self, db: Session, defined: dict[str, CatalogDefinition]
    ) -> None:
        descriptions.refresh_property_descriptions(db, SEED)

        newer = {**SEED, YIELD: "고쳐 쓴 씨앗 문장."}
        filled, _ = descriptions.refresh_property_descriptions(db, newer)

        assert filled == [YIELD]
        assert defined[YIELD].description == "고쳐 쓴 씨앗 문장."

    def test_씨앗_파일이_읽힌다(self) -> None:
        texts = descriptions.load_seed()
        assert texts[YIELD] and texts[PASTE]
        # **이름이 비슷한 두 물성을 뜻으로 가른다** — 정의문이 서로를 짚는다.
        assert "유변학" in texts[YIELD] and "항복강도" in texts[PASTE]


def _snapshot(path: Path) -> Path:
    """원본 모양의 빈 이관 파일 하나 — 정의문이 **비어 있는** 정의 한 줄."""
    db = path / "mt.db"
    con = sqlite3.connect(db)
    for table, columns in importer.EXPECTED_COLUMNS.items():
        con.execute(f"create table {table} ({', '.join(sorted(columns))})")
    con.execute(
        "insert into property_definition (id, key, domain, name, symbol, si_unit, value_type, "
        "description, test_standard, condition_axes, created_at) values "
        f"(1, '{YIELD}', 'mechanical', '항복강도', 'Rp0.2', 'Pa', 'numeric', null, "
        "'ISO 6892', null, '2026-07-01 00:00:00')"
    )
    con.commit()
    con.close()
    return db


class Test이관:
    def test_원본의_빈_정의문이_사내_정의문을_안_지운다(
        self, db: Session, tmp_path: Path
    ) -> None:
        """배포마다 이관이 다시 돈다 — 빈 값으로 덮으면 정의문이 배포마다 지워진다."""
        snapshot = _snapshot(tmp_path)
        importer.run(db, snapshot)
        db.flush()
        one = db.scalar(select(CatalogDefinition).where(CatalogDefinition.key == YIELD))
        assert one is not None
        one.description = "사내가 적은 정의문."
        db.flush()

        importer.run(db, snapshot)
        db.flush()

        assert one.description == "사내가 적은 정의문."


class Test조회:
    def test_이름_풀기가_정의문과_규격을_싣는다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        defined: dict[str, CatalogDefinition],
    ) -> None:
        descriptions.refresh_property_descriptions(db, SEED)
        db.commit()

        got = client.get(
            "/api/catalog/properties/resolve", params={"q": "항복"}, headers=admin_headers
        )

        assert got.status_code == 200, got.text
        by_key = {one["key"]: one for one in got.json()["candidates"]}
        assert by_key[YIELD]["description"] == SEED[YIELD]
        assert by_key[YIELD]["test_standard"] == "ISO 6892"
        assert by_key[PASTE]["description"] == SEED[PASTE]

    def test_뜻으로_찾은_후보도_정의문을_싣는다(
        self,
        db: Session,
        defined: dict[str, CatalogDefinition],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """이름이 안 맞아 뜻으로 찾은 후보야말로 정의문으로 맞는지 봐야 한다.

        실측(2026-10-02): 이 길이 정의문을 빠뜨려, AI 가 「유전손실계수(Df)」 를 정의문이
        없는 물성이라고 답했다. 의미 검색은 시험 환경에서 꺼져 있을 수 있어 결과를 흉내 낸다.
        """
        descriptions.refresh_property_descriptions(db, SEED)
        db.commit()
        monkeypatch.setattr(
            semantic,
            "search",
            lambda _db, _text: [SimpleNamespace(kind="property", entity_id=PASTE, score=0.9)],
        )

        found = property_names.describe(
            property_names.resolve(db, "반죽이 흐르기 시작하는 힘")
        )

        meaning = [one for one in found["candidates"] if one["matched_by"] == "meaning"]
        assert meaning and meaning[0]["key"] == PASTE
        assert meaning[0]["description"] == SEED[PASTE]

    def test_물성_키_사전이_정의문을_싣는다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        defined: dict[str, CatalogDefinition],
    ) -> None:
        """다른 시스템이 받아 가는 허브 사전 — 키의 뜻을 자기 개념과 견줄 때 읽는다."""
        descriptions.refresh_property_descriptions(db, SEED)
        db.commit()

        got = client.get("/api/catalog/properties/dictionary", headers=admin_headers)

        assert got.status_code == 200, got.text
        rows = {one["key"]: one for one in got.json()["properties"]}
        assert rows[YIELD]["description"] == SEED[YIELD]

    def test_사내_항목은_같은_물성으로_이어진_키의_정의문을_낸다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        defined: dict[str, CatalogDefinition],
    ) -> None:
        """뜻은 허브 키 한 곳에 둔다 — 항목마다 따로 적으면 두 벌이 된다."""
        ensure_builtin_property_items(db)
        ensure_builtin_property_links(db)
        descriptions.refresh_property_descriptions(db, SEED)
        db.commit()

        got = client.get("/api/materials/property-items", headers=admin_headers)

        assert got.status_code == 200, got.text
        items = {one["item"]: one for one in got.json()}
        assert items["항복강도"]["property_key"] == YIELD
        assert items["항복강도"]["description"] == SEED[YIELD]
        # 이어진 키의 정의가 DB 에 없으면(이 시험엔 탄성계수 정의가 없다) 비어 있다.
        assert items["탄성계수"]["description"] is None

    def test_같은_물성이_아닌_연결의_정의문은_항목에_안_붙는다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        defined: dict[str, CatalogDefinition],
    ) -> None:
        """「관련」 · 「더 좁은」 키의 정의문은 이 항목의 뜻이 아니다 — 붙이면 다른 물성의
        뜻을 읽는다."""
        ensure_builtin_property_items(db)
        descriptions.refresh_property_descriptions(db, SEED)
        term = db.scalar(select(VocabularyTerm).where(VocabularyTerm.value == "연신율"))
        assert term is not None
        db.add(PropertyLink(property_key=PASTE, term_id=term.id, kind="related"))
        db.commit()

        got = client.get("/api/materials/property-items", headers=admin_headers)

        items = {one["item"]: one for one in got.json()}
        assert items["연신율"]["description"] is None
        assert items["연신율"]["property_key"] is None

    def test_매핑_화면이_정의문을_받는다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        defined: dict[str, CatalogDefinition],
    ) -> None:
        descriptions.refresh_property_descriptions(db, SEED)
        db.commit()

        got = client.get("/api/catalog/properties/mapping", headers=admin_headers)

        assert got.status_code == 200, got.text
        rows = {one["key"]: one for one in got.json()["rows"]}
        assert rows[PASTE]["description"] == SEED[PASTE]


class Test고치기:
    def test_자료_관리자가_고치면_남고_씨앗이_안_덮는다(
        self,
        client: TestClient,
        db: Session,
        workspace: Workspace,
        defined: dict[str, CatalogDefinition],
    ) -> None:
        descriptions.refresh_property_descriptions(db, SEED)
        db.commit()
        _user(db, workspace, "steward@example.com", is_data_manager=True)
        text = "사내 정의: 0.2 % 오프셋 내력. 상항복점과 구별한다."

        got = client.patch(
            f"/api/catalog/properties/{YIELD}",
            json={"description": text},
            headers=_headers(client, "steward@example.com"),
        )

        assert got.status_code == 200, got.text
        assert got.json()["description"] == text
        db.expire_all()
        assert (
            audit.CATALOG_PROPERTY_DESCRIBED
            in db.scalars(
                select(AuditEntry.action).where(AuditEntry.target_id == defined[YIELD].id)
            ).all()
        )
        _, kept = descriptions.refresh_property_descriptions(db, SEED)
        assert kept == [YIELD]

    def test_안_보낸_칸은_그대로_비운_칸은_비운다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        defined: dict[str, CatalogDefinition],
    ) -> None:
        descriptions.refresh_property_descriptions(db, SEED)
        db.commit()

        same = client.patch(f"/api/catalog/properties/{YIELD}", json={}, headers=admin_headers)
        assert same.json()["description"] == SEED[YIELD]

        cleared = client.patch(
            f"/api/catalog/properties/{YIELD}",
            json={"description": None},
            headers=admin_headers,
        )
        assert cleared.json()["description"] is None

    def test_자료_관리자가_아니면_못_고친다(
        self,
        client: TestClient,
        db: Session,
        workspace: Workspace,
        defined: dict[str, CatalogDefinition],
    ) -> None:
        _user(db, workspace, "member@example.com")

        refused = client.patch(
            f"/api/catalog/properties/{YIELD}",
            json={"description": "아무나 적은 뜻"},
            headers=_headers(client, "member@example.com"),
        )

        assert refused.status_code == 403, refused.text
        assert refused.json()["error"]["code"] == "MNX-CATALOG-0054"

    def test_없는_키는_404(self, client: TestClient, admin_headers: dict[str, str]) -> None:
        got = client.patch(
            "/api/catalog/properties/mechanical.nope",
            json={"description": "x"},
            headers=admin_headers,
        )
        assert got.status_code == 404, got.text
