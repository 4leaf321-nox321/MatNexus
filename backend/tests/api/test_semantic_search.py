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
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.modules.guide.models import GuideDocument, GuideSection
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
