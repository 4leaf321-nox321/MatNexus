"""압축 시험 → 압축 응력 · 변형률 · 탄성률 · 규격 지표(확장 `compression`, 2026-10-16).

부호      장비가 압축을 음수로 적어도 양수로 바꾼다 — 통계가 오름차순 변형률을 전제한다
접촉점    닿기 전 구간을 버리고 그 자리를 변형 0 으로
사이클    고무 · 폼은 4번째(ISO 3386) · 3번째(D3574 C) 하중 구간을 쓴다
강도      ISO 844 · D1621: 10% 전의 **항복 봉우리**, 없으면 10% 응력 — 전체 최대가 아니다
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from matcore import extensions
from matcore.processing import Frame, ProcessingError

extensions.load(Path(__file__).resolve().parents[2] / "extensions")

compress = importlib.import_module(f"{extensions.PACKAGE}.compression.compress")

HEIGHT = 0.0125
AREA = np.pi * 0.029**2 / 4
E = 5.0e6


def _frame(**columns: np.ndarray) -> Frame:
    units = {"force": "N", "displacement": "m", "strain": "1"}
    return Frame(dict(columns), {key: units[key] for key in columns})


def _options(**extra: Any) -> dict[str, Any]:
    return {"height": HEIGHT, "area": AREA, **extra}


def _values(step: Any) -> dict[str, float]:
    return {one.key: one.value for one in step.scalars}


def _rubber(top: float = 0.3, points: int = 301) -> tuple[np.ndarray, np.ndarray]:
    strain = np.linspace(0, top, points)
    return strain * HEIGHT, E * strain * AREA


def test_변위를_높이로_나눠_양수_응력_변형률() -> None:
    displacement, force = _rubber()
    step = compress.engineering(_frame(force=force, displacement=displacement), _options())
    strain = step.frame.columns[compress.STRAIN]
    stress = step.frame.columns[compress.STRESS]
    assert strain[-1] == pytest.approx(0.3)
    assert stress[-1] == pytest.approx(E * 0.3)
    found = _values(compress.modulus(step.frame, {"method": "secant", "maximum_strain": 0.1}))
    assert found["compressive_modulus"] == pytest.approx(E, rel=1e-6)


def test_압축이_음수면_뒤집는다() -> None:
    displacement, force = _rubber()
    step = compress.engineering(_frame(force=-force, displacement=-displacement), _options())
    assert step.frame.columns[compress.STRESS][-1] == pytest.approx(E * 0.3)
    assert any("뒤집" in one for one in step.notes)
    kept = compress.engineering(
        _frame(force=-force, displacement=-displacement), _options(sign="as_is")
    )
    assert kept.frame.columns[compress.STRESS][-1] < 0


def test_압축계_변형률이_있으면_그것() -> None:
    displacement, force = _rubber()
    strain = displacement / HEIGHT / 2  # 압축계는 시편 가운데만 — 변위보다 작다
    step = compress.engineering(
        _frame(force=force, displacement=displacement, strain=strain), _options()
    )
    assert step.frame.columns[compress.STRAIN][-1] == pytest.approx(0.15)
    forced = compress.engineering(
        _frame(force=force, displacement=displacement, strain=strain),
        _options(source="displacement"),
    )
    assert forced.frame.columns[compress.STRAIN][-1] == pytest.approx(0.3)


def test_닿기_전_구간을_버리고_변형_0_을_옮긴다() -> None:
    displacement, force = _rubber()
    gap = np.linspace(0, 0.001, 20)  # 1 mm 를 헛누른다
    frame = _frame(
        force=np.concatenate([np.zeros(20), force[1:]]),
        displacement=np.concatenate([gap, displacement[1:] + 0.001]),
    )
    step = compress.engineering(frame, _options())
    strain = step.frame.columns[compress.STRAIN]
    assert strain[0] == pytest.approx(0.0)
    assert strain[-1] == pytest.approx(0.3, rel=0.01)
    assert any("접촉 전" in one for one in step.notes)


def _cycles(count: int, soften: float = 0.1) -> Frame:
    """count 번 0 → 30% → 0. 누를 때마다 soften 만큼 부드러워진다(Mullins)."""
    up = np.linspace(0, 0.3, 61)
    down = up[::-1][1:]
    strain_parts, force_parts = [], []
    for cycle in range(count):
        modulus = E * (1 - soften * cycle)
        strain_parts += [up if cycle == 0 else up[1:], down]
        force_parts += [
            modulus * (up if cycle == 0 else up[1:]) * AREA,
            0.6 * modulus * down * AREA,
        ]
    strain = np.concatenate(strain_parts)
    return _frame(force=np.concatenate(force_parts), displacement=strain * HEIGHT)


def test_사이클을_세고_자동이면_마지막() -> None:
    step = compress.engineering(_cycles(4), _options(contact_force=0.0))
    assert _values(step)["loading_cycle_count"] == 4
    stress = step.frame.columns[compress.STRESS]
    # 마지막(4번째) 하중 구간: E·(1 - 0.3).
    assert stress[-1] == pytest.approx(E * 0.7 * 0.3, rel=1e-6)
    assert np.all(np.diff(step.frame.columns[compress.STRAIN]) >= 0)


def test_규격이_정한_사이클을_고른다() -> None:
    step = compress.engineering(_cycles(4), _options(contact_force=0.0, cycle=2))
    assert step.frame.columns[compress.STRESS][-1] == pytest.approx(E * 0.9 * 0.3, rel=1e-6)
    with pytest.raises(ProcessingError, match="4개뿐"):
        compress.engineering(_cycles(4), _options(contact_force=0.0, cycle=5))


def test_전부_남기면_반복_시험_단계가_사이클을_센다() -> None:
    """하나만 남기면 그 뒤 `cyclic.*` 이 「사이클을 찾지 못했습니다」 로 멈췄다 — 반복 압축의
    사이클 분석을 할 길이 없었다(2026-10-20 검토)."""
    from matcore import registry

    step = compress.engineering(_cycles(4), _options(contact_force=0.0, cycle=-1))
    assert len(step.frame.columns[compress.STRAIN]) == len(_cycles(4).columns["force"])
    assert any("모두 남겼습니다" in one for one in step.notes)
    counted = registry.get("cyclic.cycles").fn(step.frame, {})
    assert {one.key: one.value for one in counted.scalars}["cycle_count"] == 4
    with pytest.raises(ProcessingError, match="-1"):
        compress.engineering(_cycles(4), _options(contact_force=0.0, cycle=-2))


def test_한_번_누른_시험은_구간이_하나() -> None:
    displacement, force = _rubber()
    step = compress.engineering(_frame(force=force, displacement=displacement), _options())
    assert _values(step)["loading_cycle_count"] == 1
    assert not any("하중 구간" in one for one in step.notes)


def _indices(strain: np.ndarray, stress: np.ndarray) -> dict[str, float]:
    frame = Frame(
        {compress.STRAIN: strain, compress.STRESS: stress},
        {compress.STRAIN: "1", compress.STRESS: "Pa"},
    )
    return _values(compress.indices(frame, {}))


def test_닿은_변형률의_응력만_낸다() -> None:
    strain = np.linspace(0, 0.45, 451)
    found = _indices(strain, E * strain)
    assert found["compressive_stress_at_10pct"] == pytest.approx(E * 0.10)
    assert found["compressive_stress_at_40pct"] == pytest.approx(E * 0.40)
    assert "compressive_stress_at_50pct" not in found
    assert "compressive_stress_at_65pct" not in found


def _rigid_foam() -> tuple[np.ndarray, np.ndarray]:
    """5% 에서 항복 봉우리(1 MPa) → 0.8 MPa 평탄 → 50% 뒤 치밀화(봉우리보다 커진다)."""
    strain = np.linspace(0, 0.8, 801)
    stress = np.where(strain < 0.05, 20e6 * strain, 0.0)
    stress = np.where(
        (strain >= 0.05) & (strain < 0.08), 1e6 - (strain - 0.05) / 0.03 * 0.2e6, stress
    )
    stress = np.where((strain >= 0.08) & (strain < 0.5), 0.8e6, stress)
    stress = np.where(strain >= 0.5, 0.8e6 + 20e6 * (strain - 0.5) ** 2, stress)
    return strain, stress


def test_압축_강도는_10퍼센트_전의_항복_봉우리() -> None:
    """**전체 최대가 아니다** — 경질 폼은 치밀화 뒤가 더 크다."""
    strain, stress = _rigid_foam()
    assert float(np.max(stress)) > 1e6
    found = _indices(strain, stress)
    assert found["compressive_strength"] == pytest.approx(1e6, rel=0.01)


def test_봉우리가_없으면_10퍼센트_응력() -> None:
    strain = np.linspace(0, 0.3, 301)
    stress = 1e6 * (1 - np.exp(-strain / 0.03)) + 2e6 * strain
    found = _indices(strain, stress)
    assert found["compressive_strength"] == pytest.approx(
        float(np.interp(0.10, strain, stress))
    )


def test_10퍼센트에_못_닿으면_최대() -> None:
    strain = np.linspace(0, 0.05, 51)
    found = _indices(strain, E * strain)
    assert found["compressive_strength"] == pytest.approx(E * 0.05)


def test_폼_평탄_응력_치밀화_흡수_에너지() -> None:
    strain, stress = _rigid_foam()
    found = _indices(strain, stress)
    assert found["plateau_stress"] == pytest.approx(0.8e6)
    # 0.8e6 + 20e6 (ε - 0.5)² = 1.3 · 0.8e6 → ε = 0.5 + √(0.012) ≈ 0.6095
    assert found["densification_strain"] == pytest.approx(0.5 + np.sqrt(0.012), abs=0.002)
    expected = float(np.trapezoid(stress[strain <= 0.5], strain[strain <= 0.5]))
    assert found["energy_absorption_50pct"] == pytest.approx(expected, rel=1e-3)


def test_높이가_0_이면_멈춘다() -> None:
    displacement, force = _rubber()
    with pytest.raises(ProcessingError, match="높이"):
        compress.engineering(
            _frame(force=force, displacement=displacement), _options(height=0.0)
        )


def _toe_curve(strain_key: str, stress_key: str) -> Frame:
    """앞 2 % 가 눕는 곡선 — 그 뒤 직선을 응력 0 까지 늘이면 1.9 % 에서 만난다."""
    strain = np.linspace(0.0, 0.2, 401)
    soft = (E / 20) * strain
    stiff = E * (strain - 0.019)
    stress = np.where(strain < 0.02, soft, stiff)
    return Frame({strain_key: strain, stress_key: stress}, {strain_key: "1", stress_key: "Pa"})


def test_토우_보정은_인장의_계산을_이_시험의_열로_쓴다() -> None:
    """사용자 보고(2026-10-20): 압축 처리에 토우 보정이 없다 — 기존 단계를 재사용. 열 이름만
    이 시험의 것이 기본으로 선다(사람이 열을 다시 고르지 않아도 된다)."""
    from matcore import processing, registry

    frame = _toe_curve("compressive_strain", "compressive_stress")
    out = processing.apply(
        [
            processing.Step(
                "compression.toe_compensation", {"minimum_strain": 0.05, "maximum_strain": 0.1}
            )
        ],
        frame,
    )
    found = {one.key: one.value for one in out.stages[-1].scalars}
    assert found["toe_strain_offset"] == pytest.approx(0.019, abs=1e-6)
    assert found["toe_r_squared"] == pytest.approx(1.0)
    moved = out.stages[-1].frame.columns["compressive_strain"]
    assert moved[-1] == pytest.approx(0.2 - 0.019)
    # 계산은 하나다 — 인장의 그 함수를 이 시험의 열로 부른다.
    assert registry.get("compression.toe_compensation").makes_values == (
        registry.get("tensile.toe_compensation").makes_values
    )


class Test초탄성을_압축으로:
    """사용자 보고(2026-10-20): 압축 시험을 초탄성 카드로 내보낼 경로가 없었다 — 식이 단축 인장
    축에만 걸려 있었다. 같은 식을 압축(양수) 축에 뒤집어 걸고, 카드에 모드를 남긴다."""

    C10 = 0.4e6

    def curve(self) -> tuple[np.ndarray, np.ndarray]:
        """Neo-Hookean 단축 압축 — 압축을 양수로 적은 공칭 응력 · 변형률."""
        strain = np.linspace(0.0, 0.4, 41)
        stretch = 1.0 - strain
        return strain, 2.0 * self.C10 * (stretch**-2.0 - stretch)

    def test_압축_데이터로_계수를_되찾고_모드를_남긴다(self) -> None:
        from matcore import fitting

        family = fitting.FAMILIES["neo_hookean_compression"]
        assert (family.x_column, family.y_column) == (compress.STRAIN, compress.STRESS)
        x, y, _notes = family.prepare(*self.curve())
        found = fitting.fit_with(family, x, y)
        assert found.parameters[0].value == pytest.approx(self.C10, rel=1e-6)
        extras = family.extras(np.asarray([self.C10]))
        # **식의 이름은 인장과 같다** — 덱은 그 이름으로 옮긴다. 모드는 데이터의 것.
        assert extras["mode"] == "단축 압축"
        assert extras["model"] == "neo_hookean"
        assert extras["shear_modulus"] == pytest.approx(2 * self.C10)
        # 압축이 커질수록 압축 응력이 커진다 — 안정성 경고가 없어야 한다.
        assert family.stability(np.asarray([self.C10]), x) == []

    def test_넷_다_압축으로_선다(self) -> None:
        from matcore import fitting

        for base in ("neo_hookean", "mooney_rivlin", "yeoh", "ogden_1"):
            twin = fitting.FAMILIES[f"{base}_compression"]
            assert twin.block == "hyperelastic"
            assert twin.parameter_names == fitting.FAMILIES[base].parameter_names

    def test_덱은_같은_식으로_옮긴다(self) -> None:
        """`neo_hookean_compression` 은 덱이 모르는 이름이다 — 식의 이름(`model`)으로
        옮긴다."""
        import matcore.export.dyna  # noqa: F401  (렌더러 등록)
        from matcore import cards
        from matcore.export import Deck, render

        cards.load_builtin()
        rubber = Deck(
            name="EPDM",
            solver_id=7,
            blocks={
                "elastic": {"values": {"poisson_ratio": 0.4995, "density": 1100.0}},
                "hyperelastic": {
                    "values": {
                        "family": "neo_hookean_compression",
                        "model": "neo_hookean",
                        "mode": "단축 압축",
                    },
                    "rows": [{"name": "c10", "value": self.C10}],
                },
            },
        )
        text = render("dyna_hyperelastic", rubber).text
        assert "*MAT_MOONEY-RIVLIN_RUBBER" in text


class Test폼_카드:
    """사용자 보고(2026-10-20): 폼 소재를 해석 카드로 내보낼 경로가 없었다 — 「폼 카드
    공칭응력-변형률 표 블록 대응 필요」."""

    foam = importlib.import_module(f"{extensions.PACKAGE}.compression.foam")

    @staticmethod
    def member(label: str, top: float, scale: float = 1.0) -> Any:
        from matcore.groups import Member

        strain = np.linspace(0.0, top, 301)
        # 연질 폼 모양 — 처음 직선(0.1 MPa/1), 평탄, 끝에서 치밀화로 가팔라진다.
        stress = scale * (0.1e6 * strain + 2.0e6 * strain**4)
        return Member(label=label, columns={compress.STRAIN: strain, compress.STRESS: stress})

    def test_공통_구간에서_평균하고_짧은_끝에서_자른다(self) -> None:
        got = self.foam.foam_curve([self.member("A", 0.7, 0.9), self.member("B", 0.6, 1.1)])
        assert got.values["strain_max"] == pytest.approx(0.6)
        assert got.values["sample_count"] == 2
        strain, stress = got.columns[compress.STRAIN], got.columns[compress.STRESS]
        assert strain[0] == 0.0 and stress[0] == 0.0
        # 평균(0.9 · 1.1 → 1.0)이다 — 한 시편의 곡선이 아니다.
        # 길게 간 시편은 그 끝을 보간한다 — 직선 보간의 오차만큼(4차 곡선) 느슨하게.
        assert stress[-1] == pytest.approx(0.1e6 * 0.6 + 2.0e6 * 0.6**4, rel=1e-4)
        assert any("가장 짧은 시편의 끝" in one for one in got.warnings)
        # 처음 기울기 — 원점을 지나는 직선, 0.1 MPa 근처.
        assert got.values["initial_modulus"] == pytest.approx(0.1e6, rel=0.05)

    def test_카드는_표와_E_를_낸다(self) -> None:
        got = self.foam.foam_curve([self.member("A", 0.6), self.member("B", 0.6)])
        blocks = self.foam.card_blocks(got.values, got.detail, got.warnings)
        rows = blocks["foam_curve"]["rows"]
        assert len(rows) == self.foam.TABLE_POINTS
        assert rows[0] == {"strain": 0.0, "stress": 0.0}
        assert blocks["elastic"]["values"]["youngs_modulus"] == pytest.approx(0.1e6, rel=0.05)

    @staticmethod
    def deck(rows: list[dict[str, float]]) -> Any:
        from matcore.export import Deck

        return Deck(
            name="PU_FOAM",
            solver_id=21,
            blocks={
                "elastic": {"values": {"youngs_modulus": 0.1e6, "density": 45.0}},
                "foam_curve": {"values": {"sample_count": 2}, "rows": rows},
            },
        )

    def test_LS_DYNA_저밀도_폼으로_내보낸다(self) -> None:
        from matcore.export import render

        got = self.foam.foam_curve([self.member("A", 0.6), self.member("B", 0.6)])
        rows = self.foam.card_blocks(got.values, got.detail, got.warnings)["foam_curve"][
            "rows"
        ]
        text = render("dyna_foam", self.deck(rows)).text
        assert "*MAT_LOW_DENSITY_FOAM" in text and "*DEFINE_CURVE" in text
        card = text.split("*MAT_LOW_DENSITY_FOAM", 1)[1].splitlines()[1:]
        # MID RO E LCID — 곡선 번호가 재료 번호와 같고, RO · E 가 제 칸에.
        first = card[1]
        assert first[0:10].strip() == "21" and first[30:40].strip() == "21"
        assert float(first[10:20]) == pytest.approx(45.0)
        assert float(first[20:30]) == pytest.approx(0.1e6)
        curve = text.split("$                 a1                  o1", 1)[1].splitlines()[1:]
        assert len([line for line in curve if line and not line.startswith("*")]) == len(rows)

    def test_응력이_내려가면_내보내지_않는다(self) -> None:
        """경질 폼의 항복 봉우리 — 눌러 펴서 내보내면 다른 재료다. 파쇄형 폼이 맞다."""
        from matcore.export import ExportError, render

        rows = [
            {"strain": 0.0, "stress": 0.0},
            {"strain": 0.05, "stress": 1.0e6},
            {"strain": 0.1, "stress": 0.8e6},
            {"strain": 0.5, "stress": 1.2e6},
        ]
        with pytest.raises(ExportError, match="내려가는"):
            render("dyna_foam", self.deck(rows))
