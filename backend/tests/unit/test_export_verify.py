"""1요소 검증 모델(`matcore.export.verify`, 2026-10-12).

키트가 틀리면 해석 담당이 **맞는 덱을 틀렸다고** 읽는다 — 그래서 여기서 무는 것:

    기대 응답   README 의 손계산(DP600 σx 700.32 MPa · εp 0.40213 · 반력 467.50 N,
               고무 4.725 MPa)과 같은가. 당기는 양이 카드가 아는 범위 안인가
    끼우기     재료 번호 1 · Abaqus 재료 이름 · Radioss 런 이름이 모델과 맞는가, 틀의 자리가
               남지 않았나, 고정폭 칸(Nastran SPCD 8칸 · 곡선 20칸)에 당기는 양이 들어갔나
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from matcore import cards, export
from matcore.export import ansys, bulk, dyna, radioss, verify  # noqa: F401  (렌더러 등록)
from matcore.export.systems import MM_N_TONNE

cards.load_builtin()

CURVE = [(0.0, 350e6), (0.02, 455e6), (0.1, 560e6), (0.4, 700e6), (1.0, 790e6)]
STEEL: dict[str, Any] = {
    "elastic": {"values": {"youngs_modulus": 210e9, "poisson_ratio": 0.3, "density": 7850.0}},
    "table": {"rows": [{"plastic_strain": x, "true_stress": y} for x, y in CURVE]},
}
RUBBER: dict[str, Any] = {
    "elastic": {"values": {"poisson_ratio": 0.4995, "density": 1100.0}},
    "hyperelastic": {
        "values": {"family": "mooney_rivlin"},
        "rows": [
            {"name": "c10", "value": 0.6e6, "si_unit": "Pa"},
            {"name": "c01", "value": 0.15e6, "si_unit": "Pa"},
        ],
    },
}


def kit(key: str, blocks: dict[str, Any], name: str = "CASE") -> verify.Kit:
    deck = export.Deck(name=name, solver_id=7, blocks=blocks)
    rendered = export.render(key, replace(deck, solver_id=1), MM_N_TONNE)
    return verify.build(key, key, deck, rendered.text, rendered.notes)


def last(made: verify.Kit) -> dict[str, float]:
    lines = made.files["expected.csv"].decode().splitlines()
    return dict(zip(lines[0].split(","), map(float, lines[-1].split(",")), strict=True))


def model(made: verify.Kit) -> str:
    names = [name for name in made.files if name.endswith(("inp", "dat", "k", "bdf", "fem"))]
    names += [name for name in made.files if name.endswith("_0000.rad")]
    return made.files[names[0]].decode()


@pytest.mark.parametrize("key", sorted(verify.KITS))
def test_열두_형식이_다_키트를_낸다(key: str) -> None:
    case, _ = verify.KITS[key]
    made = kit(key, STEEL if case == "tension" else RUBBER)
    text = model(made)
    assert "@@" not in text
    assert {"expected.csv", "README.txt"} <= set(made.files)
    # 정의판 형식도 같은 키트를 쓴다.
    assert verify.kit_for(f"{key}_def") == verify.KITS[key]


def test_탄소성_기대값은_README_손계산과_같다() -> None:
    """공칭 50% 에서 진응력 700.32 · 소성 0.40213 · 대수 ln 1.5 · 반력 467.50(소성 비압축 +
    탄성 체적)."""
    made = kit("dyna", STEEL)
    assert made.pull == 0.5
    end = last(made)
    assert end["log_strain"] == pytest.approx(0.405465, abs=1e-6)
    assert end["true_stress_MPa"] == pytest.approx(700.32, abs=0.01)
    assert end["plastic_strain"] == pytest.approx(0.40213, abs=1e-5)
    assert end["reaction_N"] == pytest.approx(467.50, abs=0.01)


def test_소성_표_너머로는_안_당긴다() -> None:
    """표 끝(εp 0.1) 너머는 솔버마다 늘리는 법이 달라 기대값이 하나로 서지 않는다."""
    short = {
        **STEEL,
        "table": {"rows": [{"plastic_strain": x, "true_stress": y} for x, y in CURVE[:3]]},
    }
    made = kit("abaqus", short)
    assert last(made)["plastic_strain"] == pytest.approx(0.09, abs=2e-4)
    assert f"PULL, 1, 1, {made.pull:.4f}" in model(made)


def test_고무_기대값은_비압축_해석해() -> None:
    made = kit("abaqus_hyperelastic", RUBBER)
    assert made.pull == 1.0
    assert last(made)["true_stress_MPa"] == pytest.approx(4.725, abs=1e-6)
    assert last(made)["nominal_stress_MPa"] == pytest.approx(2.3625, abs=1e-6)


def test_고무는_맞춘_구간_끝까지만() -> None:
    fitted = {
        **RUBBER,
        "hyperelastic": {
            **RUBBER["hyperelastic"],
            "values": {"family": "mooney_rivlin", "strain_max": 0.6},
        },
    }
    assert kit("ansys_hyperelastic", fitted).pull == 0.6


@pytest.mark.parametrize(
    ("family", "values", "stress"),
    [
        # Ogden(Abaqus 규약) α=3, λ=2: (2μ/α)(λ^α - λ^(-α/2)) — check_openradioss 의 기대값.
        ("ogden_1", {"mu": 1.5, "alpha": 3.0}, 7.646),
        # Neo-Hookean C10 = 0.5: 2(λ² - 1/λ)·C10 = 3.5
        ("neo_hookean", {"c10": 0.5}, 3.5),
    ],
)
def test_다른_식의_해석해(family: str, values: dict[str, float], stress: float) -> None:
    assert verify.rubber_stress(family, values, 2.0) == pytest.approx(stress, abs=1e-3)


def test_다항식은_I2_항까지_넣는다() -> None:
    """C11 · C02 를 빼면 2차 다항식 카드의 기대값이 조용히 낮게 나온다."""
    base = verify.rubber_stress("polynomial_2", {"c10": 0.3, "c01": 0.06}, 2.0)
    full = verify.rubber_stress(
        "polynomial_2", {"c10": 0.3, "c01": 0.06, "c11": 0.01, "c02": 0.01}, 2.0
    )
    i1, i2 = 4 + 1.0, 4 + 0.25
    w1 = 0.3 + 0.01 * (i2 - 3)
    w2 = 0.06 + 0.01 * (i1 - 3) + 2 * 0.01 * (i2 - 3)
    assert full == pytest.approx(2 * (4 - 0.5) * (w1 + w2 / 2), abs=1e-9)
    assert full > base


def test_Abaqus_재료_이름이_단면과_같다() -> None:
    text = model(kit("abaqus", STEEL, name="SUS304"))
    assert "*SOLID SECTION, ELSET=CUBE, MATERIAL=SUS304" in text
    assert "*MATERIAL, NAME=SUS304" in text


def test_LS_DYNA_는_머리와_끝을_한_번씩() -> None:
    text = model(kit("dyna", STEEL))
    assert text.count("*KEYWORD") == 1 and text.count("*END") == 1
    assert "*MAT_PIECEWISE_LINEAR_PLASTICITY" in text
    ramp = text.splitlines()[
        text.splitlines().index("pull ramp:  0 -> 0.5000 mm over 0.01 s") + 4
    ]
    assert ramp == f"{'0.0100':>20}{'0.5000':>20}"


def test_Nastran_SPCD_는_8칸() -> None:
    """D1 · D2 는 33~40 · 57~64 열 — 칸을 벗기지 않고 열 그대로 본다(칸 안의 빈칸을 벗기면
    한 자 밀린 것도 통과한다)."""
    text = model(kit("nastran_plastic", STEEL))
    spcd = [line for line in text.splitlines() if line.startswith("SPCD")]
    assert len(spcd) == 2
    for line in spcd:
        assert line[32:40] == "0.5000  " and line[56:64] == "0.5000  "
        assert line[40:48].rstrip() in ("3", "7") and line[48:56] == "1       "


def test_Radioss_는_런_이름이_맞고_끝이_하나() -> None:
    made = kit("openradioss_hyperelastic", RUBBER)
    starter = made.files[f"{verify.RADIOSS_RUN}_0000.rad"].decode()
    engine = made.files[f"{verify.RADIOSS_RUN}_0001.rad"].decode()
    assert f"/BEGIN\n{verify.RADIOSS_RUN}\n" in starter
    assert f"/RUN/{verify.RADIOSS_RUN}/1" in engine
    assert starter.count("\n/END") == 1 and starter.rstrip().endswith("/END")
    assert "/MAT/LAW42/1" in starter and "#RADIOSS STARTER" in starter.split("\n")[0]


def test_키트가_없는_형식은_까닭을_말한다() -> None:
    deck = export.Deck(name="CASE", solver_id=1, blocks=STEEL)
    with pytest.raises(export.ExportError, match="검증 모델이 아직 없습니다"):
        verify.build("dyna_elastic", "LS-DYNA (선형)", deck, "")
