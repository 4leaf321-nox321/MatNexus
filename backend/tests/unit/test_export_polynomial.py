"""2차 다항식 초탄성(`polynomial_2`, 2026-10-12) — 솔버마다 **칸의 자리**를 못 박는다.

정의판과 코드판이 서로 같은지는 `test_export_twins.py` 가 보지만, 둘이 같이 틀리면 못 문다.
여기서는 매뉴얼의 칸 차례를 직접 대 본다 — 자리가 하나 밀리면 C11 이 C20 으로 읽히고 고무가
다른 재료로 조용히 돈다.

    Abaqus      *HYPERELASTIC, POLYNOMIAL, N=2   C10, C01, C20, C11, C02, D1, D2
    ANSYS       TB,HYPER,,,5,MOONEY              C10, C01, C20, C11, C02, d
    LS-DYNA     *MAT_077_H 카드 2                C10 C01 C11 C20 C02 C30
    Nastran     MATHP                            NA=2(기본 1 이면 2차 항을 버린다), A20 A11 A02
    OptiStruct  MATHE MOONEY                     C20 C11 C02 (NA 기본 2)
"""

from __future__ import annotations

from typing import Any

from matcore import cards, export
from matcore.export import ansys, bulk, dyna, radioss  # noqa: F401  (렌더러 등록)

cards.load_builtin()

C = {"c10": 300000.0, "c01": 60000.0, "c20": 2000.0, "c11": -1500.0, "c02": 800.0}
BLOCKS: dict[str, Any] = {
    "elastic": {"values": {"poisson_ratio": 0.4995, "density": 1100.0}},
    "hyperelastic": {
        "values": {"family": "polynomial_2"},
        "rows": [{"name": name, "value": value, "si_unit": "Pa"} for name, value in C.items()],
    },
}


def text(key: str) -> list[str]:
    deck = export.Deck(name="POLY", solver_id=7, blocks=BLOCKS)
    return export.render(key, deck, export.SYSTEMS[0]).text.splitlines()


def numbers(line: str, sep: str = ",") -> list[float]:
    return [float(one) for one in line.split(sep) if one.strip()]


def test_Abaqus_는_C10_C01_C20_C11_C02_D1_D2() -> None:
    lines = text("abaqus_hyperelastic")
    data = numbers(lines[lines.index("*HYPERELASTIC, POLYNOMIAL, N=2") + 1])
    assert data[:5] == [C["c10"], C["c01"], C["c20"], C["c11"], C["c02"]]
    assert data[5] > 0 and data[6] == 0.0


def test_ANSYS_는_다섯_항_MOONEY() -> None:
    lines = text("ansys_hyperelastic")
    assert "TB,HYPER,MNX_MAT,1,5,MOONEY" in lines
    data = numbers(
        next(one for one in lines if one.startswith("TBDATA,1,")).removeprefix("TBDATA,1,")
    )
    assert data[:5] == [C["c10"], C["c01"], C["c20"], C["c11"], C["c02"]]


def test_LS_DYNA_는_C11_이_C20_앞이다() -> None:
    lines = text("dyna_hyperelastic")
    card2 = lines[
        lines.index("$      c10       c01       c11       c20       c02       c30    therml")
        + 1
    ]
    fields = [float(card2[at : at + 10]) for at in range(0, 60, 10)]
    assert fields == [C["c10"], C["c01"], C["c11"], C["c20"], C["c02"], 0.0]


def test_Nastran_은_NA_2_를_적는다() -> None:
    lines = text("nastran_hyperelastic")
    start = next(i for i, one in enumerate(lines) if one.startswith("MATHP*"))
    card = lines[start:]
    # 큰 칸 형식: 줄마다 앞 8자 + 16자 칸 넷. 논리 2번 줄(물리 셋째)의 둘째 · 셋째 칸이
    # NA · ND 다.
    second = card[2]
    assert second[8 + 16 : 8 + 32].strip() == "2"
    assert second[8 + 32 : 8 + 48].strip() == "1"
    third = card[4]
    assert [float(third[8 + 16 * i : 8 + 16 * (i + 1)]) for i in range(3)] == [
        C["c20"],
        C["c11"],
        C["c02"],
    ]


def test_OptiStruct_는_C20_줄() -> None:
    lines = text("optistruct_hyperelastic")
    start = next(i for i, one in enumerate(lines) if one.startswith("MATHE*"))
    assert "MOONEY" in lines[start]
    third = lines[start + 4]
    assert [float(third[8 + 16 * i : 8 + 16 * (i + 1)]) for i in range(3)] == [
        C["c20"],
        C["c11"],
        C["c02"],
    ]


def test_Radioss_는_거절한다() -> None:
    deck = export.Deck(name="POLY", solver_id=7, blocks=BLOCKS)
    try:
        export.render("openradioss_hyperelastic", deck, export.SYSTEMS[0])
    except export.ExportError as refused:
        assert "2차 다항식" in str(refused)
    else:
        raise AssertionError("LAW42 는 2차 다항식을 못 받는다")


def test_초기_전단탄성률은_2_C10_C01() -> None:
    assert export.initial_shear("polynomial_2", C) == 2 * (C["c10"] + C["c01"])
