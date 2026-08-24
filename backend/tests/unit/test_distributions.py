"""스칼라 분포 적합 — **답을 아는 표본으로 검산한다.**

적합 코드는 "돌아간다" 로 아무것도 증명되지 않는다. 틀린 파라미터도 숫자를 내고,
아무것도 안 맞을 때도 AICc 1등은 나온다. 그래서 **참 분포에서 뽑은 표본**을
만들어 그 분포가 1등으로 돌아오는지 본다.

그리고 태도를 시험한다 — 모자란 것과 실패한 것을 가르는지, 없는 값과 못 쓰는
값을 가르는지, 구별되지 않을 때 구별되지 않는다고 말하는지. 그쪽이 이 모듈의
값이다.
"""

from __future__ import annotations

import numpy as np
import pytest

from matcore import distributions

#: 시험을 빠르게 돌리려고 낮춘다. 부트스트랩 p 의 **정밀도**만 떨어지고
#: 통계량·파라미터는 그대로다. 기본값(999)은 API 가 쓴다.
ROUNDS = 149


def weibull(
    count: int, *, shape: float = 9.0, scale: float = 620e6, seed: int = 3
) -> list[float]:
    """참 와이블 표본. 최대응력이 620 MPa 근처인 강판을 흉내낸다."""
    return list(scale * np.random.default_rng(seed).weibull(shape, count))


def normal(count: int, *, mean: float = 620e6, sd: float = 20e6, seed: int = 5) -> list[float]:
    return list(np.random.default_rng(seed).normal(mean, sd, count))


class Test참_분포가_돌아온다:
    def test_와이블_표본에서_와이블이_1등이다(self) -> None:
        report = distributions.fit_all(weibull(60), bootstrap=ROUNDS)
        assert report.best == "weibull"
        winner = next(item for item in report.candidates if item.key == "weibull")
        shape, scale = winner.parameters
        assert shape == pytest.approx(9.0, rel=0.2)
        assert scale == pytest.approx(620e6, rel=0.05)

    def test_정규_표본에서는_1등을_고를_수_없다(self) -> None:
        """**이 시험은 처음에 "정규가 1등이다" 로 썼다가 실측에 맞춰 고쳤다.**

        강판 최대응력의 CV 는 3% 쯤이다. 그 좁은 폭에서 로그정규는 정규와
        **수치적으로 거의 같은 곡선**이고(σ_log 가 작으면 그렇게 된다), 60점으로는
        갈리지 않는다. 실측한 ΔAICc:

            CV  3% n=60    lognormal 0.0   normal 0.61   weibull 13.64
            CV  3% n=200   lognormal 0.0   normal 1.90   weibull 42.44
            CV 15% n=60    lognormal 0.0   normal 1.78   weibull  8.17
            CV 30% n=120   normal    0.0   lognormal 0.06  weibull 1.48

        **n 을 200으로 늘려도 안 갈린다.** 재료 시험의 흩어짐이 좁은 것이 이유라,
        시편을 더 만들어도 답이 안 나온다.

        그러니 여기서 볼 것은 "정규가 이긴다" 가 아니라 **"못 가른다고 말하는가"**
        다. 파라미터는 1등이 무엇이든 제대로 나와야 한다.
        """
        report = distributions.fit_all(normal(60), bootstrap=ROUNDS)
        normal_fit = next(item for item in report.candidates if item.key == "normal")
        mu, sigma = normal_fit.parameters
        assert mu == pytest.approx(620e6, rel=0.02)
        assert sigma == pytest.approx(20e6, rel=0.25)

        # 정규는 1등과 구별되지 않는 자리에 있어야 한다.
        assert normal_fit.delta_aicc is not None and normal_fit.delta_aicc < 2.0
        # 그리고 그 사실을 말해야 한다.
        assert any("구별되지 않습니다" in note for note in report.notes)
        # 와이블은 갈린다 — 무엇이든 못 가르는 것은 아니다.
        weibull_fit = next(item for item in report.candidates if item.key == "weibull")
        assert weibull_fit.delta_aicc is not None and weibull_fit.delta_aicc > 5.0

    def test_아닌_분포는_p_값이_작다(self) -> None:
        """**AICc 만으로는 부족하다.** 상대적이라 전부 안 맞아도 하나는 1등이
        된다. 절대적인 판단은 Anderson-Darling 이 한다."""
        # 로그정규 표본. 정규는 오른쪽 꼬리를 못 따라간다.
        values = list(np.random.default_rng(11).lognormal(np.log(620e6), 0.45, 120))
        report = distributions.fit_all(values, bootstrap=ROUNDS)
        assert report.best == "lognormal"
        loser = next(item for item in report.candidates if item.key == "normal")
        assert loser.p_value is not None and loser.p_value < 0.05


class Test모자란_것과_실패한_것:
    def test_표본이_모자라면_실패가_아니라_대상이_아니다(self) -> None:
        """**한 칸에 넣으면 나중에 못 가른다.** 시편 5개는 적합에 실패한 것이
        아니라 애초에 물을 수 없는 것이다."""
        report = distributions.fit_all(weibull(5), bootstrap=ROUNDS)
        assert report.best is None
        assert {item.status for item in report.candidates} == {"not_eligible"}
        for item in report.candidates:
            assert item.reason is not None
            assert "물음이 성립하지 않습니다" in item.reason
            # 값이 없는 것이지 0 인 것이 아니다.
            assert item.aicc is None and item.p_value is None

    def test_모자란_이유를_안내에도_적는다(self) -> None:
        report = distributions.fit_all(weibull(5), bootstrap=ROUNDS)
        assert any("모자란 것이지 안 맞는 것이 아닙니다" in note for note in report.notes)

    def test_경계_바로_위는_답을_내되_믿지_말라고_한다(self) -> None:
        report = distributions.fit_all(weibull(10), bootstrap=ROUNDS)
        assert report.best is not None
        assert any("가려낼 힘이 없습니다" in note for note in report.notes)

    def test_실패한_후보도_목록에_남는다(self) -> None:
        """**안 뜨면 "안 해 봤다" 로 읽힌다.** 양수만 받는 분포가 음수 섞인
        데이터에서 못 도는 것은 결과이지 부재가 아니다."""
        report = distributions.fit_all([-5.0] * 20 + list(weibull(4)), bootstrap=ROUNDS)
        keys = {item.key for item in report.candidates}
        assert keys == {"normal", "lognormal", "weibull"}
        # 음수를 걷어내면 양수 분포에는 4개만 남는다 — 대상이 아니다.
        for key in ("lognormal", "weibull"):
            item = next(one for one in report.candidates if one.key == key)
            assert item.status == "not_eligible"


class Test관측_상태:
    def test_없는_것과_못_쓰는_것을_가른다(self) -> None:
        values: list[float | None] = [1.0, None, float("nan"), 3.0, float("inf")]
        report = distributions.fit_all(values, bootstrap=0)
        assert [item.status for item in report.observations] == [
            "observed",
            "missing",
            "non_finite",
            "observed",
            "non_finite",
        ]
        assert report.count == 2

    def test_자리를_그대로_돌려준다(self) -> None:
        """**어느 시편이었는지 되짚을 수 있어야 한다.** 조용히 빼면 "왜 9개죠" 를
        답할 수 없다."""
        values: list[float | None] = [1.0, None, 3.0]
        report = distributions.fit_all(values, bootstrap=0)
        assert [item.index for item in report.observations] == [0, 1, 2]

    def test_관측_표는_분포마다_바뀌지_않는다(self) -> None:
        """음수는 정규에서는 정상이고 와이블에서는 정의역 밖이다. 표시가 분포마다
        달라지면 **같은 시편이 표마다 다르게 보인다** — 그건 사유로 말한다."""
        report = distributions.fit_all([-1.0, 2.0, 3.0], bootstrap=0)
        assert [item.status for item in report.observations] == [
            "observed",
            "observed",
            "observed",
        ]


class Test견주기:
    def test_구별되지_않으면_그렇게_말한다(self) -> None:
        """**AICc 차이가 2 미만이면 이 데이터로는 못 가른다.** 그때 1등을 고르는
        것은 데이터가 아니라 사람이다."""
        # 형상이 크면 와이블이 정규에 가까워져 둘이 잘 안 갈린다.
        report = distributions.fit_all(weibull(12, shape=30.0, seed=17), bootstrap=ROUNDS)
        near = [
            item
            for item in report.candidates
            if item.delta_aicc is not None and 0 < item.delta_aicc < 2.0
        ]
        if near:
            assert any("구별되지 않습니다" in note for note in report.notes)

    def test_1등의_델타는_0_이다(self) -> None:
        report = distributions.fit_all(weibull(40), bootstrap=ROUNDS)
        winner = next(item for item in report.candidates if item.key == report.best)
        assert winner.delta_aicc == pytest.approx(0.0)
        # AICc 오름차순으로 나온다.
        scored = [item.aicc for item in report.candidates if item.aicc is not None]
        assert scored == sorted(scored)

    def test_분위수를_함께_준다(self) -> None:
        """**설계가 묻는 것은 파라미터가 아니라 하위 5% 다.**"""
        report = distributions.fit_all(weibull(40), bootstrap=0)
        winner = next(item for item in report.candidates if item.key == report.best)
        assert set(winner.quantiles) == {"p05", "p50", "p95"}
        assert winner.quantiles["p05"] < winner.quantiles["p50"] < winner.quantiles["p95"]


class Test재현:
    def test_같은_seed_는_같은_p_를_낸다(self) -> None:
        """**부트스트랩 p 가 난수에 따라 흔들리면 근거가 못 된다.** 같은 데이터에서
        다른 p 가 나오면 "재현이 안 된다" 가 되고, 그러면 그 숫자를 보고서에
        적을 수 없다."""
        values = weibull(30)
        first = distributions.fit_all(values, bootstrap=ROUNDS)
        second = distributions.fit_all(values, bootstrap=ROUNDS)
        assert [item.p_value for item in first.candidates] == [
            item.p_value for item in second.candidates
        ]

    def test_부트스트랩을_끄면_p_가_없다(self) -> None:
        """0 이면 안 낸다. **0.0 을 넣으면 "확실히 아니다" 로 읽힌다.**"""
        report = distributions.fit_all(weibull(30), bootstrap=0)
        assert all(item.p_value is None for item in report.candidates)
        # 통계량 자체는 그대로 나온다 — 부트스트랩은 p 를 만드는 데만 쓴다.
        assert all(
            item.anderson_darling is not None
            for item in report.candidates
            if item.status == "succeeded"
        )


class Test거절:
    def test_모르는_분포는_있는_것을_알려_준다(self) -> None:
        with pytest.raises(distributions.DistributionError, match="있는 것:"):
            distributions.fit_all(weibull(20), keys=("감마",), bootstrap=0)

    def test_너무_많으면_거절한다(self) -> None:
        with pytest.raises(distributions.DistributionError, match="무거워집니다"):
            distributions.fit_all([1.0] * (distributions.MAX_SAMPLES + 1), bootstrap=0)


class Test레지스트리:
    def test_분포를_더할_수_있다(self) -> None:
        """**곡선이 아닌 입력도 확장이 붙는다**(ADR 0013). `Family` 는 `(x, y)` 를
        받는데 여기는 값 배열 하나다 — 레지스트리를 따로 둔 이유다."""
        distributions.load_builtin()
        added = distributions.Distribution(
            key="_지수",
            label="지수",
            parameter_names=("rate",),
            parameter_labels=("비율",),
            fit=lambda values: np.asarray([1.0 / float(np.mean(values))]),
            logpdf=lambda p, x: np.log(p[0]) - p[0] * x,
            cdf=lambda p, x: 1.0 - np.exp(-p[0] * x),
            ppf=lambda p, q: -np.log(1.0 - q) / p[0],
            sample=lambda p, n, rng: rng.exponential(1.0 / p[0], n),
            describe="시험용",
            positive_only=True,
        )
        try:
            distributions.register(added)
            report = distributions.fit_all(
                list(np.random.default_rng(2).exponential(3.0, 60)),
                keys=("_지수", "normal"),
                bootstrap=ROUNDS,
            )
            assert report.best == "_지수"
        finally:
            distributions.DISTRIBUTIONS.pop("_지수", None)
