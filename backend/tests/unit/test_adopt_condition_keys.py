"""문헌 반영 화면의 **조건 키 표가 서버와 같다**(2026-11-15).

화면(`frontend/src/modules/catalog/AdoptDialog.tsx` 의 `CATALOG_KEYS`)은 문헌 값의 조건에서
온도 · 주파수 · 파장을 SI 로 읽어 선언 물성 점에 싣는다. 서버의 표는
`standard_conditions.catalog_keys` 다. 화면이 `frequency_hz` 하나만 읽고 있어서, 씨앗의
`frequency_MHz` · `frequency_ghz` 값 약 300건이 주파수 없는 유전율로 담겼다. 표가 두 벌이라
여기서 글자를 읽어 맞대 본다 — 화면 표를 손으로 고치면 여기서 멈춘다.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

import pytest

from app.shared import declared_conditions, standard_conditions
from matcore import units

DIALOG = (
    Path(__file__).resolve().parents[3]
    / "frontend"
    / "src"
    / "modules"
    / "catalog"
    / "AdoptDialog.tsx"
)

_ENTRY = re.compile(r"\[\s*'([^']+)'\s*,\s*([^,\]]+?)\s*,\s*([^,\]]+?)\s*\]")


def _number(expression: str) -> float:
    """표의 수식(`5 / 9` · `1 / (2 * Math.PI)` · `CELSIUS_ZERO_K - (32 * 5) / 9`)을 숫자로 —
    이 꼴만 받는다(아래 정규식이 숫자 · 연산자 · 괄호만 통과시킨다). `CELSIUS_ZERO_K` 는 화면이
    단위 표에서 읽는 0 °C 의 켈빈이다 — 서버 단위 표의 `degC` 오프셋과 같아야 한다."""
    zero = repr(float(units.unit_of("degC").offset))
    text = expression.replace("Math.PI", repr(math.pi)).replace("CELSIUS_ZERO_K", zero)
    assert re.fullmatch(r"[\d.e+\-*/() ]+", text), expression
    return float(eval(text, {"__builtins__": {}}, {}))


def _table() -> dict[str, list[tuple[str, float, float]]]:
    source = DIALOG.read_text(encoding="utf-8")
    head = source.index("const CATALOG_KEYS")
    body = source[head : source.index("\n}\n", head)]
    out: dict[str, list[tuple[str, float, float]]] = {}
    for block in re.finditer(r"(\w+): \[(.*?)\n  \]", body, re.S):
        out[block.group(1)] = [
            (key, _number(factor), _number(offset))
            for key, factor, offset in _ENTRY.findall(block.group(2))
        ]
    return out


@pytest.mark.parametrize(
    ("point_key", "quantity"),
    [
        (declared_conditions.TEMPERATURE.key, "temperature"),
        (declared_conditions.FREQUENCY.key, "frequency"),
        (declared_conditions.WAVELENGTH.key, "wavelength"),
    ],
)
def test_화면의_조건_키_표가_서버_표와_같다(point_key: str, quantity: str) -> None:
    screen = _table()[point_key]
    server = standard_conditions.catalog_keys(quantity)
    assert [one[0] for one in screen] == [one[0] for one in server]
    for (_, factor, offset), (_, want_factor, want_offset) in zip(screen, server, strict=True):
        assert factor == pytest.approx(want_factor)
        assert offset == pytest.approx(want_offset)
