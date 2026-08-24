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


class Test소성구간:
    """**경화식은 탄성 구간을 설명하지 않는다.**

    개발 데이터에서 실제로 걸린 결함이다 — 대표 곡선 50점 중 34점이 소성변형률
    0 이었고(`clip_zero` 가 남긴 자국), 그 34점의 응력이 133~341 MPa 로 흩어져
    있었다. 어떤 단조 함수도 그것을 맞출 수 없어 **식이 맞는데도 R² 가 0.42** 로
    나왔다.
    """

    def test_잘린_탄성_구간을_한_점으로_모은다(self) -> None:
        strain = np.array([0.0, 0.0, 0.0, 0.01, 0.02])
        stress = np.array([130e6, 200e6, 341e6, 350e6, 360e6])
        trimmed_strain, trimmed_stress, notes = fitting.plastic_branch(strain, stress)
        assert list(trimmed_strain) == [0.0, 0.01, 0.02]
        # **마지막 0 점이 항복점이다.** 첫 점을 남기면 130 MPa 를 항복강도로 쓴다.
        assert trimmed_stress[0] == pytest.approx(341e6)
        assert any("항복점" in note for note in notes)

    def test_모을_것이_없으면_그대로_둔다(self) -> None:
        strain, stress = voce_curve()
        trimmed_strain, _, notes = fitting.plastic_branch(strain, stress)
        assert len(trimmed_strain) == len(strain)
        assert notes == []

    def test_걷어내면_적합이_실제로_좋아진다(self) -> None:
        """이 시험이 위 결함의 재현이자 회귀 방지다."""
        strain, stress = voce_curve(20)
        # 탄성 구간이 0 으로 잘린 모양을 앞에 붙인다.
        clipped_strain = np.concatenate([np.zeros(30), strain])
        clipped_stress = np.concatenate([np.linspace(130e6, stress[0], 30), stress])

        dirty = fitting.fit("voce", clipped_strain, clipped_stress)
        clean = fitting.fit(
            "voce", *fitting.plastic_branch(clipped_strain, clipped_stress)[:2]
        )
        assert dirty.relative_rmse > 0.05
        assert clean.relative_rmse < 0.01


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


#: 식이 성립하는 자리의 x 와 그럴듯한 파라미터. 경계에 붙지 않은 값으로 고른다.
SAMPLES: dict[str, tuple[np.ndarray, np.ndarray]] = {
    "voce": (np.linspace(0.001, 0.25, 15), np.array([250e6, 200e6, 12.0])),
    "swift": (np.linspace(0.001, 0.25, 15), np.array([800e6, 0.005, 0.18])),
    "hockett_sherby": (
        np.linspace(0.0, 0.25, 15),  # ε=0 을 일부러 넣는다 — 특이점이 거기다
        np.array([250e6, 200e6, 8.0, 0.7]),
    ),
    "neo_hookean": (np.linspace(0.0, 2.0, 15), np.array([0.4e6])),
    "mooney_rivlin": (np.linspace(0.0, 2.0, 15), np.array([0.3e6, 0.1e6])),
    "yeoh": (np.linspace(0.0, 2.0, 15), np.array([0.4e6, -0.02e6, 0.005e6])),
    "ogden_1": (np.linspace(0.0, 2.0, 15), np.array([0.5e6, 2.3])),
}


class Test야코비안:
    """**틀린 미분은 막히지 않는다 — 다른 답에 수렴할 뿐이다.**

    `least_squares` 는 준 야코비안이 식과 맞는지 확인하지 않는다. 부호 하나를
    틀려도 예외 없이 돌아가고, 그럴듯한 파라미터와 그럴듯한 R² 를 낸다. 그래서
    **선언한 식마다 수치 미분과 대조한다.**

    등록된 식을 훑으므로 새 식이 야코비안을 달면 이 시험이 자동으로 덮는다 —
    안 달면 건너뛴다(수치 미분으로 도는 것은 정상이다, ADR 0013).
    """

    def test_해석적_미분이_수치_미분과_맞는다(self) -> None:
        fitting.load_builtin()
        checked = []
        for key, family in sorted(fitting.FAMILIES.items()):
            if family.jacobian is None:
                continue
            assert key in SAMPLES, (
                f"'{key}' 가 야코비안을 선언했는데 대조할 표본이 없습니다. "
                f"`SAMPLES` 에 그 식이 성립하는 x 와 파라미터를 넣으세요."
            )
            x, parameters = SAMPLES[key]
            analytic = np.asarray(family.jacobian(parameters, x), dtype=np.float64)
            assert analytic.shape == (len(x), len(parameters)), (
                f"'{key}' 야코비안의 모양이 (점 수, 파라미터 수) 가 아닙니다: {analytic.shape}"
            )
            assert np.all(np.isfinite(analytic)), f"'{key}' 야코비안에 NaN·inf 가 있습니다."

            # 중앙 차분. 파라미터마다 **제 크기에 비례한** 폭을 쓴다 — Pa(1e8)와
            # 무차원(0.1)에 같은 폭을 쓰면 한쪽은 반올림에 묻힌다.
            for index in range(len(parameters)):
                step = max(abs(float(parameters[index])), 1.0) * 1e-6
                up, down = (
                    parameters.astype(np.float64).copy(),
                    parameters.astype(np.float64).copy(),
                )
                up[index] += step
                down[index] -= step
                numeric = (family.evaluate(up, x) - family.evaluate(down, x)) / (2.0 * step)
                scale = max(float(np.max(np.abs(numeric))), 1e-12)
                assert np.allclose(
                    analytic[:, index], numeric, rtol=1e-4, atol=scale * 1e-6
                ), f"'{key}' 의 {family.parameter_names[index]} 미분이 어긋납니다."
            checked.append(key)

        # 하나도 안 돌고 통과하면 시험이 아니다.
        assert len(checked) >= 7, f"대조한 식이 {len(checked)}개뿐입니다: {checked}"

    def test_없어도_적합은_돈다(self) -> None:
        """**확장은 야코비안 없이 식만 등록할 수 있다**(ADR 0013). 그때는 scipy 가
        차분으로 낸다 — 느릴 뿐 틀리지 않는다."""
        bare = fitting.Family(
            key="_바닐라",
            label="야코비안 없는 식",
            parameter_names=("a", "b"),
            parameter_units=("Pa", "1"),
            evaluate=lambda p, x: p[0] * (1.0 - np.exp(-p[1] * x)),
            guess=lambda x, y: np.asarray([float(np.max(y)), 10.0]),
            bounds=lambda x, y: (
                np.asarray([0.0, 1e-6]),
                np.asarray([float(np.max(y)) * 5.0, 1e4]),
            ),
            describe="시험용",
        )
        assert bare.jacobian is None
        try:
            fitting.register_family(bare)
            strain = np.linspace(0.001, 0.25, 30)
            result = fitting.fit("_바닐라", strain, 300e6 * (1.0 - np.exp(-9.0 * strain)))
            values = {item.name: item.value for item in result.parameters}
            assert values["a"] == pytest.approx(300e6, rel=1e-3)
            assert values["b"] == pytest.approx(9.0, rel=1e-3)
        finally:
            fitting.FAMILIES.pop("_바닐라", None)

    def test_같은_답에_수렴한다(self) -> None:
        """**해석적 미분은 답을 바꾸는 것이 아니라 가는 길을 바꾼다.**

        아는 곡선에서 아는 파라미터가 여전히 되돌아와야 한다 — 안 그러면 미분이
        틀린 것이고, 그때는 그럴듯한 다른 답이 나온다.
        """
        strain, stress = voce_curve()
        result = fitting.fit("voce", strain, stress)
        values = {item.name: item.value for item in result.parameters}
        assert values["sigma_0"] == pytest.approx(SIGMA_0, rel=1e-4)
        assert values["q"] == pytest.approx(Q, rel=1e-4)
        assert values["b"] == pytest.approx(B, rel=1e-4)
