"""기준정보 — **눈에 같아 보이는 것을 하나로 모으는가.**

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
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.jobs import handlers, worker
from app.modules.tests.definitions import ensure_builtin_test_types
from app.modules.vocabulary import services
from app.modules.vocabulary.models import (
    Vocabulary,
    VocabularyAlias,
    VocabularyDriftCheck,
    VocabularyTerm,
)
from app.modules.vocabulary.normalize import clean, compare_key
from app.modules.vocabulary.schemas import BULK_MAX

TRA = Path(__file__).resolve().parents[1] / "fixtures" / "Example.tra"


def drain(db: Session, limit: int = 20) -> int:
    """큐가 빌 때까지 워커를 돌린다. 처리한 개수를 돌려준다."""
    handlers.load_all()
    processed = 0
    while processed < limit and worker.run_once(session=db):
        processed += 1
    return processed


def _run_in(
    client: TestClient,
    headers: dict[str, str],
    db: Session,
    sample_id: str,
    orientation: str,
) -> str:
    """시료에 시편·시험을 붙인다. 이름 연쇄 변경을 시험하려면 끝까지 필요하다."""
    from app.modules.tests import services as test_services

    specimen = client.post(
        f"/api/samples/{sample_id}/specimens",
        json={"orientation": orientation},
        headers=headers,
    ).json()
    created = client.post(
        "/api/test-runs",
        data={"specimen_id": specimen["id"], "test_type": "tensile", "conditions": "{}"},
        files={"file": ("Example.tra", TRA.read_bytes())},
        headers=headers,
    ).json()
    assert test_services.parse_run(db, uuid.UUID(created["id"])) == "parsed"
    return str(created["id"])


@pytest.fixture
def material(client: TestClient, admin_headers: dict[str, str], db: Session) -> dict[str, Any]:
    # 시험까지 붙이는 검사가 있다 — 시험 종류가 없으면 업로드가 404 다.
    ensure_builtin_test_types(db)
    db.commit()
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
        ).json()["items"]
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
        """**기준정보를 도입한 이유가 이 줄이다.**

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

    def test_기준정보를_거쳐_저장된다(
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


class Test관리:
    """**기준정보를 켜 두고 고칠 데가 없으면 절반만 한 것이다.**

    오타가 값이 되면 그것을 고르는 다음 사람이 생기고, 오염이 자기 강화된다.
    개발 DB 에 실제로 `'???'` 가 들어가 있었다.
    """

    def test_이름을_고치면_가리키던_것이_따라온다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        material: dict[str, Any],
    ) -> None:
        """**외래키로 간 이유가 이 줄이다.** 문자열이었으면 전 행을 훑어야 했다."""
        for _ in range(3):
            client.post(
                f"/api/materials/{material['id']}/samples",
                json={"manufacturer": "고칠제철"},
                headers=admin_headers,
            )
        term = client.get(
            "/api/vocabularies/manufacturer/terms",
            params={"q": "고칠제철"},
            headers=admin_headers,
        ).json()["items"][0]

        changed = client.patch(
            f"/api/vocabularies/manufacturer/terms/{term['id']}",
            json={"value": "고칠제철(주)"},
            headers=admin_headers,
        )
        assert changed.status_code == 200, changed.text

        samples = client.get(
            f"/api/materials/{material['id']}/samples", headers=admin_headers
        ).json()
        assert {item["manufacturer"] for item in samples} == {"고칠제철(주)"}

    def test_같은_이름으로_고치면_막고_병합을_가리킨다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """**말없이 합치지 않는다.** 두 값을 하나로 만드는 것은 병합이고, 어느
        쪽이 살아남는지·참조를 어떻게 옮길지를 정해야 하는 일이다."""
        first = client.post(
            "/api/vocabularies/manufacturer/terms",
            json={"value": "가제철"},
            headers=admin_headers,
        ).json()
        client.post(
            "/api/vocabularies/manufacturer/terms",
            json={"value": "나제철"},
            headers=admin_headers,
        )

        denied = client.patch(
            f"/api/vocabularies/manufacturer/terms/{first['id']}",
            json={"value": "나제철"},
            headers=admin_headers,
        )
        assert denied.status_code == 409, denied.text
        assert "병합" in denied.json()["error"]["message"]

    def test_감추면_피커에서만_사라진다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        material: dict[str, Any],
    ) -> None:
        """지우면 그 시료가 어느 제조사였는지 알 수 없게 된다 — 오타를 고치는
        것과 전혀 다른 일이다."""
        client.post(
            f"/api/materials/{material['id']}/samples",
            json={"manufacturer": "감출제철"},
            headers=admin_headers,
        )
        term = client.get(
            "/api/vocabularies/manufacturer/terms",
            params={"q": "감출제철"},
            headers=admin_headers,
        ).json()["items"][0]

        client.patch(
            f"/api/vocabularies/manufacturer/terms/{term['id']}",
            json={"status": "deprecated"},
            headers=admin_headers,
        )

        visible = client.get(
            "/api/vocabularies/manufacturer/terms",
            params={"q": "감출제철"},
            headers=admin_headers,
        ).json()["items"]
        assert visible == []

        # **되돌릴 길이 있어야 한다.** 없으면 감추기도 막다른 길이다.
        hidden = client.get(
            "/api/vocabularies/manufacturer/terms",
            params={"q": "감출제철", "include_hidden": "true"},
            headers=admin_headers,
        ).json()["items"]
        assert [item["value"] for item in hidden] == ["감출제철"]

        # 시료는 그대로다.
        samples = client.get(
            f"/api/materials/{material['id']}/samples", headers=admin_headers
        ).json()
        assert samples[0]["manufacturer"] == "감출제철"

    def test_어긋난_개수를_다시_셀_수_있다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        material: dict[str, Any],
    ) -> None:
        """**성능 때문에 둔 캐시라면 틀렸을 때 고치는 길이 있어야 한다.**

        실제로 개발 중에 생성 경로의 증가를 늦게 붙여 3 대 5 로 벌어졌다.
        """
        for _ in range(2):
            client.post(
                f"/api/materials/{material['id']}/samples",
                json={"manufacturer": "셀제철"},
                headers=admin_headers,
            )
        term = db.scalar(select(VocabularyTerm).where(VocabularyTerm.value == "셀제철"))
        assert term is not None
        term.usage_count = 99  # 어긋뜨린다
        db.commit()

        after = client.post(
            "/api/vocabularies/manufacturer/recount", headers=admin_headers
        ).json()
        counted = {item["value"]: item["usage_count"] for item in after}
        assert counted["셀제철"] == 2


class Test여러_축:
    """2단계 — 축이 늘어나도 코드가 안 늘어나는가.

    바인딩 표(`SAMPLE_BINDINGS` 등)를 두고 라우트가 그것을 훑는다. 축마다
    "resolve 하고 문자열 채우고 FK 채우고 usage 증감" 을 베껴 쓰면 그중 하나만
    고쳐지는 날이 온다 — 시료 폼이 갈렸던 것과 같은 실패다.
    """

    def test_유통사와_주_벤더가_한_축을_쓴다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        material: dict[str, Any],
    ) -> None:
        """같은 회사가 로트에 따라 둘 중 어느 쪽도 된다. 축을 나누면 같은 회사가
        두 목록에 따로 쌓이고, 합칠 방법도 없다."""
        client.post(
            f"/api/materials/{material['id']}/samples",
            json={"distributor": "한국유통 ", "primary_vendor": "한국유통"},
            headers=admin_headers,
        )
        found = client.get(
            "/api/vocabularies/vendor/terms",
            params={"q": "한국유통"},
            headers=admin_headers,
        ).json()["items"]
        assert len(found) == 1, f"한 축에 두 값이 생겼다: {found}"
        # 한 값이 **두 컬럼**에서 쓰인다.
        assert found[0]["usage_count"] == 2

    def test_시편_규격도_기준정보를_거친다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        material: dict[str, Any],
    ) -> None:
        sample = client.post(
            f"/api/materials/{material['id']}/samples", json={}, headers=admin_headers
        ).json()
        created = client.post(
            f"/api/samples/{sample['id']}/specimens",
            json={"orientation": "MD", "standard": "ASTM E8  subsize"},
            headers=admin_headers,
        ).json()
        # 가운데 두 칸이 정리된다.
        assert created["standard"] == "ASTM E8 subsize"

    def test_지우면_쓰는_곳이_줄어든다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        material: dict[str, Any],
    ) -> None:
        """안 빼면 피커에 "쓰이지 않는 값" 이 남고 '쓰는 곳' 이 거짓말을 한다."""
        sample = client.post(
            f"/api/materials/{material['id']}/samples",
            json={"sales_type": "지울유형"},
            headers=admin_headers,
        ).json()
        before = client.get(
            "/api/vocabularies/sales_type/terms",
            params={"q": "지울유형"},
            headers=admin_headers,
        ).json()["items"][0]
        assert before["usage_count"] == 1

        client.delete(f"/api/samples/{sample['id']}", headers=admin_headers)

        after = client.get(
            "/api/vocabularies/sales_type/terms",
            params={"q": "지울유형", "include_hidden": "true"},
            headers=admin_headers,
        ).json()["items"][0]
        assert after["usage_count"] == 0

    def test_적게_쓰이는_것부터_볼_수_있다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        material: dict[str, Any],
    ) -> None:
        """**`closed` 정책 대신 두는 장치다.**

        오타는 늘 `쓰는 곳 1` 로 생기는데 기본 정렬(많이 쓰는 순)에서는 목록
        끝에 묻힌다. 앞에서 막으면 사람이 대충 고르고 넘어가지만, 뒤에서 보이게
        하면 관리자가 실제 오염만 골라 낸다.
        """
        for _ in range(3):
            client.post(
                f"/api/materials/{material['id']}/samples",
                json={"manufacturer": "많이쓰는제철"},
                headers=admin_headers,
            )
        client.post(
            f"/api/materials/{material['id']}/samples",
            json={"manufacturer": "오타제쳘"},
            headers=admin_headers,
        )

        least = client.get(
            "/api/vocabularies/manufacturer/terms",
            params={"least_used": "true"},
            headers=admin_headers,
        ).json()["items"]
        assert least[0]["value"] == "오타제쳘"


class Test용도:
    """2단계 마지막 두 축 — **용도가 집계 축이 된다.**

    "도어 이너용 재료가 뭐가 있나" 는 실제로 물어보는 질문이다. 자유 문자열이면
    `도어`/`Door`/`도어 ` 가 갈려서 그 질문에 답이 셋 나온다.
    """

    def _material(
        self,
        client: TestClient,
        headers: dict[str, str],
        grade: str,
        product: str | None = None,
        part: str | None = None,
    ) -> dict[str, Any]:
        created: dict[str, Any] = client.post(
            "/api/materials",
            json={
                "family": "Metal",
                "category": "Steel",
                "grade": grade,
                "spec_thickness": 1.0,
                "applied_product": product,
                "applied_part": part,
            },
            headers=headers,
        ).json()
        return created

    def test_용도가_기준정보를_거친다(
        self, client: TestClient, admin_headers: dict[str, str], db: Session
    ) -> None:
        created = self._material(client, admin_headers, "USE01", product="도어  ", part="이너")
        # 가운데 두 칸이 정리된 값이 재료에 들어간다.
        assert created["applied_product"] == "도어"

        found = client.get(
            "/api/vocabularies/product/terms",
            params={"q": "도어"},
            headers=admin_headers,
        ).json()["items"]
        assert [item["value"] for item in found] == ["도어"]
        assert found[0]["usage_count"] == 1

    def test_표기가_갈려도_한_값이다(
        self, client: TestClient, admin_headers: dict[str, str], db: Session
    ) -> None:
        """이것이 이 축을 만든 이유 전부다."""
        for index, spelling in enumerate(
            ["후드", "후드 ", unicodedata.normalize("NFD", "후드")]
        ):
            self._material(client, admin_headers, f"USE1{index}", product=spelling)

        found = client.get(
            "/api/vocabularies/product/terms",
            params={"q": "후드"},
            headers=admin_headers,
        ).json()["items"]
        assert len(found) == 1, f"표기가 갈려 값이 여러 개 생겼다: {found}"
        assert found[0]["usage_count"] == 3

    def test_부위는_제품_아래에_안_매달린다(
        self, client: TestClient, admin_headers: dict[str, str], db: Session
    ) -> None:
        """**값 하나에 부모는 하나다.** `이너 패널` 은 도어에도 후드에도 쓰인다 —
        부모를 붙이면 먼저 들어온 제품이 이기고 나머지는 조용히 틀린 곳에 매달린다.
        """
        self._material(client, admin_headers, "USE20", product="도어", part="이너 패널")
        self._material(client, admin_headers, "USE21", product="후드", part="이너 패널")

        found = client.get(
            "/api/vocabularies/part/terms",
            params={"q": "이너 패널"},
            headers=admin_headers,
        ).json()["items"]
        assert len(found) == 1
        assert found[0]["parent_value"] is None, "부위가 제품에 매달렸다"
        assert found[0]["usage_count"] == 2

        axes = {
            item["slug"]: item
            for item in client.get("/api/vocabularies", headers=admin_headers).json()
        }
        assert axes["part"]["parent_slug"] is None

    def test_용도_이름을_고쳐도_재료_이름은_그대로다(
        self, client: TestClient, admin_headers: dict[str, str], db: Session
    ) -> None:
        """강종과 다른 점이다. 강종은 `record_name` 을 만들지만(ADR 0004) 용도는
        안 만든다 — 그래서 연쇄 변경 훅이 없어도 된다. 다만 **문자열 컬럼은
        따라와야 한다**(Expand 단계라 화면이 그쪽을 읽는다).
        """
        created = self._material(client, admin_headers, "USE30", product="구제품")
        term = client.get(
            "/api/vocabularies/product/terms",
            params={"q": "구제품"},
            headers=admin_headers,
        ).json()["items"][0]

        client.patch(
            f"/api/vocabularies/product/terms/{term['id']}",
            json={"value": "새제품"},
            headers=admin_headers,
        )

        after = client.get(f"/api/materials/{created['id']}", headers=admin_headers).json()
        assert after["applied_product"] == "새제품", "문자열이 안 따라왔다"
        assert after["record_name"] == created["record_name"], "이름이 바뀌면 안 된다"

    def test_재료를_지우면_쓰는_곳이_줄어든다(
        self, client: TestClient, admin_headers: dict[str, str], db: Session
    ) -> None:
        created = self._material(client, admin_headers, "USE40", product="지울제품")
        client.delete(f"/api/materials/{created['id']}", headers=admin_headers)

        found = client.get(
            "/api/vocabularies/product/terms",
            params={"q": "지울제품", "include_hidden": "true"},
            headers=admin_headers,
        ).json()["items"]
        assert found[0]["usage_count"] == 0


class Test강종:
    """2-2 — **강종은 재료 이름을 만든다.**

    다른 축은 값 이름을 고쳐도 표시가 바뀔 뿐이다. 강종은 재료 이름이 다시
    만들어지고 그 아래 시료·시편·시험 이름까지 내려간다(ADR 0004).
    """

    def test_강종_이름을_고치면_네_단계_이름이_전부_따라온다(
        self, client: TestClient, admin_headers: dict[str, str], db: Session
    ) -> None:
        ensure_builtin_test_types(db)
        db.commit()
        material = client.post(
            "/api/materials",
            json={
                "family": "Metal",
                "category": "Steel",
                "grade": "GRADEA",
                "details": "T",
                "spec_thickness": 1.0,
            },
            headers=admin_headers,
        ).json()
        sample = client.post(
            f"/api/materials/{material['id']}/samples", json={}, headers=admin_headers
        ).json()
        specimen = client.post(
            f"/api/samples/{sample['id']}/specimens",
            json={"orientation": "MD"},
            headers=admin_headers,
        ).json()
        run_id = _run_in(client, admin_headers, db, sample["id"], "TD")

        term = client.get(
            "/api/vocabularies/grade/terms", params={"q": "GRADEA"}, headers=admin_headers
        ).json()["items"][0]
        client.patch(
            f"/api/vocabularies/grade/terms/{term['id']}",
            json={"value": "GRADEB"},
            headers=admin_headers,
        )

        names = [
            client.get(f"/api/materials/{material['id']}", headers=admin_headers).json()[
                "record_name"
            ],
            client.get(
                f"/api/materials/{material['id']}/samples", headers=admin_headers
            ).json()[0]["record_name"],
            client.get(f"/api/specimens/{specimen['id']}", headers=admin_headers).json()[
                "record_name"
            ],
            client.get(f"/api/test-runs/{run_id}", headers=admin_headers).json()[
                "record_name"
            ],
        ]
        assert all(name.startswith("GRADEB") for name in names), names

    def test_같은_표기는_한_강종으로_모인다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """**이 축의 이득이 가장 크다.** 지금까지는 서로 다른 재료가 됐다."""
        for grade, details in (("SECC", "A"), ("secc ", "B")):
            client.post(
                "/api/materials",
                json={
                    "family": "Metal",
                    "category": "Steel",
                    "grade": grade,
                    "details": details,
                    "spec_thickness": 1.0,
                },
                headers=admin_headers,
            )
        found = client.get(
            "/api/vocabularies/grade/terms", params={"q": "secc"}, headers=admin_headers
        ).json()["items"]
        assert len(found) == 1, f"강종이 갈렸다: {found}"
        assert found[0]["usage_count"] == 2


class Test어긋남:
    """문자열과 기준정보가 벌어졌는가. **Contract 의 검증 도구다.**

    같은 사실을 두 벌로 들고 있는 동안(Expand) 둘은 벌어질 수 있다. 벌어져도
    아무도 모르는 것이 문제다 — 개발 DB 에서 2건이 벌어진 채로 있었고, 점검을
    만들고 나서야 알았다.
    """

    def test_이름을_고치면_값_자신도_바뀐다(
        self, client: TestClient, admin_headers: dict[str, str], db: Session
    ) -> None:
        """**실제로 안 바뀐 적이 있다.** 재료 이름 넷은 따라왔는데 정작 기준정보 값은
        옛 표기 그대로였다 — 이름 연쇄만 보던 시험이 못 잡았다."""
        client.post(
            "/api/materials",
            json={
                "family": "Metal",
                "category": "Steel",
                "grade": "DRIFTA",
                "details": "T",
                "spec_thickness": 1.0,
            },
            headers=admin_headers,
        )
        term = client.get(
            "/api/vocabularies/grade/terms", params={"q": "DRIFTA"}, headers=admin_headers
        ).json()["items"][0]

        renamed = client.patch(
            f"/api/vocabularies/grade/terms/{term['id']}",
            json={"value": "DRIFTB"},
            headers=admin_headers,
        )
        assert renamed.status_code == 200, renamed.text
        # 응답이 새 표기여야 한다.
        assert renamed.json()["value"] == "DRIFTB"
        # 저장된 것도 새 표기여야 한다.
        again = client.get(
            "/api/vocabularies/grade/terms", params={"q": "DRIFT"}, headers=admin_headers
        ).json()["items"]
        assert [item["value"] for item in again] == ["DRIFTB"], f"옛 표기가 남았다: {again}"

    def test_점검이_벌어진_칸을_찾는다(
        self, client: TestClient, admin_headers: dict[str, str], db: Session
    ) -> None:
        """점검 자신을 시험한다 — 안 그러면 "0건" 이 맞는 건지 못 세는 건지 모른다."""
        from app.modules.materials.models import Material

        client.post(
            "/api/materials",
            json={
                "family": "Metal",
                "category": "Steel",
                "grade": "DRIFTC",
                "details": "T",
                "spec_thickness": 1.0,
            },
            headers=admin_headers,
        )
        assert services.drift(db) == []

        # 문자열만 뒤틀어 놓는다 — 기준정보를 안 거치고 값을 바꾸는 경로가 하면
        # 이렇게 된다.
        material = db.scalar(select(Material).where(Material.grade == "DRIFTC"))
        assert material is not None
        material.grade = "DRIFTX"
        db.commit()

        found = services.drift(db)
        assert len(found) == 1, f"못 잡았다: {found}"
        assert found[0].table == "materials"
        assert found[0].field == "grade"
        assert found[0].count == 1
        assert "DRIFTX" in found[0].examples[0]

    def test_점검과_고치기가_API_로_돈다(
        self, client: TestClient, admin_headers: dict[str, str], db: Session
    ) -> None:
        """**점검만 있고 고칠 데가 없으면 막다른 길이다.**"""
        from app.modules.materials.models import Material

        client.post(
            "/api/materials",
            json={
                "family": "Metal",
                "category": "Steel",
                "grade": "DRIFTE",
                "details": "T",
                "spec_thickness": 1.0,
            },
            headers=admin_headers,
        )
        clean_report = client.get("/api/vocabularies/drift", headers=admin_headers)
        assert clean_report.status_code == 200, clean_report.text
        assert clean_report.json()["total"] == 0

        material = db.scalar(select(Material).where(Material.grade == "DRIFTE"))
        assert material is not None
        material.grade = "DRIFTY"
        db.commit()

        assert (
            client.post("/api/vocabularies/drift", headers=admin_headers).json()["total"] == 1
        )

        fixed = client.post("/api/vocabularies/repair", headers=admin_headers)
        assert fixed.status_code == 200, fixed.text
        # **고친 뒤** 상태가 온다 — 화면이 이것을 그대로 그린다.
        assert fixed.json()["total"] == 0
        # 다만 고치기 전 상태는 이력에 남아야 한다. 안 남기면 무엇이 있었는지
        # 사라지고, "언제부터 0" 이 벌어진 적 없는 것처럼 답한다.
        history = list(
            db.scalars(select(VocabularyDriftCheck).order_by(VocabularyDriftCheck.checked_at))
        )
        assert [row.total for row in history][-2:] == [1, 0], (
            f"고치기 전후가 둘 다 안 남았다: {[row.total for row in history]}"
        )

        assert (
            client.get("/api/vocabularies/drift", headers=admin_headers).json()["total"] == 0
        )
        db.expire_all()
        again = db.get(Material, material.id)
        assert again is not None
        assert again.grade == "DRIFTE", "기준정보 값으로 안 돌아왔다"
        # **이름도 따라와야 한다.** 강종은 재료 이름을 만든다(ADR 0004) — 고쳤는데
        # 이름이 옛 강종을 그대로 달고 있으면 고친 것이 아니다.
        assert again.record_name.startswith("DRIFTE"), (
            f"이름이 안 따라왔다: {again.record_name}"
        )

    def test_안_이어진_행은_기준정보로_올린다(
        self, client: TestClient, admin_headers: dict[str, str], db: Session
    ) -> None:
        """방향이 반대다. **문자열을 지우면 그 재료가 무엇이었는지 사라진다** —
        백필이 못 이은 행(눈에 안 보이는 문자가 든 값)이 실제로 이 상태였다."""
        from app.modules.materials.models import Material

        client.post(
            "/api/materials",
            json={
                "family": "Metal",
                "category": "Steel",
                "grade": "DRIFTF",
                "details": "T",
                "spec_thickness": 1.0,
            },
            headers=admin_headers,
        )
        material = db.scalar(select(Material).where(Material.grade == "DRIFTF"))
        assert material is not None
        material.grade_term_id = None  # 백필이 못 이은 상태
        db.commit()

        assert (
            client.post("/api/vocabularies/drift", headers=admin_headers).json()["total"] == 1
        )
        client.post("/api/vocabularies/repair", headers=admin_headers)

        db.expire_all()
        again = db.get(Material, material.id)
        assert again is not None
        assert again.grade == "DRIFTF", "문자열이 사라졌다"
        assert again.grade_term_id is not None, "기준정보로 안 올라갔다"
        assert (
            client.get("/api/vocabularies/drift", headers=admin_headers).json()["total"] == 0
        )

    def test_빈_값은_어긋남이_아니다(
        self, client: TestClient, admin_headers: dict[str, str], db: Session
    ) -> None:
        """`''` 와 `NULL` 이 둘로 갈리면 "없음" 이 두 종류가 된다 — 그건 표기
        문제이지 어긋남이 아니다. 여기서 걸리면 점검이 늘 시끄러워서 아무도 안 본다."""
        client.post(
            "/api/materials",
            json={
                "family": "Metal",
                "category": "Steel",
                "grade": "DRIFTD",
                "details": "T",
                "spec_thickness": 1.0,
                "applied_product": None,
            },
            headers=admin_headers,
        )
        assert services.drift(db) == []


class Test점검을_저절로_돌린다:
    """**지켜보는 게이트가 아니면 게이트가 아니다.**

    문자열 컬럼을 지우는 조건이 "한 릴리스 동안 0"(ADR 0010 Contract 4-2)인데,
    점검이 사람이 누를 때만 돌면 일주일 뒤에 그 질문에 답할 수가 없다.
    """

    def test_때가_되면_워커가_넣고_아니면_안_넣는다(self, db: Session) -> None:
        from app.jobs import kinds, schedule

        assert schedule.enqueue_due(db) == [kinds.VOCABULARY_CHECK_DRIFT]
        db.commit()

        # **바로 또 넣지 않는다.** 워커는 콘솔 앱이라 자주 껐다 켜진다 — 재기동
        # 마다 넣으면 하루에 열 번 켠 날 열 번 돈다.
        assert schedule.enqueue_due(db) == []

    def test_워커가_돌면_기록이_남는다(
        self, client: TestClient, admin_headers: dict[str, str], db: Session
    ) -> None:
        from app.jobs import kinds, schedule

        schedule.enqueue_due(db)
        db.commit()
        assert drain(db) >= 1

        row = services.latest_check(db)
        assert row is not None
        assert row.source == "worker"
        assert row.total == 0
        assert kinds.VOCABULARY_CHECK_DRIFT  # 이름이 살아 있는지

    def test_언제부터_0_인지를_답한다(
        self, client: TestClient, admin_headers: dict[str, str], db: Session
    ) -> None:
        """**"지금 0" 으로는 부족하다.** 한 번이라도 벌어졌으면 거기서 다시 센다 —
        고쳤더라도 "내내 0 이었다" 는 더 이상 참이 아니다."""
        from app.modules.materials.models import Material

        services.record_check(db, source="worker")
        db.commit()
        first = client.get("/api/vocabularies/drift", headers=admin_headers).json()
        assert first["clean_checks"] == 1
        started = first["clean_since"]
        assert started is not None

        # 한 번 벌어뜨린다.
        client.post(
            "/api/materials",
            json={
                "family": "Metal",
                "category": "Steel",
                "grade": "WATCH1",
                "details": "T",
                "spec_thickness": 1.0,
            },
            headers=admin_headers,
        )
        material = db.scalar(select(Material).where(Material.grade == "WATCH1"))
        assert material is not None
        material.grade = "WATCH2"
        db.commit()

        broken = client.post("/api/vocabularies/drift", headers=admin_headers).json()
        assert broken["total"] == 1
        assert broken["clean_checks"] == 0, "벌어졌는데 연속 0 이 남아 있다"

        # 고치면 거기서 **다시 센다** — 옛 날짜로 돌아가면 안 된다.
        fixed = client.post("/api/vocabularies/repair", headers=admin_headers).json()
        assert fixed["total"] == 0
        # 고치기가 남긴 두 줄 중 앞줄이 벌어진 상태라, 연속 0 은 뒷줄부터다.
        assert fixed["clean_checks"] == 1
        assert fixed["clean_since"] != started, "끊긴 구간을 이어 붙였다"

    def test_한_트랜잭션에_둘을_남겨도_순서가_산다(self, db: Session) -> None:
        """**포스트그레스의 `now()` 는 트랜잭션 시작 시각이다.**

        고치기는 한 번에 두 줄을 남긴다(고치기 전·후). `now()` 를 쓰면 그 둘이
        같은 시각을 받아 순서가 사라지고, "마지막 점검" 이 어느 쪽인지도, "언제부터
        0" 인지도 답이 틀린다. 실제로 그래서 시험이 깨졌다.
        """
        first = services.record_check(db, source="manual")
        second = services.record_check(db, source="manual")
        db.commit()

        assert first.checked_at < second.checked_at, (
            "같은 트랜잭션의 두 줄이 같은 시각을 받았다"
        )
        latest = services.latest_check(db)
        assert latest is not None
        assert latest.id == second.id

    def test_읽기는_새로_재지_않는다(
        self, client: TestClient, admin_headers: dict[str, str], db: Session
    ) -> None:
        """화면을 열 때마다 새로 재면 이력이 **사람이 창을 연 횟수**가 된다."""
        services.record_check(db, source="worker")
        db.commit()

        for _ in range(3):
            client.get("/api/vocabularies/drift", headers=admin_headers)
        assert db.scalar(select(func.count()).select_from(VocabularyDriftCheck)) == 1

        client.post("/api/vocabularies/drift", headers=admin_headers)
        assert db.scalar(select(func.count()).select_from(VocabularyDriftCheck)) == 2


class Test분류_계층:
    """2-3 — **분류는 사슬이다.** Metal → Steel → SECC.

    평평하게 두면 `Polymer + PP + SECC` 조합을 아무도 안 막고, 강종이 수만 개일
    때 피커가 전체를 보여 준다.
    """

    def test_재료를_만들면_사슬이_따라_붙는다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """**계층이 쓰면서 저절로 만들어진다.** 관리자가 미리 이어 놓을 필요가
        없다 — 수만 개를 손으로 잇는 일은 아무도 안 한다."""
        client.post(
            "/api/materials",
            json={
                "family": "Metal",
                "category": "Steel",
                "grade": "CHAINA",
                "details": "T",
                "spec_thickness": 1.0,
            },
            headers=admin_headers,
        )
        grade = client.get(
            "/api/vocabularies/grade/terms", params={"q": "CHAINA"}, headers=admin_headers
        ).json()["items"][0]
        assert grade["parent_value"] == "Steel"

        category = client.get(
            "/api/vocabularies/category/terms", params={"q": "Steel"}, headers=admin_headers
        ).json()["items"][0]
        assert category["parent_value"] == "Metal"

    def test_부모로_좁힌다(self, client: TestClient, admin_headers: dict[str, str]) -> None:
        for family, category, grade in (
            ("Metal", "Steel", "STEELG"),
            ("Polymer", "PP", "POLYG"),
        ):
            client.post(
                "/api/materials",
                json={
                    "family": family,
                    "category": category,
                    "grade": grade,
                    "details": "T",
                    "spec_thickness": 1.0,
                },
                headers=admin_headers,
            )

        under_steel = {
            item["value"]
            for item in client.get(
                "/api/vocabularies/grade/terms",
                params={"parent_value": "Steel", "limit": 100},
                headers=admin_headers,
            ).json()["items"]
        }
        assert "STEELG" in under_steel
        assert "POLYG" not in under_steel

    def test_부모가_없는_값은_함께_보인다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """**계층은 쓰면서 채워진다.** 초기에는 대부분 부모가 비어 있고, 그것을
        감추면 좁히기를 켠 순간 아무것도 안 보인다."""
        client.post(
            "/api/materials",
            json={
                "family": "Metal",
                "category": "Steel",
                "grade": "HASPARENT",
                "details": "T",
                "spec_thickness": 1.0,
            },
            headers=admin_headers,
        )
        # 부모 없이 만든 값
        client.post(
            "/api/vocabularies/grade/terms",
            json={"value": "NOPARENT"},
            headers=admin_headers,
        )

        under_steel = {
            item["value"]
            for item in client.get(
                "/api/vocabularies/grade/terms",
                params={"parent_value": "Steel", "limit": 100},
                headers=admin_headers,
            ).json()["items"]
        }
        assert {"HASPARENT", "NOPARENT"} <= under_steel

    def test_새_값이_고른_부모_아래로_들어간다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        client.post(
            "/api/materials",
            json={
                "family": "Metal",
                "category": "Steel",
                "grade": "SEEDG",
                "details": "T",
                "spec_thickness": 1.0,
            },
            headers=admin_headers,
        )
        added = client.post(
            "/api/vocabularies/grade/terms",
            json={"value": "DP980", "parent_value": "Steel"},
            headers=admin_headers,
        ).json()
        assert added["parent_value"] == "Steel"


class Test별칭과_병합:
    """3단계 — **표기가 갈렸을 때 되돌릴 길.**

    2단계까지는 기준정보를 만들기만 했다. 잘못 갈린 것을 합치거나, 애초에 안 갈리게
    막을 방법이 없었다.
    """

    def _term(self, client: TestClient, headers: dict[str, str], value: str) -> dict[str, Any]:
        created: dict[str, Any] = client.post(
            "/api/vocabularies/manufacturer/terms", json={"value": value}, headers=headers
        ).json()
        return created

    def test_별칭을_등록하면_새_값이_안_생긴다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """**예방이다.** 사후에 합치는 것보다 싸다."""
        term = self._term(client, admin_headers, "예방제철")
        client.post(
            f"/api/vocabularies/manufacturer/terms/{term['id']}/aliases",
            json={"alias": "YEBANG STEEL"},
            headers=admin_headers,
        )

        resolved = client.post(
            "/api/vocabularies/manufacturer/terms",
            json={"value": "yebang steel"},
            headers=admin_headers,
        ).json()
        assert resolved["id"] == term["id"]
        assert resolved["value"] == "예방제철"

    def test_이미_쓰이는_표기는_별칭으로_못_쓴다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        first = self._term(client, admin_headers, "가제철A")
        self._term(client, admin_headers, "나제철A")
        denied = client.post(
            f"/api/vocabularies/manufacturer/terms/{first['id']}/aliases",
            json={"alias": "나제철A"},
            headers=admin_headers,
        )
        assert denied.status_code == 409, denied.text

    def test_합치면_참조가_옮겨지고_옛_표기가_별칭으로_남는다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        material: dict[str, Any],
    ) -> None:
        """**병합이 일회성 청소가 아니라 규칙이 되는 지점이다.**"""
        for value in ("합칠제철", "합칠제철(주)"):
            client.post(
                f"/api/materials/{material['id']}/samples",
                json={"manufacturer": value},
                headers=admin_headers,
            )
        terms = client.get(
            "/api/vocabularies/manufacturer/terms",
            params={"q": "합칠제철"},
            headers=admin_headers,
        ).json()["items"]
        source = next(item for item in terms if "(" in item["value"])
        target = next(item for item in terms if "(" not in item["value"])

        merged = client.post(
            f"/api/vocabularies/manufacturer/terms/{source['id']}/merge",
            json={"into_id": target["id"]},
            headers=admin_headers,
        ).json()
        assert merged["usage_count"] == 2

        # 시료의 문자열도 옮겨진다(Expand 단계라 양쪽을 든다).
        samples = client.get(
            f"/api/materials/{material['id']}/samples", headers=admin_headers
        ).json()
        assert {item["manufacturer"] for item in samples} == {"합칠제철"}

        # **없어진 표기가 별칭으로 남는다** — 다음에 또 쳐도 새 값이 안 생긴다.
        again = client.post(
            "/api/vocabularies/manufacturer/terms",
            json={"value": "합칠제철(주)"},
            headers=admin_headers,
        ).json()
        assert again["id"] == target["id"]

    def test_다른_축끼리는_못_합친다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """축을 넘는 병합은 값을 합치는 것이 아니라 **뜻을 바꾸는 것**이다."""
        maker = self._term(client, admin_headers, "축넘기제철")
        vendor = client.post(
            "/api/vocabularies/vendor/terms",
            json={"value": "축넘기상사"},
            headers=admin_headers,
        ).json()
        denied = client.post(
            f"/api/vocabularies/manufacturer/terms/{maker['id']}/merge",
            json={"into_id": vendor["id"]},
            headers=admin_headers,
        )
        assert denied.status_code in (404, 422), denied.text

    def test_후보는_구두점까지_지운_키로_묶는다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        for value in ("ASTM E8", "astm-e8"):
            client.post(
                "/api/vocabularies/specimen_standard/terms",
                json={"value": value},
                headers=admin_headers,
            )
        groups = client.get(
            "/api/vocabularies/specimen_standard/merge-candidates", headers=admin_headers
        ).json()
        values = [{item["value"] for item in group} for group in groups]
        assert {"ASTM E8", "astm-e8"} in values

    def test_기각한_쌍은_다시_안_뜬다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """안 기억하면 같은 것을 매번 다시 묻게 되고, 그러면 목록을 아무도 안 본다."""
        first = self._term(client, admin_headers, "기각제철")
        second = self._term(client, admin_headers, "기각-제철")
        assert any(
            {item["value"] for item in group} == {"기각제철", "기각-제철"}
            for group in client.get(
                "/api/vocabularies/manufacturer/merge-candidates", headers=admin_headers
            ).json()
        )

        client.post(
            "/api/vocabularies/manufacturer/dismissals",
            json={"first_id": first["id"], "second_id": second["id"]},
            headers=admin_headers,
        )
        assert not any(
            {item["value"] for item in group} == {"기각제철", "기각-제철"}
            for group in client.get(
                "/api/vocabularies/manufacturer/merge-candidates", headers=admin_headers
            ).json()
        )

    def test_부모를_화면에서_정할_수_있다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """백필이 못 이은 값(부모가 갈렸던 것)을 사람이 정하는 자리다. 그 길이
        없으면 로그만 남기고 아무도 못 고친다."""
        client.post(
            "/api/materials",
            json={
                "family": "Metal",
                "category": "Steel",
                "grade": "ORPHAN",
                "details": "T",
                "spec_thickness": 1.0,
            },
            headers=admin_headers,
        )
        term = client.get(
            "/api/vocabularies/grade/terms", params={"q": "ORPHAN"}, headers=admin_headers
        ).json()["items"][0]

        client.patch(
            f"/api/vocabularies/grade/terms/{term['id']}",
            json={"parent_value": ""},
            headers=admin_headers,
        )
        cleared = client.get(
            "/api/vocabularies/grade/terms", params={"q": "ORPHAN"}, headers=admin_headers
        ).json()["items"][0]
        assert cleared["parent_value"] is None

        client.patch(
            f"/api/vocabularies/grade/terms/{term['id']}",
            json={"parent_value": "Steel"},
            headers=admin_headers,
        )
        restored = client.get(
            "/api/vocabularies/grade/terms", params={"q": "ORPHAN"}, headers=admin_headers
        ).json()["items"][0]
        assert restored["parent_value"] == "Steel"


class Test값_미리_추가:
    """**관리자가 목록을 미리 갖춰 놓는 자리.**

    지금까지 값은 누가 폼에서 써야만 생겼다. 그러면 제조사 목록을 먼저 정리해
    두고 싶어도 방법이 없고, 첫 사람이 무엇을 칠지에 목록이 끌려간다.
    """

    def test_부모와_함께_미리_등록한다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        client.post(
            "/api/materials",
            json={
                "family": "Metal",
                "category": "Steel",
                "grade": "SEEDONE",
                "details": "T",
                "spec_thickness": 1.0,
            },
            headers=admin_headers,
        )
        added = client.post(
            "/api/vocabularies/grade/terms",
            json={"value": "DP1180", "parent_value": "Steel"},
            headers=admin_headers,
        ).json()
        assert added["parent_value"] == "Steel"
        # 아직 아무도 안 쓴다 — 그래도 피커에는 뜬다.
        assert added["usage_count"] == 0

        listed = {
            item["value"]
            for item in client.get(
                "/api/vocabularies/grade/terms",
                params={"parent_value": "Steel", "limit": 100},
                headers=admin_headers,
            ).json()["items"]
        }
        assert "DP1180" in listed

    def test_별칭으로_치면_정규_값이_돌아온다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """**화면이 이 차이를 말해야 한다.** 안 말하면 사람은 자기가 친 값이
        추가된 줄 알고, 목록에 없으니 다시 친다."""
        term = client.post(
            "/api/vocabularies/manufacturer/terms",
            json={"value": "미리제철"},
            headers=admin_headers,
        ).json()
        client.post(
            f"/api/vocabularies/manufacturer/terms/{term['id']}/aliases",
            json={"alias": "MIRI STEEL"},
            headers=admin_headers,
        )

        got = client.post(
            "/api/vocabularies/manufacturer/terms",
            json={"value": "miri steel"},
            headers=admin_headers,
        ).json()
        assert got["value"] == "미리제철"
        assert got["id"] == term["id"]

    def test_부모가_없는_축은_부모를_무시한다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        added = client.post(
            "/api/vocabularies/manufacturer/terms",
            json={"value": "무부모제철", "parent_value": "Steel"},
            headers=admin_headers,
        ).json()
        assert added["parent_value"] is None


class Test여러_값_한번에:
    """붙여 넣기는 지저분하다 — **빈 줄·중복·별칭이 섞여 온다.**

    개수만 돌려주면 "50개 중 12개가 새로 생겼습니다" 로 끝나는데, 사람이 알고
    싶은 것은 어느 것이 안 생겼고 왜인지다.
    """

    def test_빈_줄과_중복과_별칭이_섞인_목록을_정직하게_가른다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        seed = client.post(
            "/api/vocabularies/manufacturer/terms",
            json={"value": "있던제철"},
            headers=admin_headers,
        ).json()
        client.post(
            f"/api/vocabularies/manufacturer/terms/{seed['id']}/aliases",
            json={"alias": "OLD STEEL"},
            headers=admin_headers,
        )

        result = client.post(
            "/api/vocabularies/manufacturer/terms/bulk",
            json={
                "values": [
                    "새제철",  # 새로
                    "",  # 건너뜀
                    " 새제철 ",  # 방금 만든 것과 같다
                    "있던제철",  # 이미 있음
                    "old steel",  # 별칭 → 정규 값
                    "   ",  # 건너뜀
                ]
            },
            headers=admin_headers,
        ).json()

        assert (result["created"], result["existing"], result["skipped"]) == (1, 3, 2)
        by_input = {item["input"]: item for item in result["items"]}
        assert by_input["새제철"]["status"] == "created"
        # **같은 요청 안의 중복도 정직하게** — 방금 만든 것을 가리킨다.
        assert by_input[" 새제철 "]["status"] == "existing"
        assert by_input[" 새제철 "]["value"] == "새제철"
        # 별칭으로 붙은 것은 **친 것과 다른 값**이 온다 — 화면이 이걸 말해야 한다.
        assert by_input["old steel"]["value"] == "있던제철"

    def test_부모가_한_번에_붙는다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        client.post(
            "/api/materials",
            json={
                "family": "Metal",
                "category": "Steel",
                "grade": "BULKSEED",
                "details": "T",
                "spec_thickness": 1.0,
            },
            headers=admin_headers,
        )
        client.post(
            "/api/vocabularies/grade/terms/bulk",
            json={"values": ["DP590", "DP780", "DP980"], "parent_value": "Steel"},
            headers=admin_headers,
        )
        under_steel = {
            item["value"]
            for item in client.get(
                "/api/vocabularies/grade/terms",
                params={"parent_value": "Steel", "limit": 100},
                headers=admin_headers,
            ).json()["items"]
        }
        assert {"DP590", "DP780", "DP980"} <= under_steel

    def test_줄마다_상위를_달리_적을_수_있다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """**창에서 고른 상위 하나를 전 줄에 붙이면 분류가 섞인 목록을 못 넣는다.**

        엑셀에서 두 열을 복사하면 탭으로 붙는다 — 그 형태를 그대로 받는다.
        """
        for family, category in (("Metal", "Steel"), ("Polymer", "PP")):
            client.post(
                "/api/materials",
                json={
                    "family": family,
                    "category": category,
                    "grade": f"SEED{category}",
                    "details": "T",
                    "spec_thickness": 1.0,
                },
                headers=admin_headers,
            )

        result = client.post(
            "/api/vocabularies/grade/terms/bulk",
            json={
                "values": [
                    "Steel\tTABBED",  # 탭 — 엑셀 두 열
                    "PP > ANGLED",  # 꺾쇠 — 손으로 칠 때
                    "FALLBACK",  # 안 적음 → 요청의 기본값
                    "없는분류 > ORPHAN",  # 상위를 못 찾음
                ],
                "parent_value": "Steel",
            },
            headers=admin_headers,
        ).json()

        assert result["rejected"] == 1
        by_input = {item["input"]: item for item in result["items"]}
        assert by_input["Steel\tTABBED"]["parent_value"] == "Steel"
        assert by_input["PP > ANGLED"]["parent_value"] == "PP"
        assert by_input["FALLBACK"]["parent_value"] == "Steel"

        # **말없이 버리지 않는다.** 그냥 만들면 그 값이 어디 속하는지 모른다.
        orphan = by_input["없는분류 > ORPHAN"]
        assert orphan["status"] == "rejected"
        assert "없는분류" in (orphan["reason"] or "")

        under_pp = {
            item["value"]
            for item in client.get(
                "/api/vocabularies/grade/terms",
                params={"parent_value": "PP", "limit": 100},
                headers=admin_headers,
            ).json()["items"]
        }
        assert "ANGLED" in under_pp
        assert "TABBED" not in under_pp

    def test_부모가_없는_축은_꺾쇠를_안_가른다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """제조사 값에 `>` 가 들어 있을 수 있다 — 부모 없는 축에서 갈라 버리면
        멀쩡한 값이 반토막 난다."""
        result = client.post(
            "/api/vocabularies/manufacturer/terms/bulk",
            json={"values": ["A > B 상사"]},
            headers=admin_headers,
        ).json()
        assert result["items"][0]["value"] == "A > B 상사"

    def test_상한을_넘기면_서버가_거절한다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """**화면이 미리 자르면 몇 줄이 빠졌는지 아무도 모른다.** 그대로 보내고
        서버가 말하게 둔다."""
        denied = client.post(
            "/api/vocabularies/manufacturer/terms/bulk",
            json={"values": [f"값{index}" for index in range(BULK_MAX + 1)]},
            headers=admin_headers,
        )
        assert denied.status_code == 422, denied.text


class Test여러_값_지우기:
    """**지우기는 되돌릴 수 없다.** 그래서 무엇이 막는지 말한다.

    쓰이고 있는 값을 지우면서 참조를 끊으면 그 시료가 어느 제조사였는지 영영
    알 수 없게 된다 — 그건 값을 정리하는 것과 전혀 다른 일이다.
    """

    def test_안_쓰는_것만_지우고_나머지는_이유를_말한다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        material: dict[str, Any],
    ) -> None:
        client.post(
            f"/api/materials/{material['id']}/samples",
            json={"manufacturer": "쓰는제철"},
            headers=admin_headers,
        )
        used = client.get(
            "/api/vocabularies/manufacturer/terms",
            params={"q": "쓰는제철"},
            headers=admin_headers,
        ).json()["items"][0]
        free = client.post(
            "/api/vocabularies/manufacturer/terms",
            json={"value": "안쓰는제철"},
            headers=admin_headers,
        ).json()

        result = client.post(
            "/api/vocabularies/manufacturer/terms/delete",
            json={"ids": [free["id"], used["id"]]},
            headers=admin_headers,
        ).json()

        # **요청 전체를 실패시키지 않는다** — 하나가 막힌다고 나머지를 못 지울
        # 이유가 없다.
        assert (result["deleted"], result["blocked"]) == (1, 1)
        by_value = {item["value"]: item for item in result["items"]}
        assert by_value["안쓰는제철"]["deleted"] is True
        assert by_value["쓰는제철"]["deleted"] is False
        assert "1곳에서 쓰고 있습니다" in (by_value["쓰는제철"]["reason"] or "")

    def test_하위가_있으면_안_지운다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """지우면 하위 값들이 고아가 된다."""
        client.post(
            "/api/materials",
            json={
                "family": "Metal",
                "category": "Steel",
                "grade": "CHILDA",
                "details": "T",
                "spec_thickness": 1.0,
            },
            headers=admin_headers,
        )
        parent = client.get(
            "/api/vocabularies/category/terms",
            params={"q": "Steel"},
            headers=admin_headers,
        ).json()["items"][0]

        result = client.post(
            "/api/vocabularies/category/terms/delete",
            json={"ids": [parent["id"]]},
            headers=admin_headers,
        ).json()
        assert result["blocked"] == 1
        assert result["items"][0]["reason"]

    def test_캐시가_어긋나도_실제_참조를_센다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        material: dict[str, Any],
    ) -> None:
        """`usage_count` 는 캐시고 어긋날 수 있다(실제로 3 대 5 로 벌어진 적이
        있다). 캐시가 0 이라고 지웠는데 참조가 남아 있으면 외래키가 막고 요청이
        500 으로 죽는다."""
        client.post(
            f"/api/materials/{material['id']}/samples",
            json={"manufacturer": "캐시틀린제철"},
            headers=admin_headers,
        )
        term = db.scalar(select(VocabularyTerm).where(VocabularyTerm.value == "캐시틀린제철"))
        assert term is not None
        term.usage_count = 0  # 어긋뜨린다
        db.commit()

        result = client.post(
            "/api/vocabularies/manufacturer/terms/delete",
            json={"ids": [str(term.id)]},
            headers=admin_headers,
        ).json()
        assert result["blocked"] == 1

    def test_목록이_쪽으로_온다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        for index in range(5):
            client.post(
                "/api/vocabularies/manufacturer/terms",
                json={"value": f"쪽제철{index}"},
                headers=admin_headers,
            )
        first = client.get(
            "/api/vocabularies/manufacturer/terms",
            params={"limit": 2},
            headers=admin_headers,
        ).json()
        assert first["total"] >= 5
        assert len(first["items"]) == 2

        second = client.get(
            "/api/vocabularies/manufacturer/terms",
            params={"limit": 2, "offset": 2},
            headers=admin_headers,
        ).json()
        assert first["items"][0]["id"] != second["items"][0]["id"]
