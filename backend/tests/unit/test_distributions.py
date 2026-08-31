"""스칼라 분포 적합 — **답을 아는 표본으로 검산한다.**

적합 코드는 "돌아간다" 로 아무것도 증명되지 않는다. 틀린 파라미터도 숫자를 내고,
아무것도 안 맞을 때도 AICc 1등은 나온다. 그래서 **참 분포에서 뽑은 표본**을
만들어 그 분포가 1등으로 돌아오는지 본다.

그리고 태도를 시험한다 — 모자란 것과 실패한 것을 가르는지, 없는 값과 못 쓰는
값을 가르는지, 구별되지 않을 때 구별되지 않는다고 말하는지. 그쪽이 이 모듈의
값이다.
"""

from __future__ import annotations

from itertools import pairwise
from pathlib import Path

import numpy as np
import pytest

from matcore import distributions

#: 시험을 빠르게 돌리려고 낮춘다. 부트스트랩 p 의 **정밀도**만 떨어지고
#: 통계량·파라미터는 그대로다. 기본값(999)은 API 가 쓴다.
ROUNDS = 149

#: p 값 자체를 보는 시험만 높인다. 149 로는 0.05 근처가 흔들린다.
BOOTSTRAP_FOR_P = 499


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


BENCHMARKS = Path(__file__).resolve().parents[1] / "fixtures" / "reliability_benchmarks.txt"


def benchmark(name: str) -> list[float]:
    """문헌 데이터 하나. 출처는 픽스처 머리글에 있다."""
    values: list[float] = []
    current = None
    for line in BENCHMARKS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("["):
            current = line.strip("[]")
            continue
        if current == name:
            values.extend(float(token) for token in line.split())
    assert values, f"'{name}' 를 픽스처에서 못 찾았습니다."
    return values


class Test문헌_벤치마크:
    """**우리가 만든 표본으로는 견주기를 시험할 수 없다.**

    위의 시험들은 전부 우리가 뽑은 표본이다 — 와이블에서 뽑아 와이블이 1등인지
    보는 식이다. 그것은 *계수가 되돌아오는지* 를 보는 시험이지 **후보 중 무엇을
    고를 것인가** 를 보는 시험이 아니다.

    실측으로 확인했다(2026-08-25): `_aicc` 를 `lambda ll, n, k: -ll` 로 바꿔
    **유한표본 보정도 파라미터 벌점도 통째로 지웠는데 시험이 전부 통과했다.**
    와이블 데이터에서는 우도만으로도 와이블이 이기기 때문이다.

    그래서 **우리가 안 만든 데이터**를 쓴다. 초탄성에서 Treloar 로 한 것과 같다
    (v1.57.0). 셋 다 신뢰성 문헌의 표준 예제이고 와이블로 다루는 것이 합의돼
    있다.
    """

    def test_유리섬유에서_와이블이_이긴다(self) -> None:
        """**유리섬유는 약한 고리가 정한다** — 가장 약한 결함 하나가 끊는 자리를
        정하므로 와이블이 맞는 모양이라는 것이 문헌의 합의다.

        실측(2026-08-25, ΔAICc):

            1.5cm (n=63)   와이블 0.00 · 정규 5.41 · 로그정규 25.60
            15cm  (n=46)   와이블 0.00 · 정규 2.84 · 로그정규 19.81

        **로그정규가 크게 진다** — 이것이 우리가 만든 표본으로는 못 보던 것이다.
        """
        for name, expected_gap in (("glassfiber1_5", 20.0), ("glassfiber15", 15.0)):
            report = distributions.fit_all(benchmark(name), bootstrap=ROUNDS)
            assert report.best == "weibull", name
            lognormal = next(item for item in report.candidates if item.key == "lognormal")
            assert lognormal.delta_aicc is not None
            assert lognormal.delta_aicc > expected_gap, name

    def test_짧은_섬유는_와이블도_안_맞는다고_말한다(self) -> None:
        """**1등이라고 맞는다는 뜻이 아니다.**

        1.5cm 섬유에서 와이블이 1등인데 p 값이 0.007 이다 — AICc 는 *후보 중
        어느 것이 나은가* 를 답하고 Anderson-Darling 은 *맞기는 하나* 를 답한다.
        둘이 다른 것을 본다는 것이 여기서 눈에 보인다.

        실제로 Smith·Naylor 가 이 데이터로 **3-파라미터** 와이블을 논한 이유가
        그것이다. 우리는 2-파라미터만 쓰므로 왼쪽 꼬리를 못 따라간다.
        """
        report = distributions.fit_all(benchmark("glassfiber1_5"), bootstrap=BOOTSTRAP_FOR_P)
        winner = next(item for item in report.candidates if item.key == report.best)
        assert winner.p_value is not None
        assert winner.p_value < 0.05

    def test_베어링은_구별되지_않는다고_말한다(self) -> None:
        """**n=23 에서는 로그정규와 와이블이 안 갈린다.**

        문헌은 베어링 수명을 와이블로 다루는데, 우리 결과는 로그정규가 1등이고
        와이블이 ΔAICc 1.13 이다. **그것을 틀렸다고 보지 않는다** — 표본이
        스물셋이고 두 분포가 이 자리에서 거의 같은 모양이기 때문이다.

        중요한 것은 **우리가 그 사실을 말하는가** 다. ΔAICc 2 미만이면 안내에
        "이 데이터로는 구별되지 않습니다" 가 뜬다 — 그 안내가 없으면 사람은
        「로그정규」를 답으로 읽는다.
        """
        report = distributions.fit_all(benchmark("bearings"), bootstrap=ROUNDS)
        weibull_fit = next(item for item in report.candidates if item.key == "weibull")
        assert weibull_fit.delta_aicc is not None
        assert weibull_fit.delta_aicc < 2.0
        assert any("구별되지 않습니다" in note for note in report.notes)

    def test_AICc_를_망가뜨리면_잡힌다(self) -> None:
        """**이 시험 묶음이 존재하는 이유다.**

        우리가 만든 표본으로 하는 시험은 `_aicc` 를 통째로 지워도 전부 통과했다.
        문헌 데이터에서는 그것이 드러나야 한다 — 안 드러나면 이 파일도 장식이다.
        """
        values = benchmark("glassfiber15")
        real = distributions._aicc
        try:
            # 유한표본 보정도 파라미터 벌점도 없앤다.
            distributions._aicc = lambda ll, n, k: -ll  # type: ignore[assignment]
            broken = distributions.fit_all(values, bootstrap=0)
        finally:
            distributions._aicc = real
        sound = distributions.fit_all(values, bootstrap=0)

        # 1등은 그대로일 수 있다. **갈린 정도가 달라지는 것**이 신호다.
        broken_gap = next(i for i in broken.candidates if i.key == "normal").delta_aicc
        sound_gap = next(i for i in sound.candidates if i.key == "normal").delta_aicc
        assert broken_gap is not None and sound_gap is not None
        assert abs(broken_gap - sound_gap) > 0.5


# --- 모자랄 때도 빈손으로 두지 않는다 ---------------------------------------


def test_최소값이_덮는_분위수는_표본이_늘수록_꼬리로_간다() -> None:
    """**작은 표본이 꼬리를 못 본다는 사실을 수로 말한다.**

    「데이터가 모자랍니다」 는 막다른 길이고, 「최소값으로 63% 분위수까지
    말할 수 있습니다」 는 판단할 거리다.
    """
    assert distributions.covered_quantile(3) == pytest.approx(0.6316, abs=1e-4)
    assert distributions.covered_quantile(20) == pytest.approx(0.1391, abs=1e-4)
    # 표본이 늘면 단조로 내려간다 — 최소값이 점점 더 아래 분위수를 덮는다.
    covered = [distributions.covered_quantile(n) for n in range(1, 40)]
    assert all(one is not None for one in covered)
    assert all(a > b for a, b in pairwise([one for one in covered if one is not None]))


def test_표본이_없으면_분위수도_없다() -> None:
    assert distributions.covered_quantile(0) is None


def test_하위_5퍼센트를_분포_없이_말하려면_59개() -> None:
    """**분포를 맞추는 이유가 이 수다.** 59개를 재는 대신 모양을 가정한다."""
    assert distributions.needed_for(0.05, confidence=0.95) == 59
    # 정의를 되짚는다: 그 n 에서 최소값이 덮는 분위수가 0.05 이하여야 한다.
    낮은쪽 = distributions.covered_quantile(59)
    높은쪽 = distributions.covered_quantile(58)
    assert 낮은쪽 is not None and 낮은쪽 <= 0.05
    assert 높은쪽 is not None and 높은쪽 > 0.05


def test_요약은_가정_없이_있는_값만_말한다() -> None:
    summary = distributions.empirical([610.0, 618.0, 625.0])
    assert summary.count == 3
    assert summary.minimum == 610.0
    assert summary.median == 618.0
    assert summary.maximum == 625.0


def test_값이_없어도_자료형은_돌려준다() -> None:
    """**화면이 갈리지 않게.** `None` 이면 쓰는 쪽이 매번 분기한다."""
    summary = distributions.empirical([])
    assert summary.count == 0
    assert summary.minimum is None
    assert summary.needed_for_design == 59


def test_적합이_하나도_못_돌아도_요약과_안내가_남는다() -> None:
    """**막다른 길로 두지 않는다.** 전에는 「표본 모자람」 배지 셋이 전부였다."""
    report = distributions.fit_all([610.0, 618.0, 625.0])
    assert report.best is None
    assert all(item.status == "not_eligible" for item in report.candidates)

    assert report.empirical is not None
    assert report.empirical.count == 3
    assert report.empirical.covered_quantile == pytest.approx(0.6316, abs=1e-4)

    말 = " ".join(report.notes)
    assert "59개" in 말
    assert "63%" in 말


def test_적합이_돌_때도_요약은_함께_온다() -> None:
    """적합한 분위수가 관측값에서 얼마나 떨어졌는지 견줄 자리가 된다."""
    값 = [610.0, 615.0, 618.0, 620.0, 622.0, 625.0, 628.0, 631.0, 634.0, 640.0]
    report = distributions.fit_all(값, bootstrap=19)
    assert report.empirical is not None
    assert report.empirical.count == len(값)
    assert report.empirical.minimum == 610.0
