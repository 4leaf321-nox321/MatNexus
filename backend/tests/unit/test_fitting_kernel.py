"""경화식 적합 — **답을 아는 곡선으로 검산한다.**

적합 코드는 "돌아간다" 로 아무것도 증명되지 않는다. 경계에 붙은 파라미터도
숫자를 내고, 엉뚱한 극소에 수렴한 결과도 곡선을 그린다. 둘 다 그럴듯해 보인다.

그래서 **파라미터를 아는 곡선을 만들어 그 값이 되돌아오는지** 본다. 그리고
태도를 시험한다 — 적합 구간 밖을 말하지 않는지, 경계에 붙었을 때 그 사실을
남기는지. 그쪽이 이 모듈의 값이다.
"""

from __future__ import annotations

import numpy as np
import pytest

from matcore import fitting

#: 답을 아는 Voce 곡선.
SIGMA_0 = 250e6
Q = 200e6
B = 12.0


def voce_curve(points: int = 40) -> tuple[np.ndarray, np.ndarray]:
    strain = np.linspace(0.001, 0.25, points)
    stress = SIGMA_0 + Q * (1.0 - np.exp(-B * strain))
    return strain, stress


class Test파라미터복원:
    def test_아는_값이_되돌아온다(self) -> None:
        strain, stress = voce_curve()
        result = fitting.fit("voce", strain, stress)
        values = {item.name: item.value for item in result.parameters}
        assert values["sigma_0"] == pytest.approx(SIGMA_0, rel=1e-4)
        assert values["q"] == pytest.approx(Q, rel=1e-4)
        assert values["b"] == pytest.approx(B, rel=1e-4)
        assert result.r_squared == pytest.approx(1.0, abs=1e-9)

    def test_경계와_초기값을_남긴다(self) -> None:
        """**비선형 적합은 경계와 초기값에 따라 다른 답에 수렴한다.**

        남기지 않으면 같은 데이터로 다시 돌려도 재현이 안 되고, 그러면 그 값은
        근거가 아니라 우연이다.
        """
        strain, stress = voce_curve()
        result = fitting.fit("voce", strain, stress)
        for item in result.parameters:
            assert item.lower <= item.value <= item.upper
            assert item.lower <= item.initial <= item.upper


class Test적합도:
    def test_안_맞는_식은_상대RMSE로_드러난다(self) -> None:
        """Swift 는 포화하지 않으므로 Voce 데이터에 잘 안 맞는다.

        **절대 RMSE 가 아니라 상대값을 보는 이유:** 재료마다 응력 크기가 달라
        절대값으로는 식끼리 견줄 수 없다.
        """
        strain, stress = voce_curve()
        ranked = fitting.compare(strain, stress)
        assert ranked[0].family in {"voce", "hockett_sherby"}
        swift = next(item for item in ranked if item.family == "swift")
        assert swift.relative_rmse > ranked[0].relative_rmse

    def test_크게_어긋나면_말해_준다(self) -> None:
        # 직선 데이터에 포화형을 맞추면 잘 안 맞는다. 그 사실이 근거에 남아야 한다.
        strain = np.linspace(0.01, 0.5, 30)
        stress = 100e6 + 800e6 * strain
        result = fitting.fit("voce", strain, stress)
        if result.relative_rmse > 0.05:
            assert any("안 맞을 수 있습니다" in note for note in result.notes)

    def test_최대_잔차도_낸다(self) -> None:
        # 평균이 좋아도 한 점이 크게 틀릴 수 있다.
        strain, stress = voce_curve()
        result = fitting.fit("voce", strain, stress)
        assert result.max_residual >= 0


class Test태도:
    """**적합 구간 밖을 말하지 않는다.**"""

    def test_구간을_결과에_박아_둔다(self) -> None:
        strain, stress = voce_curve()
        result = fitting.fit("voce", strain, stress)
        assert result.strain_min == pytest.approx(0.001)
        assert result.strain_max == pytest.approx(0.25)
        assert any("적합 구간 밖에서 검증되지 않았습니다" in note for note in result.notes)

    def test_식마다_구간_밖이_전혀_다르다(self) -> None:
        """이 시험이 위 경고의 근거다.

        같은 데이터에 맞춘 두 식이 적합 구간에서는 거의 같은데, 그 밖에서는
        갈린다 — Swift 는 계속 올라가고 Voce 는 포화한다. **어느 쪽이 맞는지는
        데이터에 없다.**
        """
        strain, stress = voce_curve()
        voce = fitting.fit("voce", strain, stress)
        swift = fitting.fit("swift", strain, stress)

        inside = np.array([0.2])
        assert voce.evaluate(inside)[0] == pytest.approx(swift.evaluate(inside)[0], rel=0.05)

        far = np.array([1.5])
        assert voce.evaluate(far)[0] != pytest.approx(swift.evaluate(far)[0], rel=0.05)

    def test_점이_모자라면_보간이라고_말한다(self) -> None:
        # 파라미터 3개를 3점으로 맞추면 잔차가 0 이 나온다. 그것은 적합이 아니다.
        strain = np.linspace(0.01, 0.1, 3)
        with pytest.raises(fitting.FittingError, match="보간"):
            fitting.fit("voce", strain, 250e6 + 100e6 * strain)

    def test_모르는_식은_있는_것을_알려_준다(self) -> None:
        strain, stress = voce_curve()
        with pytest.raises(fitting.FittingError, match="있는 것"):
            fitting.fit("made_up", strain, stress)


class Test견주기:
    def test_하나가_안_되도_나머지를_버리지_않는다(self) -> None:
        strain, stress = voce_curve()
        results = fitting.compare(strain, stress, families=("voce", "made_up", "swift"))
        assert {item.family for item in results} == {"voce", "swift"}

    def test_상대RMSE_순으로_준다(self) -> None:
        # **어느 것이 맞는지 고르지는 않는다.** 순서만 주고 선택은 사람이 한다 —
        # 큰 변형까지 쓸 것인지가 선택을 바꾸고, 그것은 해석하는 사람이 안다.
        strain, stress = voce_curve()
        results = fitting.compare(strain, stress)
        assert [item.relative_rmse for item in results] == sorted(
            item.relative_rmse for item in results
        )
