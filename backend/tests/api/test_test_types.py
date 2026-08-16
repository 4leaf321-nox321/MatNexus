"""시험 종류 정의 편집 — "정의는 데이터" 가 실제로 성립하는가.

**여기가 위험한 자리다.** 정의를 열어 주면 사람이 이미 저장된 데이터의 해석을
바꿀 수 있게 된다.

  key       Parquet 컬럼 이름이자 `Curve.channels` 의 값이다. 바꾸면 저장된
            곡선을 못 읽고, 오류가 아니라 조용히 "채널 없음" 이 된다.
  si_unit   더 나쁘다. 저장된 숫자는 그대로인데 뜻이 바뀐다 — force 를 N → kN 으로
            바꾸면 3466.4 N 이 3466.4 kN 으로 읽힌다. **숫자가 그대로라 티가 안 난다.**

그래서 데이터가 있으면 그 둘을 잠그고, 라벨·정렬·필수여부만 연다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.tests.definitions import ensure_builtin_test_types

TRA = Path(__file__).resolve().parents[1] / "fixtures" / "Example.tra"

COMPRESSION: dict[str, Any] = {
    "key": "compression",
    "label": "압축시험",
    "abbr": "COM",
    "description": "단축 압축.",
    "parser_key": None,
    "channels": [
        {"key": "displacement", "label": "변위", "dimension": "length", "si_unit": "m"},
        {"key": "force", "label": "하중", "dimension": "force", "si_unit": "N"},
    ],
    "conditions": [
        {
            "key": "temperature",
            "label": "시험 온도",
            "value_type": "number",
            "dimension": "temperature",
            "si_unit": "K",
        }
    ],
}


#: 시드가 만든 인장 채널 그대로. 편집 요청은 이것을 기준으로 한 칸씩 바꿔 본다.
TENSILE_CHANNELS: list[dict[str, Any]] = [
    {"key": "displacement", "label": "변위", "dimension": "length", "si_unit": "m"},
    {"key": "force", "label": "하중", "dimension": "force", "si_unit": "N"},
    {
        "key": "specimen_width",
        "label": "시편 폭",
        "dimension": "length",
        "si_unit": "m",
        "is_required": False,
    },
]


@pytest.fixture
def tensile(db: Session) -> None:
    ensure_builtin_test_types(db)
    db.commit()


class TestCreate:
    def test_배포_없이_새_종류를_만든다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """이것이 되지 않으면 '정의는 데이터' 는 말뿐이다."""
        response = client.post("/api/test-types", json=COMPRESSION, headers=admin_headers)
        assert response.status_code == 201, response.text
        created = response.json()
        assert created["key"] == "compression"
        assert [c["key"] for c in created["channels"]] == ["displacement", "force"]

        listed = client.get("/api/test-types", headers=admin_headers).json()
        assert "compression" in {t["key"] for t in listed}

    def test_같은_키는_거절한다(
        self, client: TestClient, admin_headers: dict[str, str], tensile: None
    ) -> None:
        response = client.post(
            "/api/test-types", json={**COMPRESSION, "key": "tensile"}, headers=admin_headers
        )
        assert response.status_code == 409

    def test_채널이_없으면_거절한다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        response = client.post(
            "/api/test-types", json={**COMPRESSION, "channels": []}, headers=admin_headers
        )
        assert response.status_code == 422

    def test_모르는_단위를_거절한다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """저장은 되는데 변환할 때 터진다 — 그때는 이미 데이터가 들어온 뒤다."""
        broken = {
            **COMPRESSION,
            "channels": [
                {"key": "force", "label": "하중", "dimension": "force", "si_unit": "furlong"}
            ],
        }
        response = client.post("/api/test-types", json=broken, headers=admin_headers)
        assert response.status_code == 422
        assert "furlong" in response.json()["error"]["message"]

    def test_차원과_단위가_어긋나면_거절한다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        broken = {
            **COMPRESSION,
            "channels": [
                {"key": "force", "label": "하중", "dimension": "force", "si_unit": "mm"}
            ],
        }
        response = client.post("/api/test-types", json=broken, headers=admin_headers)
        assert response.status_code == 422

    def test_등록되지_않은_파서는_거절한다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """**파서는 정의로 만들 수 없다 — 코드다.** 그 경계를 흐리면 사용자는
        종류를 만들어 놓고 왜 파일이 안 읽히는지 모른다."""
        response = client.post(
            "/api/test-types",
            json={**COMPRESSION, "parser_key": "nonexistent"},
            headers=admin_headers,
        )
        assert response.status_code == 422
        assert "파서" in response.json()["error"]["message"]

    def test_등록된_파서는_고를_수_있다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        parsers = client.get("/api/test-types/parsers", headers=admin_headers)
        assert parsers.status_code == 200, parsers.text
        assert "zwick_tra" in {p["id"] for p in parsers.json()}
        assert (
            ".tra" in next(p for p in parsers.json() if p["id"] == "zwick_tra")["extensions"]
        )


class TestEditWithoutData:
    def test_데이터가_없으면_무엇이든_바꾼다(
        self, client: TestClient, admin_headers: dict[str, str], tensile: None
    ) -> None:
        """아직 아무도 안 쓴 정의는 자유롭게 고칠 수 있어야 한다 — 잠그는 이유는
        데이터를 지키기 위해서지 규율 자체가 목적이 아니다.

        **차원까지 바꿔 본다.** 저장 단위는 고를 수 없고 차원을 따라오므로,
        해석이 완전히 달라지는 변경은 이것뿐이다.
        """
        response = client.put(
            "/api/test-types/tensile",
            json={
                "label": "인장시험(개정)",
                "abbr": "TEN",
                "parser_key": "zwick_tra",
                "channels": [
                    {
                        "key": "displacement",
                        "label": "변위",
                        "dimension": "length",
                        "si_unit": "m",
                    },
                    {"key": "force", "label": "응력", "dimension": "stress", "si_unit": "Pa"},
                ],
                "conditions": [],
            },
            headers=admin_headers,
        )
        assert response.status_code == 200, response.text
        updated = response.json()
        assert updated["label"] == "인장시험(개정)"
        assert {c["si_unit"] for c in updated["channels"]} == {"m", "Pa"}
        assert updated["conditions"] == []

    def test_저장_단위를_고를_수_없다(
        self, client: TestClient, admin_headers: dict[str, str], tensile: None
    ) -> None:
        """**값은 언제나 그 차원의 정본 SI 로 저장된다.** 정의에 `kN` 이라고 적으면
        저장된 숫자는 N 인데 화면·계산은 kN 으로 읽어 1000배 틀린다 — 숫자가
        멀쩡해 보여 티가 나지 않는 그 계열이다.

        데이터가 없어도 거절한다. 이건 데이터를 지키는 잠금이 아니라 **애초에
        성립하지 않는 상태**를 막는 것이다.
        """
        response = client.put(
            "/api/test-types/tensile",
            json={
                "label": "인장시험",
                "abbr": "TEN",
                "parser_key": "zwick_tra",
                "channels": [
                    {"key": "force", "label": "하중", "dimension": "force", "si_unit": "kN"},
                ],
                "conditions": [],
            },
            headers=admin_headers,
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "MNX-TESTS-0018"
        assert "저장 단위는 N" in response.json()["error"]["message"]


class TestEditWithData:
    @pytest.fixture
    def with_run(
        self, client: TestClient, admin_headers: dict[str, str], tensile: None
    ) -> None:
        material = client.post(
            "/api/materials",
            json={
                "family": "Metal",
                "category": "Steel",
                "grade": "SECC",
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
        client.post(
            "/api/test-runs",
            data={
                "specimen_id": specimen["id"],
                "test_type": "tensile",
                "conditions": "{}",
            },
            files={"file": ("Example.tra", TRA.read_bytes())},
            headers=admin_headers,
        )

    def _put(
        self, client: TestClient, headers: dict[str, str], channels: list[dict[str, Any]]
    ) -> Any:
        return client.put(
            "/api/test-types/tensile",
            json={
                "label": "인장시험",
                "abbr": "TEN",
                "parser_key": "zwick_tra",
                "channels": channels,
                "conditions": [],
            },
            headers=headers,
        )

    def test_단위를_바꾸면_거절한다(
        self, client: TestClient, admin_headers: dict[str, str], with_run: None
    ) -> None:
        """**저장된 숫자는 그대로인데 뜻만 바뀐다.** 3466.4 N 이 3466.4 Pa 가 되고
        화면 어디에도 티가 안 난다.

        저장 단위는 고를 수 없으므로 단위가 바뀌는 길은 **차원을 바꾸는 것**뿐이다.
        """
        changed = [
            {**TENSILE_CHANNELS[0]},
            {**TENSILE_CHANNELS[1], "dimension": "stress", "si_unit": "Pa"},
            {**TENSILE_CHANNELS[2]},
        ]
        response = self._put(client, admin_headers, changed)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "MNX-TESTS-0019"
        assert "티가" in response.json()["error"]["message"]

    def test_채널을_지우면_거절한다(
        self, client: TestClient, admin_headers: dict[str, str], with_run: None
    ) -> None:
        """이미 저장된 곡선이 그 이름으로 열을 갖고 있다."""
        response = self._put(client, admin_headers, TENSILE_CHANNELS[:2])
        assert response.status_code == 409
        assert "specimen_width" in response.json()["error"]["message"]

    def test_라벨과_필수여부는_바꿀_수_있다(
        self, client: TestClient, admin_headers: dict[str, str], with_run: None
    ) -> None:
        """해석을 바꾸지 않는 것까지 잠그면 정의를 데이터로 둔 뜻이 없다."""
        renamed = [
            {**TENSILE_CHANNELS[0], "label": "크로스헤드 변위"},
            {**TENSILE_CHANNELS[1], "is_required": False},
            {**TENSILE_CHANNELS[2]},
        ]
        response = self._put(client, admin_headers, renamed)
        assert response.status_code == 200, response.text
        by_key = {c["key"]: c for c in response.json()["channels"]}
        assert by_key["displacement"]["label"] == "크로스헤드 변위"
        assert by_key["force"]["is_required"] is False

    def test_채널을_더하는_것은_된다(
        self, client: TestClient, admin_headers: dict[str, str], with_run: None
    ) -> None:
        """새 채널은 기존 데이터의 해석을 바꾸지 않는다."""
        response = self._put(
            client,
            admin_headers,
            [
                *TENSILE_CHANNELS,
                {
                    "key": "temperature",
                    "label": "온도",
                    "dimension": "temperature",
                    "si_unit": "K",
                    "is_required": False,
                },
            ],
        )
        assert response.status_code == 200, response.text
        assert len(response.json()["channels"]) == 4

    def test_시험이_있으면_종류를_지우지_못한다(
        self, client: TestClient, admin_headers: dict[str, str], with_run: None
    ) -> None:
        """지우면 그 시험들이 무엇이었는지 말할 수 없게 된다."""
        response = client.delete("/api/test-types/tensile", headers=admin_headers)
        assert response.status_code == 409
        assert "중단" in response.json()["error"]["message"]

    def test_안_쓰는_종류는_지울_수_있다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        client.post("/api/test-types", json=COMPRESSION, headers=admin_headers)
        response = client.delete("/api/test-types/compression", headers=admin_headers)
        assert response.status_code == 204
        listed = client.get("/api/test-types", headers=admin_headers).json()
        assert "compression" not in {t["key"] for t in listed}


class TestPermissions:
    def test_일반_사용자는_정의를_바꿀_수_없다(
        self, client: TestClient, db: Session, tensile: None
    ) -> None:
        from sqlalchemy import select

        from app.modules.accounts.models import User
        from app.modules.auth import security
        from app.modules.workspaces.models import Workspace

        workspace = db.scalar(select(Workspace))
        db.add(
            User(
                email="member",
                password_hash=security.hash_password("member-password-1"),
                display_name="일반 사용자",
                status="active",
                is_system_admin=False,
                home_workspace_id=workspace.id if workspace else None,
            )
        )
        db.commit()
        token = client.post(
            "/api/auth/login", json={"email": "member", "password": "member-password-1"}
        ).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        assert (
            client.post("/api/test-types", json=COMPRESSION, headers=headers).status_code
            == 403
        )
        assert client.delete("/api/test-types/tensile", headers=headers).status_code == 403
        # 읽기는 된다 — 업로드 폼을 그리려면 정의가 필요하다
        assert client.get("/api/test-types", headers=headers).status_code == 200


class Test검증오류메시지:
    """**어느 칸이 왜 틀렸는지 말한다.**

    실사용 보고: 시험 종류 키에 `DMA` 를 넣었더니 "요청 형식이 올바르지 않습니다"
    만 떴다. 대소문자 규칙에 걸린 것인데 화면은 그 사실을 말해 주지 않아 무엇을
    고쳐야 할지 알 수 없었다.
    """

    def test_어느_칸이_틀렸는지_말한다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        response = client.post(
            "/api/test-types",
            json={
                "key": "DMA",
                "label": "DMA 스윕",
                "abbr": "DMA",
                "channels": [],
                "conditions": [],
            },
            headers=admin_headers,
        )
        assert response.status_code == 422
        message = response.json()["error"]["message"]
        assert "key" in message
        assert "쓸 수 없는 문자" in message
        # 무엇이 허용되는지도 함께 준다 — 규칙을 모르면 고칠 수 없다.
        assert "a-z" in message

    def test_중첩된_칸도_짚어_준다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """채널이 여러 줄일 때 '어느 줄' 인지가 없으면 찾을 수 없다."""
        response = client.post(
            "/api/test-types",
            json={
                "key": "bend",
                "label": "굽힘",
                "abbr": "BND",
                "channels": [
                    {"key": "force", "label": "하중", "dimension": "force", "si_unit": "N"},
                    {"key": "x", "label": "", "dimension": "length", "si_unit": "m"},
                ],
                "conditions": [],
            },
            headers=admin_headers,
        )
        assert response.status_code == 422
        message = response.json()["error"]["message"]
        assert "channels[1].label" in message

    def test_자세한_내용은_details_에_그대로_남는다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """사람이 읽는 요약과 별개로, 원본은 진단용으로 남겨 둔다."""
        response = client.post(
            "/api/test-types",
            json={"key": "DMA", "label": "x", "abbr": "DMA", "channels": [], "conditions": []},
            headers=admin_headers,
        )
        assert response.json()["error"]["details"]["errors"]
