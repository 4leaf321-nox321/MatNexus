"""프로파일이 메타를 **시험 칸**과 **식별자**에 잇는다.

둘을 갈라 둔 이유는 되돌릴 수 있는 실수와 없는 실수의 차이다. 시험자를 잘못
채우면 고치면 되지만, 곡선이 남의 재료에 붙으면 그 시험은 만들 때 그 시편 id 에
묶여 있어 칸을 고쳐 되돌릴 수 없다. 그래서 **시험 칸은 채우고, 식별자는 짚기만
한다.**
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.modules.tests.legacy_profiles import LEGACY_TENSILE_DEFINITION
from matcore.readers import profile as profiles

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
WITH_UNITS = FIXTURES / "legacy_tensile.mtet"


def made(**meta: Any) -> bytes:
    """메타 키-값과 최소한의 표를 가진 JSON."""
    doc: dict[str, Any] = {
        **meta,
        "curve": [
            {"disp": 0.0, "load": 0.0},
            {"disp": 0.1, "load": 400.0},
        ],
    }
    return json.dumps(doc, ensure_ascii=False).encode("utf-8")


BASE: dict[str, Any] = {
    "match": {"extensions": [".json"], "header_any": ["load"]},
    "tables": {"mode": "all", "include": "^curve$"},
    "columns": {
        "disp": {"channel": "displacement", "unit": "mm"},
        "load": {"channel": "force", "unit": "N"},
    },
}


class Test옛_정의는_안_바뀐다:
    def test_선언이_없으면_비어_있다(self) -> None:
        """**하위 호환.** 기존 프로파일에 이 자리가 없으면 전과 똑같아야 한다."""
        parsed = profiles.apply(LEGACY_TENSILE_DEFINITION, WITH_UNITS.read_bytes())
        assert parsed.record == {}
        assert parsed.identity == {}


class Test시험_칸:
    def test_선언한_칸을_읽는다(self) -> None:
        rule = {**BASE, "record": {"작업자": {"field": "operator"}}}
        parsed = profiles.apply(rule, made(작업자="홍길동"))
        assert parsed.record == {"operator": "홍길동"}

    def test_원문이_메타에_그대로_남는다(self) -> None:
        """가져가 버리면 "파일에는 뭐라고 적혀 있었나" 에 못 답한다 — 그건 원본
        보관의 뜻을 반쯤 없앤다."""
        rule = {**BASE, "record": {"작업자": {"field": "operator"}}}
        parsed = profiles.apply(rule, made(작업자="홍길동"))
        assert "홍길동" in parsed.metadata.values()

    def test_빈_값은_안_적은_것이다(self) -> None:
        """`Unknown` 을 그대로 넣으면 시험자가 `Unknown` 인 기록이 생기고, 그
        뒤로는 그 칸이 비어 있었다는 사실을 알 수 없다."""
        rule = {
            **BASE,
            "record": {"작업자": {"field": "operator"}, "장비": {"field": "instrument"}},
        }
        parsed = profiles.apply(rule, made(작업자="Unknown", 장비="  "))
        assert parsed.record == {}


class Test날짜:
    def test_ISO_는_그냥_읽는다(self) -> None:
        rule = {**BASE, "record": {"일자": {"field": "tested_at"}}}
        parsed = profiles.apply(rule, made(일자="2024-03-11T09:00:00"))
        assert parsed.record["tested_at"] == "2024-03-11T09:00:00"

    def test_형식을_적으면_그것으로_읽는다(self) -> None:
        rule = {**BASE, "record": {"일자": {"field": "tested_at", "format": "%d/%m/%Y"}}}
        parsed = profiles.apply(rule, made(일자="05/06/2020"))
        assert parsed.record["tested_at"].startswith("2020-06-05")

    def test_형식을_모르면_짐작하지_않는다(self) -> None:
        """`05/06/2020` 은 6월 5일일 수도 5월 6일일 수도 있다. **둘 다 그럴듯해서**
        잘못 읽어도 화면 어디에도 티가 안 난다."""
        rule = {**BASE, "record": {"일자": {"field": "tested_at", "format": "%Y-%m-%d"}}}
        parsed = profiles.apply(rule, made(일자="05/06/2020"))
        assert "tested_at" not in parsed.record
        assert any("일자" in warning for warning in parsed.warnings)


class Test식별자:
    def test_짚어_주기만_한다(self) -> None:
        rule = {
            **BASE,
            "identity": {
                "재료": {"field": "material_grade"},
                "로트": {"field": "sample_lot_no"},
            },
        }
        parsed = profiles.apply(rule, made(재료="SECC", 로트="LOT-A"))
        assert parsed.identity == {"material_grade": "SECC", "sample_lot_no": "LOT-A"}
        # **채우지 않는다.** 곡선과 섞이지 않아야 한다.
        assert parsed.record == {}

    def test_식별자에는_날짜_형식이_없다(self) -> None:
        """식별자는 이름이지 시각이 아니다. 형식을 적어도 안 쓴다."""
        rule = {**BASE, "identity": {"재료": {"field": "material_grade", "format": "%Y"}}}
        parsed = profiles.apply(rule, made(재료="2024"))
        assert parsed.identity == {"material_grade": "2024"}
