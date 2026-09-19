"""단위 환산 API — **서버가 곱한다.** AI 가 머릿속으로 곱하지 않게(2026-09-19).

MCP 안내는 「환산하지 마라」 고 말해 왔는데 시킬 손잡이가 없었다. 손잡이가 없으면
말은 지켜지지 않는다 — tonne/mm³ 를 kg/m³ 로 옮기며 10¹² 을 세는 것은 사람도 자주
틀린다.

무는 것:

    알려진 환산표대로 나온다        300 MPa = 30.59 kgf/mm²
    비우면 저장 단위(SI)로          to 를 안 주면 그 차원의 정본
    차원이 다르면 거절한다          항복강도를 °C 로 — 숫자는 나와도 뜻이 없다
    모르는 단위는 까닭과 함께       「갈리는 표기」 는 「표에 없다」 와 다음 할 일이 다르다
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient


def _convert(client: TestClient, headers: dict[str, str], **params: object) -> Any:
    return client.get("/api/units/convert", params=params, headers=headers)


class Test환산:
    @pytest.mark.parametrize(
        ("value", "from_unit", "to_unit", "expected"),
        [
            (300, "MPa", "kgf/mm2", 30.5915),  # 국내 성적서 표기
            (1, "tonne/mm3", "kg/m3", 1.0e12),  # Abaqus mm-tonne 계 밀도
            (25, "degC", "K", 298.15),  # 오프셋
            (1, "W/(mm*K)", "W/(m.K)", 1000.0),  # 접두어 조합 + 곱 기호
            (2.5, "%", "1", 0.025),
        ],
    )
    def test_알려진_환산표대로_나온다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        value: float,
        from_unit: str,
        to_unit: str,
        expected: float,
    ) -> None:
        got = _convert(
            client, admin_headers, value=value, **{"from": from_unit, "to": to_unit}
        )
        assert got.status_code == 200, got.text
        assert got.json()["result"] == pytest.approx(expected, rel=1e-4)

    def test_비우면_저장_단위로_간다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        got = _convert(client, admin_headers, value=450, **{"from": "MPa"})
        assert got.status_code == 200, got.text
        body = got.json()
        assert body["to_unit"] == "Pa" and body["result"] == pytest.approx(450e6)
        assert body["si_unit"] == "Pa" and body["dimension"] == "stress"
        # 받은 표기는 정본으로 되돌려 준다 — 사람이 다음에 무엇을 적을지 안다.
        assert body["from_unit"] == "MPa"

    def test_차원이_다르면_거절한다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        got = _convert(client, admin_headers, value=300, **{"from": "MPa", "to": "degC"})
        assert got.status_code == 422
        assert got.json()["error"]["code"] == "MNX-UNITS-0002"

    def test_모르는_단위는_까닭과_함께_거절한다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        got = _convert(client, admin_headers, value=1, **{"from": "furlong"})
        assert got.status_code == 422
        assert got.json()["error"]["code"] == "MNX-UNITS-0001"
        # 대소문자로 갈리는 표기는 **왜 안 받는지**가 실려 온다(ADR 0031 D3-1).
        got = _convert(client, admin_headers, value=1, **{"from": "MPa.s"})
        assert got.status_code == 422
        assert "대소문자" in got.json()["error"]["message"]

    def test_로그인_없이는_못_쓴다(self, client: TestClient) -> None:
        assert _convert(client, {}, value=1, **{"from": "MPa"}).status_code == 401
