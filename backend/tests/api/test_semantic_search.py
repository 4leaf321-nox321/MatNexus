"""의미 검색 — **낱말이 안 겹쳐도 뜻이 가까우면 찾는다.**

무는 것이 다섯이다.

    꺼져 있어도 검색은 돈다        선택 부품이 검색을 인질로 잡으면 안 된다
    넣은 것을 그대로 되찾는다      벡터 왕복이 정확한가(같은 글 → 1.0)
    **글자가 안 겹쳐도 걸린다**     이 기능의 전부다
    지운 것은 안 나온다            색인에 남은 조각이 유령 결과가 되면 안 된다
    조각은 겹치며 쪼개진다         경계에서 잘린 문장이 어디에도 없으면 안 된다

## mock 으로 무엇을 시험할 수 있나

`mock` 백엔드는 텍스트 해시로 벡터를 만든다 — **뜻은 없다.** 그래서 「비슷한 뜻을
찾나」 는 여기서 못 잰다. 대신 **같은 글은 같은 벡터**라, 「색인한 글로 그 글을
되찾을 수 있나」 는 정확히 잴 수 있다. 배관이 도는지가 여기서 갈린다.

CI 에 Ollama 를 두지 않는 값이 그보다 크다(RA 와 같은 판단).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from test_voc import member_headers

from app.config import get_settings
from app.modules.catalog.models import CatalogDefinition
from app.modules.guide.models import GuideDocument, GuideSection
from app.modules.workspaces.models import Workspace
from app.shared import semantic

#: 색인에 넣을 산문. **제목에는 없는 낱말**로 본문을 채운다 — 그래야 트라이그램이
#: 못 찾고 뜻으로만 걸리는 상황을 만들 수 있다.
BODY = (
    "박판 인장 시편은 표점거리를 먼저 정하고 나서 어깨 반지름을 맞춘다. "
    "두께가 얇을수록 물림부에서 미끄러지기 쉬우므로 사포를 덧대거나 물림압을 "
    "올린다. 그리고 신율은 표점 안에서만 재야 하며, 물림부 변형이 섞이면 값이 "
    "과대해진다. 이 절차는 얇은 강판과 알루미늄 판에 공통으로 적용한다."
)


@pytest.fixture
def semantic_off() -> Iterator[None]:
    """**꺼진 상태를 시험이 스스로 만든다.**

    전에는 개발 `.env` 가 `off` 인 것에 기대고 있었다 — 그 파일에 `EMBEDDING_BACKEND=ollama`
    를 넣자 「꺼져 있어도 검색은 돈다」 가 빨개졌다(2026-09-18). 시험은 사람 기계의 설정에
    기대면 안 된다.
    """
    settings = get_settings()
    before = settings.embedding_backend
    settings.embedding_backend = "off"
    try:
        yield
    finally:
        settings.embedding_backend = before


@pytest.fixture
def semantic_ready(db: Session) -> Iterator[None]:
    """pgvector 가 있고 mock 임베딩을 켠 상태.

    **없으면 건너뛴다.** 확장은 기계마다 설치 여부가 다르고(윈도우는 손으로 넣는다),
    그것 때문에 시험 전체가 빨개지면 안 된다.
    """
    settings = get_settings()
    if not semantic.ensure_schema(db):
        pytest.skip("pgvector 가 없습니다 — install_pgvector.ps1 로 넣습니다.")
    db.commit()

    before = settings.embedding_backend
    settings.embedding_backend = "mock"
    try:
        yield
    finally:
        settings.embedding_backend = before
        db.execute(text(f"DELETE FROM {semantic.TABLE}"))
        db.commit()


def _definition(db: Session) -> None:
    """물성 정의 하나 — 시험 DB 에는 사전이 없다(반입으로 들어오는 것이라서)."""
    if db.scalar(
        select(CatalogDefinition).where(CatalogDefinition.key == "mechanical.tensile_strength")
    ):
        return
    db.add(
        CatalogDefinition(
            mt_id=880_777,
            key="mechanical.tensile_strength",
            name="인장강도",
            domain="mechanical",
            si_unit="Pa",
            value_type="number",
            description="잡아당겨 끊어질 때까지 견디는 가장 큰 응력.",
        )
    )
    db.commit()


def _handbook(db: Session, *, title: str, body: str) -> GuideSection:
    document = GuideDocument(
        key=f"doc-{uuid.uuid4().hex[:8]}", title="시험 안내", kind="guide"
    )
    db.add(document)
    db.flush()
    section = GuideSection(document_id=document.id, key="s1", title=title, body_text=body)
    db.add(section)
    db.commit()
    return section


class TestPlumbing:
    def test_긴_글은_겹치며_쪼개진다(self) -> None:
        """겹치지 않으면 경계에서 잘린 문장이 어느 조각에도 온전히 안 남는다."""
        long = ("가나다라마바사 " * 200).strip()
        pieces = semantic.split(long)
        assert len(pieces) > 1
        assert all(len(one) <= semantic.CHUNK_CHARS + 10 for one in pieces)
        # 앞 조각의 끝이 뒤 조각의 앞에 다시 나온다.
        assert pieces[0][-20:] in pieces[1] or pieces[1][:20] in pieces[0]

    def test_짧은_글은_그대로_한_조각이다(self) -> None:
        assert semantic.split("짧다") == ["짧다"]
        assert semantic.split("   ") == []


@pytest.mark.usefixtures("semantic_off")
class TestOff:
    def test_꺼져_있어도_검색은_돈다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """**선택 부품이 검색을 인질로 잡으면 안 된다.**"""
        answer = client.get(
            "/api/search", params={"q": "SECC", "mode": "similar"}, headers=admin_headers
        )
        assert answer.status_code == 200, answer.text
        assert answer.json()["meaning"] is False

    def test_꺼져_있으면_의미_검색이_빈손이다(self, db: Session) -> None:
        assert semantic.search(db, "무엇이든") == []


@pytest.mark.usefixtures("semantic_ready")
class TestMeaning:
    def test_넣은_글로_그_글을_되찾는다(self, db: Session) -> None:
        """벡터 왕복이 정확한가. 같은 글이면 거리가 0이라 점수가 1.0 이어야 한다."""
        section = _handbook(db, title="시편 준비", body=BODY)
        made = semantic.reindex(db)
        assert made["chunks"] >= 1

        row = db.execute(
            text(f"SELECT title, body FROM {semantic.TABLE} WHERE entity_id = :id"),
            {"id": str(section.id)},
        ).first()
        assert row is not None
        found = semantic.search(db, f"{row[0]}\n{row[1]}")
        assert found[0].entity_id == str(section.id)
        assert found[0].score == pytest.approx(1.0, abs=1e-4)

    def test_글자가_안_겹쳐도_걸린다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        """**이 기능의 전부다.**

        제목은 「시편 준비」 인데 본문에는 「물림부」 가 있다. 본문으로 물으면
        트라이그램(제목만 본다)은 못 찾고 의미 검색만 찾는다.
        """
        section = _handbook(db, title="시편 준비", body=BODY)
        semantic.reindex(db)

        letters = client.get(
            "/api/search",
            params={"q": BODY[:120], "mode": "contains", "kind": ["guide_section"]},
            headers=admin_headers,
        )
        assert letters.json()["total"] == 0, "글자로 걸리면 이 시험이 아무것도 안 잰다"

        meaning = client.get(
            "/api/search",
            params={"q": BODY[:120], "mode": "similar", "kind": ["guide_section"]},
            headers=admin_headers,
        )
        assert meaning.status_code == 200, meaning.text
        body = meaning.json()
        assert body["meaning"] is True
        hits = body["groups"][0]["hits"] if body["groups"] else []
        assert [one["id"] for one in hits] == [str(section.id)]
        assert hits[0]["matched"] == "meaning"

    def test_지운_절은_결과에서_사라진다(self, db: Session) -> None:
        """색인에 남은 조각이 유령 결과가 되면, 눌러도 아무 데도 안 간다."""
        from datetime import UTC, datetime

        section = _handbook(db, title="지울 절", body=BODY)
        semantic.reindex(db)
        assert semantic.search(db, BODY)

        section.deleted_at = datetime.now(UTC)
        db.commit()
        made = semantic.reindex(db)
        assert made["removed"] >= 1
        assert all(one.entity_id != str(section.id) for one in semantic.search(db, BODY))


#: 재료 메모 — 이름(등급 코드)에는 없는 말. 「뜻으로만 걸리는」 상황을 만든다.
MATERIAL_NOTE = (
    "전기아연도금 냉연강판으로 가전 외판과 섀시에 쓴다. 도장성이 좋고 내식성이 "
    "필요한 부위에 고르며, 성형 해석에는 인장 곡선을 경화식으로 적합해 쓴다."
)


def _member_of(client: TestClient, admin_headers: dict[str, str], slug: str) -> dict[str, str]:
    email = f"sem-{uuid.uuid4().hex[:6]}@x.com"
    made = client.post(
        "/api/accounts",
        json={"email": email, "display_name": email, "workspace_slug": slug, "role": "member"},
        headers=admin_headers,
    )
    assert made.status_code in (200, 201), made.text
    token = client.post(
        "/api/auth/login",
        json={"email": email, "password": made.json()["temporary_password"]},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.usefixtures("semantic_ready")
class TestMaterials:
    """사내 재료도 **말로** 색인한다(2026-09-15). 「SECC」 로는 뜻이 없고, 분류·별칭·
    용도·메모를 엮은 문장이 뜻이다."""

    def test_메모로_재료를_되찾는다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        made = client.post(
            "/api/materials",
            json={
                "family": "Metal",
                "category": "Steel",
                "grade": "SEMCODE1",
                "alias": "가전용 아연도금",
                "note": MATERIAL_NOTE,
            },
            headers=admin_headers,
        )
        assert made.status_code == 201, made.text
        material_id = made.json()["id"]
        counted = semantic.reindex(db)
        assert counted["chunks"] >= 1

        row = db.execute(
            text(f"SELECT title, body FROM {semantic.TABLE} WHERE entity_id = :id"),
            {"id": material_id},
        ).first()
        assert row is not None
        # 분류·별칭·용도·메모가 한 문장에 든다 — 이름만 심으면 뜻이 없다.
        assert "Metal · Steel · SEMCODE1" in row[1]
        assert "별칭 가전용 아연도금" in row[1]
        assert MATERIAL_NOTE in row[1]

        # 글자로는 안 걸린다(이름·별칭에 메모의 낱말이 없다) — 뜻으로만 걸린다.
        letters = client.get(
            "/api/search",
            params={"q": MATERIAL_NOTE[:80], "mode": "contains", "kind": ["material"]},
            headers=admin_headers,
        ).json()
        assert letters["total"] == 0
        meaning = client.get(
            "/api/search",
            params={"q": f"{row[0]}\n{row[1]}"[:200], "mode": "similar", "kind": ["material"]},
            headers=admin_headers,
        ).json()
        hits = meaning["groups"][0]["hits"] if meaning["groups"] else []
        assert material_id in [one["id"] for one in hits], meaning
        assert next(one for one in hits if one["id"] == material_id)["matched"] in (
            "meaning",
            "both",
        )

    def test_잠긴_부서의_재료는_뜻으로도_안_샌다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        """조각 표에는 부서가 없다 — 검색이 권한을 다시 안 걸면 색인이 유출 통로다."""
        for slug, name in (("sem-a", "A 부서"), ("sem-b", "B 부서")):
            client.post(
                "/api/workspaces", json={"name": name, "slug": slug}, headers=admin_headers
            )
        made = client.post(
            "/api/materials",
            json={
                "family": "Metal",
                "category": "Steel",
                "grade": "SEMSECRET",
                "note": MATERIAL_NOTE,
                "workspace_slug": "sem-a",
            },
            headers=admin_headers,
        )
        assert made.status_code == 201, made.text
        material_id = made.json()["id"]
        locked = client.patch(
            "/api/workspaces/sem-a", json={"restricted": True}, headers=admin_headers
        )
        assert locked.status_code == 200, locked.text
        semantic.reindex(db)
        row = db.execute(
            text(f"SELECT title, body FROM {semantic.TABLE} WHERE entity_id = :id"),
            {"id": material_id},
        ).first()
        assert row is not None
        query = f"{row[0]}\n{row[1]}"[:200]

        outsider = _member_of(client, admin_headers, "sem-b")
        hidden = client.get(
            "/api/search",
            params={"q": query, "mode": "similar", "kind": ["material"]},
            headers=outsider,
        ).json()
        assert material_id not in [
            one["id"] for group in hidden["groups"] for one in group["hits"]
        ], hidden
        # 주인에게는 보인다.
        mine = client.get(
            "/api/search",
            params={"q": query, "mode": "similar", "kind": ["material"]},
            headers=admin_headers,
        ).json()
        assert material_id in [one["id"] for group in mine["groups"] for one in group["hits"]]


class Test관리_화면:
    """**꺼졌으면 왜, 그리고 무엇을 하면 되나** — 「조각 0개」 만으로는 셋을 못 가른다
    (자료가 없다 · 엔진이 없다 · 아직 안 돌렸다). 2026-09-18."""

    STATUS = "/api/search/semantic"
    REINDEX = "/api/search/semantic/reindex"

    @pytest.mark.usefixtures("semantic_off")
    def test_꺼져_있으면_이유와_할_일을_말한다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        body = client.get(self.STATUS, headers=admin_headers).json()
        assert body["ready"] is False and body["engine"] == "off"
        assert "EMBEDDING_BACKEND" in (body["blocked"] or "")
        # 꺼진 채로는 색인을 예약하지 않는다 — 빈 작업이 큐에 쌓이기만 한다.
        denied = client.post(self.REINDEX, headers=admin_headers)
        assert denied.status_code == 409
        assert denied.json()["error"]["code"] == "MNX-SEARCH-0003"

    @pytest.mark.usefixtures("semantic_ready")
    def test_켜져_있고_색인이_있으면_켜짐이다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        _handbook(db, title="시편 준비", body=BODY)
        semantic.reindex(db)
        body = client.get(self.STATUS, headers=admin_headers).json()
        assert body["ready"] is True
        assert body["chunks"] >= 1 and body["kinds"].get("guide_section", 0) >= 1
        assert body["models"] == ["mock"] and body["blocked"] is None
        assert body["table_dim"] == body["dim"]

    @pytest.mark.usefixtures("semantic_ready")
    def test_색인은_워커가_뒤에서_돌고_두_번_예약되지_않는다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        made = client.post(self.REINDEX, headers=admin_headers)
        assert made.status_code == 202, made.text
        assert made.json()["job_id"]
        # 도는 중에는 현황이 그렇게 말하고, 또 누르면 막힌다.
        assert client.get(self.STATUS, headers=admin_headers).json()["running"] is True
        again = client.post(self.REINDEX, headers=admin_headers)
        assert again.status_code == 409
        assert again.json()["error"]["code"] == "MNX-SEARCH-0004"

    def test_시스템_관리자만_본다(
        self, client: TestClient, db: Session, workspace: Workspace
    ) -> None:
        headers = member_headers(client, db, workspace)
        assert client.get(self.STATUS, headers=headers).status_code == 403
        assert client.post(self.REINDEX, headers=headers).status_code == 403


@pytest.mark.usefixtures("semantic_ready")
class Test차원이_바뀌면:
    def test_표를_다시_만들고_전부_새로_채운다(self, db: Session) -> None:
        """**모델을 바꾸면 차원이 바뀐다**(bge-m3 1024 · nomic 768). 옛 표에 새 벡터를 넣으면
        통째로 실패하는데, 그 실패는 워커 로그에만 남는다."""
        _handbook(db, title="시편 준비", body=BODY)
        semantic.reindex(db)
        assert semantic.table_dim(db) == get_settings().embedding_dim

        settings = get_settings()
        before = settings.embedding_dim
        settings.embedding_dim = before - 8
        try:
            assert semantic.ensure_schema(db) is True
            db.commit()
            assert semantic.table_dim(db) == before - 8
            # 옛 조각은 버렸다 — 원문은 그대로라 다시 채우면 된다.
            assert semantic.stats(db)["chunks"] == 0
            assert semantic.reindex(db)["chunks"] >= 1
        finally:
            settings.embedding_dim = before
            semantic.ensure_schema(db)
            db.commit()


@pytest.mark.usefixtures("semantic_ready")
class Test뜻과_글자가_서로_돕는다:
    """**역할을 갈라 두고, 서로 못 하는 것을 맡는다**(2026-09-18).

    이름·번호·별칭은 트라이그램이, 산문과 「달리 부르는 말」 은 임베딩이. mock 백엔드는 뜻이
    없으므로(해시 벡터) 여기서는 **길이 이어져 있는가**를 본다 — 뜻의 품질은 사람이 본다.
    """

    def test_물성_정의가_색인에_든다(self, db: Session) -> None:
        # 이것이 없으면 이름 해소가 뜻을 쓸 수 없다 — 사전에 없는 말은 어디에도 안 걸린다.
        _definition(db)
        assert any(one.kind == "property" for one in semantic.collect(db))
        semantic.reindex(db)
        assert semantic.stats(db)["kinds"].get("property", 0) > 0

    def test_글자로_찾은_것을_뜻이_밀어내지_않는다(self, db: Session) -> None:
        """별칭은 사람이 못 박은 것이고 뜻은 짐작이다 — 둘이 같은 무게면 안 된다."""
        from app.shared import property_names

        _definition(db)
        semantic.reindex(db)
        found = property_names.resolve(db, "인장강도", limit=5)
        assert found, "글자로 걸리는 것이 있어야 한다"
        assert found[0].matched_by != "meaning"

    def test_뜻_후보에는_바닥이_있다(self, db: Session) -> None:
        """**아무 말이나 넣어도 무언가는 가장 가깝다** — 바닥이 없으면 헛것이 후보로 선다."""
        from app.shared import property_names

        _definition(db)
        semantic.reindex(db)
        assert property_names.MEANING_FLOOR > 0
        junk = property_names.resolve(db, "아무말대잔치zzz", limit=3)
        assert all(one.matched_by != "meaning" for one in junk)

    def test_못_푼_이름에_이것_아닐까가_붙는다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        """못 푼 이름이야말로 뜻 검색이 제일 잘 하는 일인데, 전에는 이름만 쌓였다."""
        from app.shared import alias_candidates

        _definition(db)
        semantic.reindex(db)
        alias_candidates.record(db, kind="property", text="인장", source="resolve")
        db.commit()
        rows = client.get(
            "/api/catalog/properties/alias-candidates", headers=admin_headers
        ).json()
        row = next(one for one in rows if one["text"] == "인장")
        # 「인장」 은 글자로도 걸린다 — 후보가 서고, 뜻으로 걸린 것은 그렇다고 적힌다.
        assert row["suggestions"], "후보가 있어야 관리자가 고를 수 있다"
        assert {"key", "name", "si_unit", "value_count", "matched_by"} <= set(
            row["suggestions"][0]
        )
