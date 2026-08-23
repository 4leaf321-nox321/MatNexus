"""유동곡선 외삽 — **시험이 답한 범위와 해석이 쓰는 범위 사이의 구멍.**

인장시험은 네킹까지만 준다(강판이면 진소성변형률 0.1~0.25). 충돌 해석은 0.5~1.5,
성형은 0.3~1.0 을 쓴다. 그 구멍을 안 채우면 솔버가 자기 기본값으로 채우고 — 대개
마지막 응력을 붙들고 간다 — **그것도 물리적 주장이다.** 금속은 계속 경화하므로 그
구간에서 하중을 낮게 계산한다.

여기서 지키는 것은 넷이다.

    측정점을 안 지운다          시험이 답한 것과 식이 답한 것을 섞지 않는다
    이음매가 벌어지면 짚는다     그 식이 곡선의 끝을 못 따라간 것이다
    외삽 구간의 연화를 짚는다    측정이 아니라 식이 지어낸 모양이다
    한계는 받는다, 안 정한다     기본값을 두면 그 값이 곧 결정이 된다
"""

from __future__ import annotations

import numpy as np
import pytest

from matcore import fitting


def measured(
    family: str = "voce",
    parameters: tuple[float, ...] = (300e6, 250e6, 12.0),
    top: float = 0.20,
    points: int = 40,
) -> tuple[np.ndarray, np.ndarray]:
    """네킹에서 끝나는 측정 곡선. 답을 아는 식으로 만든다."""
    strain = np.linspace(0.0, top, points)
    stress = fitting.FAMILIES[family].evaluate(
        np.asarray(parameters, dtype=np.float64), strain
    )
    return strain, np.asarray(stress, dtype=np.float64)


class Test접선:
    """**외삽이 물리적으로 말이 되는지 보는 근거다.**"""

    @pytest.mark.parametrize(
        ("family", "parameters"),
        [
            ("voce", [300e6, 250e6, 12.0]),
            ("swift", [700e6, 0.005, 0.2]),
            ("hockett_sherby", [300e6, 250e6, 12.0, 0.8]),
        ],
    )
    def test_해석적_접선이_수치_미분과_맞다(
        self, family: str, parameters: list[float]
    ) -> None:
        spec = fitting.FAMILIES[family]
        values = np.asarray(parameters, dtype=np.float64)
        grid = np.asarray([0.05, 0.2, 0.5, 1.0])
        step = 1e-7
        numeric = (spec.evaluate(values, grid + step) - spec.evaluate(values, grid - step)) / (
            2 * step
        )
        analytic = spec.tangent(values, grid)
        assert np.max(np.abs(analytic - numeric) / np.abs(numeric)) < 1e-5

    def test_Hockett_Sherby_는_원점에서_무한대다(self) -> None:
        """**진짜 +∞ 극한이다.** 유한한 큰 수로 바꿔 주면 "여기서 기울기가 아주
        크다" 와 "여기서 정의되지 않는다" 를 구별할 수 없게 된다."""
        spec = fitting.FAMILIES["hockett_sherby"]
        got = spec.tangent(np.asarray([300e6, 250e6, 12.0, 0.6]), np.asarray([0.0]))
        assert np.isinf(got[0])

    def test_포화형과_멱함수형이_다르게_간다(self) -> None:
        """Voce 는 접선이 0 으로 수렴하고 Swift 는 안 그런다 — **외삽에서 갈리는
        이유가 이것이다.**"""
        far = np.asarray([2.0])
        voce = fitting.FAMILIES["voce"].tangent(np.asarray([300e6, 250e6, 12.0]), far)[0]
        swift = fitting.FAMILIES["swift"].tangent(np.asarray([700e6, 0.005, 0.2]), far)[0]
        assert voce < 1e3
        assert swift > 1e7


class Test외삽:
    def test_측정점을_지우지_않는다(self) -> None:
        """시험이 답한 것과 식이 답한 것을 섞지 않는다."""
        strain, stress = measured()
        got = fitting.fit("voce", strain, stress)
        extended = fitting.extend_table(got, strain, stress, to=1.0, points=10)

        assert len(extended.points) == len(strain) + 10
        assert extended.added == 10
        assert extended.points[: len(strain)] == tuple(
            (float(x), float(y)) for x, y in zip(strain, stress, strict=True)
        )
        assert extended.measured_max == pytest.approx(0.20)
        assert extended.extrapolated_to == pytest.approx(1.0)

    def test_늘린_구간이_식을_따라간다(self) -> None:
        strain, stress = measured()
        got = fitting.fit("voce", strain, stress)
        extended = fitting.extend_table(got, strain, stress, to=1.0, points=10)
        # Voce 는 포화한다 — σ0 + Q = 550 MPa.
        assert extended.points[-1][1] == pytest.approx(550e6, rel=1e-3)

    def test_식이_다르면_외삽이_크게_갈린다(self) -> None:
        """**적합 구간에서는 거의 같은데 1.0 에서 갈린다.** 어느 식이 맞는지
        데이터가 정하지 않는 이유가 이것이다(ADR 0009)."""
        strain, stress = measured()
        ends = {}
        for family in ("voce", "swift"):
            got = fitting.fit(family, strain, stress)
            extended = fitting.extend_table(got, strain, stress, to=1.0, points=10)
            ends[family] = extended.points[-1][1]
        assert ends["swift"] > ends["voce"] * 1.2

    def test_한계가_측정_끝_이하면_거절한다(self) -> None:
        strain, stress = measured()
        got = fitting.fit("voce", strain, stress)
        with pytest.raises(fitting.FittingError, match="늘릴 구간이 없습니다"):
            fitting.extend_table(got, strain, stress, to=0.1)

    def test_늘렸다는_사실을_늘_적는다(self) -> None:
        """**덱만 받은 사람이 알아야 한다.**"""
        strain, stress = measured()
        got = fitting.fit("voce", strain, stress)
        extended = fitting.extend_table(got, strain, stress, to=1.0, points=10)
        assert any("검증되지 않았습니다" in note for note in extended.notes)


class Test경고:
    def test_이음매가_벌어지면_짚는다(self) -> None:
        """그 식이 곡선의 끝을 못 따라간 것이다 — 그 상태로 늘리면 안 된다."""
        # 포화하는 곡선에 멱함수형을 억지로 맞춘다.
        strain, stress = measured("voce", (300e6, 250e6, 40.0))
        got = fitting.fit("swift", strain, stress)
        extended = fitting.extend_table(got, strain, stress, to=1.0, points=10)
        assert extended.junction_gap > 0.02
        assert any("벌어집니다" in note for note in extended.notes)

    def test_잘_맞는_식에는_안_짚는다(self) -> None:
        strain, stress = measured()
        got = fitting.fit("voce", strain, stress)
        extended = fitting.extend_table(got, strain, stress, to=1.0, points=10)
        assert extended.junction_gap < 1e-6
        assert not any("벌어집니다" in note for note in extended.notes)

    def test_외삽_구간이_연화하면_짚는다(self) -> None:
        """**측정 구간이 아니라 식이 지어낸 모양이다.** 해석이 발산한다."""

        def softening(parameters: np.ndarray, strain: np.ndarray) -> np.ndarray:
            # 늘어나다 꺾여 내려가는 식. 적합 구간에서는 멀쩡하다.
            (peak,) = parameters
            return np.asarray(peak * (1.0 - (strain - 0.3) ** 2), dtype=np.float64)

        saved = fitting.FAMILIES.copy()
        try:
            fitting.register_family(
                fitting.Family(
                    key="pretend_softening",
                    label="지어낸 연화식",
                    parameter_names=("peak",),
                    parameter_units=("Pa",),
                    evaluate=softening,
                    guess=lambda x, y: np.asarray([float(np.max(y))]),
                    bounds=lambda x, y: (
                        np.asarray([1.0]),
                        np.asarray([float(np.max(y)) * 10.0]),
                    ),
                    describe="시험용",
                    tangent=lambda p, e: np.asarray(-2.0 * p[0] * (e - 0.3), dtype=np.float64),
                    applies_to=fitting.METALLIC,
                )
            )
            strain, stress = measured()
            got = fitting.fit("pretend_softening", strain, stress)
            extended = fitting.extend_table(got, strain, stress, to=1.0, points=10)
            assert any("접선이 음수" in note for note in extended.notes)
            assert any("응력이 떨어집니다" in note for note in extended.notes)
        finally:
            fitting.FAMILIES.clear()
            fitting.FAMILIES.update(saved)
