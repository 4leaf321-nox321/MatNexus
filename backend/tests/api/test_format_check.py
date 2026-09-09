"""정의를 **글자로 온 표본**에 대고 검사한다 — AI 가 프로파일을 짓는 자리.

화면은 파일을 통째로 올리지만 AI 는 파일을 못 나른다(50MB 를 대화에 실을 수 없다).
구조를 판단하는 데는 앞 몇십 줄이면 충분하므로 그만큼만 글자로 받는다.

## 이 파서를 알고 나서 검사가 바뀌었다

처음에는 「매핑에 안 쓰인 열」 을 보려 했는데, **이 파서는 모든 열을 채널로 만든다.**
정의의 `columns` 는 「이 열을 무슨 채널이라 부를까」 를 정할 뿐이다. 그래서 진짜
위험은 열이 빠지는 것이 아니라 **이름을 안 정해 줘서 규약 밖 이름이 되는 것**이다 —
처리 단계는 `force`·`displacement` 로 채널을 찾으므로, 이름이 어긋나면 **읽히기는
하는데 그 뒤가 아무것도 안 된다.**

무는 것 다섯:

    정의 없이 부르면 구조만 준다      무엇이 있는지부터 본다
    표본이 길면 거절한다             파일 전체를 대화로 나르려는 시도를 막는다
    **이름 안 정한 열을 짚는다**      규약 밖 이름이 되는 자리
    **시험법 필수 채널을 대조한다**    「읽히는데 처리가 못 찾는」 것을 막는다
    **기대값과 대조한다**            「돌아는 갔다」 와 「기대한 것이 나왔다」 는 다르다
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.tests.definitions import ensure_builtin_test_types

CHECK = "/api/formats/check"

#: 인장 장비가 내는 모양을 줄인 것 — 헤더 한 줄, 단위 한 줄, 데이터 몇 줄.
#:
#: 온도 단위가 `°C` 인 것이 중요하다. **열에 채널 이름을 정해 주면 단위 검사가
#: 엄격해진다** — 안 정하면 넘어가는 `C` 가, 정하는 순간 「모르는 단위」 로 막힌다
#: (실측 2026-09-09). 그것도 이 검사가 잡아 주는 것 중 하나다.
SAMPLE = """Time;Displacement;Force;Temperature
s;mm;kN;°C
0.0;0.000;0.00;23.1
0.1;0.050;1.20;23.1
0.2;0.100;2.45;23.2
0.3;0.150;3.60;23.2
"""


def _definition(**over: Any) -> dict[str, Any]:
    """이 표본을 읽는 최소 정의.

    **`columns` 는 「이 열을 무슨 채널이라 부를까」 다.** 파서는 모든 열을 채널로
    만들고, 여기 없는 열은 원문 이름이 그대로 채널 키가 된다.
    """
    base: dict[str, Any] = {
        "columns": {
            "Time": {"channel": "time"},
            "Displacement": {"channel": "displacement"},
            "Force": {"channel": "force"},
            "Temperature": {"channel": "temperature"},
        }
    }
    base.update(over)
    return base


class TestStructure:
    def test_정의_없이_부르면_구조만_준다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        answer = client.post(
            CHECK, json={"sample_text": SAMPLE, "header_rows": 2}, headers=admin_headers
        )
        assert answer.status_code == 200, answer.text
        body = answer.json()
        assert body["ok"] is True
        header = body["structure"]["tables"][0]["header"]
        assert "Displacement" in header and "Force" in header

    def test_표본이_너무_길면_거절한다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """파일 전체를 대화로 나르려는 시도를 여기서 막는다."""
        answer = client.post(CHECK, json={"sample_text": "x" * 200_001}, headers=admin_headers)
        assert answer.status_code == 422
        assert answer.json()["error"]["code"] == "MNX-TESTS-0030"


class TestChecks:
    def test_이름을_안_정한_열을_짚는다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """정의에 없는 열은 **원문 이름이 그대로 채널 키**가 된다."""
        answer = client.post(
            CHECK,
            json={
                "sample_text": SAMPLE,
                "header_rows": 2,
                "definition": {"columns": {"Force": {"channel": "force"}}},
            },
            headers=admin_headers,
        )
        assert answer.status_code == 200, answer.text
        found = next(
            one for one in answer.json()["checks"] if one["name"] == "이름을 안 정한 열"
        )
        assert found["ok"] is False
        assert "Temperature" in found["detail"]

    def test_다_정하면_통과한다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        answer = client.post(
            CHECK,
            json={"sample_text": SAMPLE, "header_rows": 2, "definition": _definition()},
            headers=admin_headers,
        )
        found = next(
            one for one in answer.json()["checks"] if one["name"] == "이름을 안 정한 열"
        )
        assert found["ok"] is True

    def test_시험법_필수_채널을_대조한다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        """**이 검사가 가장 값지다.**

        없으면 「읽히기는 하는데 처리 단계가 채널을 못 찾는」 프로파일이 만들어진다.
        """
        ensure_builtin_test_types(db)
        db.commit()

        # 하중 열의 이름을 엉뚱하게 정했다 — 읽히기는 한다.
        answer = client.post(
            CHECK,
            json={
                "sample_text": SAMPLE,
                "header_rows": 2,
                "test_type": "tensile",
                "definition": {
                    "columns": {
                        "Time": {"channel": "time"},
                        "Displacement": {"channel": "displacement"},
                        "Force": {"channel": "무엇인가"},
                        "Temperature": {"channel": "temperature"},
                    }
                },
            },
            headers=admin_headers,
        )
        assert answer.status_code == 200, answer.text
        body = answer.json()
        found = next(one for one in body["checks"] if "필수 채널" in one["name"])
        assert found["ok"] is False, "하중 채널이 없는데 통과하면 안 된다"
        assert body["ok"] is False

    def test_기대값과_대조한다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """**「돌아는 갔다」 와 「기대한 것이 나왔다」 는 다르다.**

        사람이 장비 화면에서 읽은 값을 주면, AI 가 지은 정의가 같은 답을 내는지
        기계가 판정한다.
        """
        answer = client.post(
            CHECK,
            json={
                "sample_text": SAMPLE,
                "header_rows": 2,
                "definition": _definition(),
                "expect": {"curves": ["raw"], "summary": {"없는요약": 1.0}},
            },
            headers=admin_headers,
        )
        assert answer.status_code == 200, answer.text
        checks = {one["name"]: one for one in answer.json()["checks"]}
        assert checks["기대 곡선"]["ok"] is True
        # 없는 요약값을 기대하면 실패로 말한다 — 조용히 넘어가면 검사가 아니다.
        assert checks["기대값 없는요약"]["ok"] is False
