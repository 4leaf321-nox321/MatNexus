"""어휘 — **눈에 같아 보이는 것을 하나로 모으는가.**

여기서 지키는 것 셋.

1. **보이지 않는 드리프트가 한 값으로 모인다.** 맥에서 붙여넣은 자모 분해,
   끝 공백, 전각 — 화면에서는 같아 보이는데 DB 는 다르게 본다.
2. **별칭이 새 값을 막는다.** 사후 병합보다 싸다.
3. **`closed` 축은 사용자가 못 늘린다.** 실제로 `'Family'` 라는 값이 입력된 적이
   있다.

계산이 아니라 **게이트**를 시험한다. 값이 만들어지는 경로가 여럿이라(단건 폼·
일괄 등록·이관) 게이트가 하나여야 그 판정이 안 갈린다.
"""

from __future__ import annotations

import unicodedata
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.vocabulary import services
from app.modules.vocabulary.models import Vocabulary, VocabularyAlias, VocabularyTerm
from app.modules.vocabulary.normalize import clean, compare_key


@pytest.fixture
def material(client: TestClient, admin_headers: dict[str, str]) -> dict[str, Any]:
    created: dict[str, Any] = client.post(
        "/api/materials",
        json={
            "family": "Metal",
            "category": "Steel",
            "grade": "VOCAB",
            "details": "T",
            "spec_thickness": 1.0,
        },
        headers=admin_headers,
    ).json()
    return created


class Test정규화:
    def test_눈에_같아_보이는_것은_같은_비교키다(self) -> None:
        same = [
            "포스코",
            unicodedata.normalize("NFD", "포스코"),  # 맥에서 붙여넣기
            "포스코 ",
            " 포스코",
            "포스코​",  # 웹 복사에 딸려 오는 제로폭
        ]
        keys = {compare_key(value) for value in same}
        assert len(keys) == 1, f"하나로 안 모였다: {keys}"

    def test_전각과_논브레이킹_스페이스도_모인다(self) -> None:
        assert compare_key("ＡＳＴＭ E8") == compare_key("ASTM E8")
        assert compare_key("ASTM E8") == compare_key("ASTM E8")

    def test_빈_값은_None_이다(self) -> None:
        # `''` 와 `NULL` 이 둘로 갈리면 "없음" 이 두 종류가 된다.
        assert clean("   ") is None
        assert clean("") is None


class Test게이트:
    def test_같은_값을_두_번_만들지_않는다(
        self, client: TestClient, admin_headers: dict[str, str], db: Session
    ) -> None:
        first = client.post(
            "/api/vocabularies/manufacturer/terms",
            json={"value": "테스트제철"},
            headers=admin_headers,
        )
        assert first.status_code == 201, first.text

        # **409 가 아니다.** 피커가 낙관적으로 보내므로 정규 행이 돌아와야 한다.
        again = client.post(
            "/api/vocabularies/manufacturer/terms",
            json={"value": " 테스트제철 "},
            headers=admin_headers,
        )
        assert again.status_code == 201, again.text
        assert again.json()["id"] == first.json()["id"]

    def test_별칭으로_찾아지면_새_값을_안_만든다(
        self, client: TestClient, admin_headers: dict[str, str], db: Session
    ) -> None:
        """**별칭은 청소가 아니라 예방이다.**"""
        created = client.post(
            "/api/vocabularies/manufacturer/terms",
            json={"value": "별칭제철"},
            headers=admin_headers,
        ).json()

        vocabulary = db.scalar(select(Vocabulary).where(Vocabulary.slug == "manufacturer"))
        assert vocabulary is not None
        db.add(
            VocabularyAlias(
                vocabulary_id=vocabulary.id,
                term_id=uuid.UUID(created["id"]),
                alias="별칭제철(주)",
                normalized=compare_key("별칭제철(주)"),
            )
        )
        db.commit()

        resolved = client.post(
            "/api/vocabularies/manufacturer/terms",
            json={"value": "별칭제철(주)"},
            headers=admin_headers,
        )
        assert resolved.json()["id"] == created["id"]
        assert resolved.json()["value"] == "별칭제철"  # 정규 값이 돌아온다

    def test_별칭으로도_검색된다(
        self, client: TestClient, admin_headers: dict[str, str], db: Session
    ) -> None:
        """화면이 결과를 다시 거르면 안 되는 이유가 이것이다 — 친 글자와 다른
        값이 정답이다."""
        created = client.post(
            "/api/vocabularies/manufacturer/terms",
            json={"value": "검색제철"},
            headers=admin_headers,
        ).json()
        vocabulary = db.scalar(select(Vocabulary).where(Vocabulary.slug == "manufacturer"))
        assert vocabulary is not None
        db.add(
            VocabularyAlias(
                vocabulary_id=vocabulary.id,
                term_id=uuid.UUID(created["id"]),
                alias="SEARCHSTEEL",
                normalized=compare_key("SEARCHSTEEL"),
            )
        )
        db.commit()

        found = client.get(
            "/api/vocabularies/manufacturer/terms",
            params={"q": "searchsteel"},
            headers=admin_headers,
        ).json()
        assert [item["value"] for item in found] == ["검색제철"]

    def test_closed_축은_사용자가_못_늘린다(
        self, client: TestClient, admin_headers: dict[str, str], db: Session
    ) -> None:
        db.add(Vocabulary(slug="closed_axis", label="닫힌 축", entry_policy="closed"))
        db.commit()

        denied = client.post(
            "/api/vocabularies/closed_axis/terms",
            json={"value": "몰래 넣기"},
            headers=admin_headers,
        )
        assert denied.status_code == 422, denied.text
        assert "관리자" in denied.json()["error"]["message"]


class Test시료와의_연결:
    def test_다른_표기로_넣어도_한_값을_가리킨다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        material: dict[str, Any],
    ) -> None:
        spellings = ["연결제철", unicodedata.normalize("NFD", "연결제철"), "연결제철 "]
        for value in spellings:
            client.post(
                f"/api/materials/{material['id']}/samples",
                json={"manufacturer": value},
                headers=admin_headers,
            )

        vocabulary = db.scalar(select(Vocabulary).where(Vocabulary.slug == "manufacturer"))
        assert vocabulary is not None
        terms = list(
            db.scalars(
                select(VocabularyTerm).where(
                    VocabularyTerm.vocabulary_id == vocabulary.id,
                    VocabularyTerm.value == "연결제철",
                )
            )
        )
        assert len(terms) == 1, "표기가 갈려 값이 여러 개 생겼다"
        # **참조가 생기는 자리에서 센다.** 안 세면 피커 정렬이 무의미해진다.
        assert terms[0].usage_count == len(spellings)

    def test_제조사가_같으면_통계가_조용하다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        material: dict[str, Any],
    ) -> None:
        """**어휘를 도입한 이유가 이 줄이다.**

        전에는 문자열로 비교해서 '포스코' 와 '포스코 ' 를 다른 제조사로 보고
        헛경고를 냈다. 경고를 만들어 놓고 그 입력을 자유 텍스트로 두는 것이
        앞뒤가 안 맞았다.
        """
        for value in ("조용제철", "조용제철 "):
            client.post(
                f"/api/materials/{material['id']}/samples",
                json={"manufacturer": value},
                headers=admin_headers,
            )

        samples = client.get(
            f"/api/materials/{material['id']}/samples", headers=admin_headers
        ).json()
        ids = {item["manufacturer"] for item in samples}
        assert ids == {"조용제철"}, f"저장된 표기가 갈렸다: {ids}"

    def test_어휘를_거쳐_저장된다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        material: dict[str, Any],
    ) -> None:
        created = client.post(
            f"/api/materials/{material['id']}/samples",
            json={"manufacturer": "  거쳐제철  "},
            headers=admin_headers,
        ).json()
        # 저장된 문자열이 정리돼 있다.
        assert created["manufacturer"] == "거쳐제철"

        vocabulary = services.get_vocabulary(db, "manufacturer")
        assert services.resolve(db, vocabulary, "거쳐제철") is not None
