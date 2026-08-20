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
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.tests.definitions import ensure_builtin_test_types
from app.modules.vocabulary import services
from app.modules.vocabulary.models import Vocabulary, VocabularyAlias, VocabularyTerm
from app.modules.vocabulary.normalize import clean, compare_key
from app.modules.vocabulary.schemas import BULK_MAX

TRA = Path(__file__).resolve().parents[1] / "fixtures" / "Example.tra"


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


class Test관리:
    """**어휘를 켜 두고 고칠 데가 없으면 절반만 한 것이다.**

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
        ).json()[0]

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
        ).json()[0]

        client.patch(
            f"/api/vocabularies/manufacturer/terms/{term['id']}",
            json={"status": "deprecated"},
            headers=admin_headers,
        )

        visible = client.get(
            "/api/vocabularies/manufacturer/terms",
            params={"q": "감출제철"},
            headers=admin_headers,
        ).json()
        assert visible == []

        # **되돌릴 길이 있어야 한다.** 없으면 감추기도 막다른 길이다.
        hidden = client.get(
            "/api/vocabularies/manufacturer/terms",
            params={"q": "감출제철", "include_hidden": "true"},
            headers=admin_headers,
        ).json()
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
        ).json()
        assert len(found) == 1, f"한 축에 두 값이 생겼다: {found}"
        # 한 값이 **두 컬럼**에서 쓰인다.
        assert found[0]["usage_count"] == 2

    def test_시편_규격도_어휘를_거친다(
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
        ).json()[0]
        assert before["usage_count"] == 1

        client.delete(f"/api/samples/{sample['id']}", headers=admin_headers)

        after = client.get(
            "/api/vocabularies/sales_type/terms",
            params={"q": "지울유형", "include_hidden": "true"},
            headers=admin_headers,
        ).json()[0]
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
        ).json()
        assert least[0]["value"] == "오타제쳘"


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
        ).json()[0]
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
        ).json()
        assert len(found) == 1, f"강종이 갈렸다: {found}"
        assert found[0]["usage_count"] == 2


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
        ).json()[0]
        assert grade["parent_value"] == "Steel"

        category = client.get(
            "/api/vocabularies/category/terms", params={"q": "Steel"}, headers=admin_headers
        ).json()[0]
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
            ).json()
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
            ).json()
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

    2단계까지는 어휘를 만들기만 했다. 잘못 갈린 것을 합치거나, 애초에 안 갈리게
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
        ).json()
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
        ).json()[0]

        client.patch(
            f"/api/vocabularies/grade/terms/{term['id']}",
            json={"parent_value": ""},
            headers=admin_headers,
        )
        cleared = client.get(
            "/api/vocabularies/grade/terms", params={"q": "ORPHAN"}, headers=admin_headers
        ).json()[0]
        assert cleared["parent_value"] is None

        client.patch(
            f"/api/vocabularies/grade/terms/{term['id']}",
            json={"parent_value": "Steel"},
            headers=admin_headers,
        )
        restored = client.get(
            "/api/vocabularies/grade/terms", params={"q": "ORPHAN"}, headers=admin_headers
        ).json()[0]
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
            ).json()
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
            ).json()
        }
        assert {"DP590", "DP780", "DP980"} <= under_steel

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
