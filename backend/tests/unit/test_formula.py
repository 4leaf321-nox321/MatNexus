"""계산식 평가기 — **조용히 틀리는 자리라 값으로 못 박는다** (ADR 0030 D2).

답을 아는 식이 그대로 나온다      Swift · 항복비 · 진응력
허용 밖은 읽는 단계에서 막는다     속성·첨자·비교·람다·문자열·모르는 함수
모르는 이름은 막는다              오타를 0 으로 채우지 않는다
배열도 숫자도 같은 평가기다       열 단계와 적합식이 같은 길
"""

from __future__ import annotations

import numpy as np
import pytest

from matcore import formula


class Test답을_아는_식:
    def test_Swift_경화식(self) -> None:
        f = formula.parse("K * (e0 + x) ** n")
        assert f.names == ("K", "e0", "x", "n")
        x = np.array([0.0, 0.01, 0.1])
        got = f.evaluate({"K": 700e6, "e0": 0.002, "n": 0.2, "x": x})
        assert got == pytest.approx(700e6 * (0.002 + x) ** 0.2)

    def test_항복비_스칼라(self) -> None:
        f = formula.parse("proof_stress / tensile_strength")
        assert f.evaluate({"proof_stress": 300e6, "tensile_strength": 400e6}) == pytest.approx(
            0.75
        )

    def test_진응력_열(self) -> None:
        f = formula.parse("stress_engineering * (1 + strain_engineering)")
        s = np.array([100e6, 200e6])
        e = np.array([0.01, 0.02])
        assert f.evaluate({"stress_engineering": s, "strain_engineering": e}) == pytest.approx(
            s * (1 + e)
        )

    def test_함수와_상수(self) -> None:
        f = formula.parse("A * (1 - exp(-b * x)) + sqrt(pi) * 0")
        assert f.evaluate({"A": 2.0, "b": 1.0, "x": 0.0}) == pytest.approx(0.0)
        assert f.evaluate({"A": 2.0, "b": 1e9, "x": 1.0}) == pytest.approx(2.0)

    def test_배열과_숫자가_섞여도_모양이_맞는다(self) -> None:
        f = formula.parse("a * x + b")
        got = f.evaluate({"a": 2.0, "x": np.array([1.0, 2.0, 3.0]), "b": 1.0})
        assert got.tolist() == [3.0, 5.0, 7.0]

    def test_where_는_있지만_비교는_안_된다(self) -> None:
        """`where` 는 허용 함수인데 조건을 만들 비교 연산이 없다 — 읽는 단계에서 막힌다.
        조건은 `clip`·`max`·`min` 으로 쓴다."""
        with pytest.raises(formula.FormulaError, match="Compare"):
            formula.parse("where(x > 0, x, 0)")

    def test_clip_은_된다(self) -> None:
        f = formula.parse("clip(x, 0, 1)")
        assert f.evaluate({"x": np.array([-1.0, 0.5, 2.0])}).tolist() == [0.0, 0.5, 1.0]


class Test허용_밖:
    @pytest.mark.parametrize(
        "source",
        [
            "x.__class__",  # 속성
            "x[0]",  # 첨자
            "lambda: 1",  # 람다
            "x > 1",  # 비교
            "'abc'",  # 문자열
            "__import__('os')",  # 모르는 함수
            "x if x else 0",  # 조건식
            "x and 1",  # 논리
            "[1, 2]",  # 목록
            "f(x=1)",  # 이름 붙인 인자
            "x := 1",  # 바인딩
        ],
    )
    def test_읽는_단계에서_막는다(self, source: str) -> None:
        with pytest.raises(formula.FormulaError):
            formula.parse(source)

    def test_모르는_이름은_0_으로_채우지_않는다(self) -> None:
        f = formula.parse("stres * 2")  # 오타
        with pytest.raises(formula.FormulaError, match="stres"):
            f.evaluate({"stress": 1.0})

    def test_빈_식과_긴_식(self) -> None:
        with pytest.raises(formula.FormulaError):
            formula.parse("   ")
        with pytest.raises(formula.FormulaError, match="깁니다"):
            formula.parse("x+" * 600 + "x")

    def test_참거짓과_2차원은_안_받는다(self) -> None:
        f = formula.parse("x")
        with pytest.raises(formula.FormulaError):
            f.evaluate({"x": True})
        with pytest.raises(formula.FormulaError):
            f.evaluate({"x": np.ones((2, 2))})

    def test_0_으로_나누면_예외가_아니라_inf_다(self) -> None:
        """적합기가 경계값을 시험하며 지나가는 자리다 — 예외로 끊으면 적합이 죽는다."""
        f = formula.parse("a / x")
        assert np.isinf(f.evaluate({"a": 1.0, "x": 0.0}))
