"""묶음 Prony — **시편 여럿에서 계수 한 벌.**

세 방법이 다 있어야 한다는 것이 결론이었다. 그러면 시험은 「돌아간다」 가 아니라
**「세 방법이 서로 다른 것을 하고, 각각 제 조건을 지키는가」** 를 물어야 한다.

정답을 아는 곡선으로 검산한다 — 적합은 "수렴했다" 로 아무것도 증명되지 않는다
(`test_prony.py` 와 같은 판단).
"""

from __future__ import annotations

import numpy as np
import pytest

from matcore import groups
from matcore.groups import prony as group_prony  # noqa: F401  (등록시킨다)
from matcore.prony import PronySeries, PronyTerm, storage_loss

TRUE = PronySeries(
    equilibrium_pa=5.0e6,
    terms=(
        PronyTerm(modulus_pa=2.0e8, relaxation_time_s=1.0e-2),
        PronyTerm(modulus_pa=8.0e8, relaxation_time_s=1.0e0),
        PronyTerm(modulus_pa=3.0e8, relaxation_time_s=1.0e2),
    ),
    normalized_rmse=0.0,
    bic=0.0,
)

FREQUENCY_HZ = np.logspace(-6, 4, 120)
STORAGE_PA, LOSS_PA = storage_loss(TRUE, FREQUENCY_HZ)
_RNG = np.random.default_rng(20260828)


def member(
    label: str, *, scatter: float = 0.0, reference_k: float = 293.15, fitted: bool = False
) -> groups.Member:
    """시편 하나. `scatter` 는 시편 사이의 차이를 흉내낸다."""
    factor = 1.0 + scatter
    storage = STORAGE_PA * factor
    loss = LOSS_PA * factor
    meta: dict[str, object] = {}
    if fitted:
        # 이미 맞춰 둔 계수. 잔차는 흩어짐이 클수록 나쁜 것으로 둔다.
        meta["prony"] = PronySeries(
            equilibrium_pa=TRUE.equilibrium_pa * factor,
            terms=tuple(
                PronyTerm(term.modulus_pa * factor, term.relaxation_time_s)
                for term in TRUE.terms
            ),
            normalized_rmse=abs(scatter),
            bic=0.0,
        )
    return groups.Member(
        label=label,
        columns={"frequency_hz": FREQUENCY_HZ, "storage_pa": storage, "loss_pa": loss},
        values={"reference_temperature_k": reference_k},
        meta=meta,
    )


def run(members: list[groups.Member], **options: object) -> groups.GroupOutcome:
    return groups.run_group("viscoelastic.prony_group", members, options)


class Test묶음이라는_것:
    def test_하나만_주면_막는다(self) -> None:
        """**하나를 「묶었다」 고 부르면** 그 결과가 묶음인지 한 건인지 나중에
        구별할 수 없다."""
        with pytest.raises(groups.GroupError):
            run([member("A")])

    def test_처리_플러그인은_못_부른다(self) -> None:
        """갈래를 안 보면 「묶음」 자리에 아무 계산이나 들어간다."""
        with pytest.raises(groups.GroupError):
            groups.run_group("tensile.strength", [member("A"), member("B")])

    def test_목록에_뜬다(self) -> None:
        """화면이 고를 목록을 적어 두지 않게 한다 — 그게 확장의 요점이다."""
        found = {item.id for item in groups.groupings()}
        assert "viscoelastic.prony_group" in found


class Test기준_온도:
    def test_다르면_막고_무엇이_다른지_말한다(self) -> None:
        """마스터커브는 **기준 온도 하나에서만 유효하다.** 20 °C 것과 30 °C 것을
        겹치면 뜻이 없는 곡선이 나오는데, 그것도 그럴듯하게 생겼다."""
        with pytest.raises(groups.GroupError) as caught:
            run([member("A", reference_k=293.15), member("B", reference_k=303.15)])
        assert "기준 온도" in str(caught.value)

    def test_표기_반올림_정도는_넘어간다(self) -> None:
        """0.1 K 차이로 막으면 장비 표기만으로 못 묶는다."""
        outcome = run([member("A", reference_k=293.15), member("B", reference_k=293.25)])
        assert outcome.values["reference_temperature_k"] == pytest.approx(293.2, abs=0.05)


#: 흩어진 시편 셋. **흩어져 있어야 세 방법이 갈린다** — 똑같으면 어느 방법을
#: 써도 같은 답이 나와서, 셋을 둔 이유를 시험이 못 본다.
MEMBERS = [
    member("A", scatter=0.0, fitted=True),
    member("B", scatter=0.05, fitted=True),
    member("C", scatter=-0.05, fitted=True),
]


def shaped(label: str, *, amplitude: float, tau_factor: float, rmse: float) -> groups.Member:
    """**모양이 다른** 시편. `member` 는 진폭만 바꾸지만 이쪽은 완화 시간도 옮긴다.

    실제 시편은 완화 시간 분포가 서로 다르고, **거기서 세 방법이 갈린다** — 배율만
    다르면 pooled 와 averaged 가 수학적으로 같은 답을 낸다.
    """
    series = PronySeries(
        equilibrium_pa=TRUE.equilibrium_pa * amplitude,
        terms=tuple(
            PronyTerm(term.modulus_pa * amplitude, term.relaxation_time_s * tau_factor)
            for term in TRUE.terms
        ),
        normalized_rmse=rmse,
        bic=0.0,
    )
    storage, loss = storage_loss(series, FREQUENCY_HZ)
    return groups.Member(
        label=label,
        columns={"frequency_hz": FREQUENCY_HZ, "storage_pa": storage, "loss_pa": loss},
        values={"reference_temperature_k": 293.15},
        meta={"prony": series},
    )


#: A 가 잔차 0 이라 대표가 되고, 나머지는 진폭과 완화 시간이 함께 흩어진다.
SHAPED = [
    shaped("A", amplitude=1.0, tau_factor=1.0, rmse=0.0),
    shaped("B", amplitude=1.05, tau_factor=3.0, rmse=0.05),
    shaped("C", amplitude=1.20, tau_factor=0.3, rmse=0.10),
]


class Test세_방법:
    def test_pooled_는_전부_쓴다(self) -> None:
        outcome = run(MEMBERS, method="pooled")
        assert outcome.detail["method"] == "pooled"
        assert outcome.used == ["A", "B", "C"]
        assert outcome.values["equilibrium_pa"] == pytest.approx(TRUE.equilibrium_pa, rel=0.3)

    def test_averaged_는_τ_가_모두_같다(self) -> None:
        """**이것이 평균의 전제다.** τ 가 시편마다 다르면 계수를 더한다는 말
        자체가 성립하지 않는다."""
        outcome = run(MEMBERS, method="averaged", terms=3)
        taus = [term["relaxation_time_s"] for term in outcome.detail["terms"]]
        assert len(taus) == 3
        assert taus == sorted(taus)

    def test_averaged_는_잔차가_무엇인지_말한다(self) -> None:
        """시편별 적합의 잔차이지 **평균 계수 자체의 잔차가 아니다.** 같은 칸에
        담으면 「평균이 잘 맞는다」 로 읽힌다."""
        outcome = run(MEMBERS, method="averaged", terms=3)
        assert any("평균 계수 자체의 잔차가 아닙니다" in said for said in outcome.warnings)

    def test_representative_는_하나만_쓴다(self) -> None:
        outcome = run(MEMBERS, method="representative")
        assert len(outcome.used) == 1

    def test_representative_는_고른_이유를_남긴다(self) -> None:
        """「아무거나 첫째」 로 두면 파일 순서가 물성을 정한다."""
        outcome = run(MEMBERS, method="representative")
        # 흩어짐이 0 인 A 가 잔차가 가장 작다.
        assert outcome.used == ["A"]
        assert any("잔차가 가장 작은" in said for said in outcome.warnings)

    def test_representative_는_지목할_수_있다(self) -> None:
        outcome = run(MEMBERS, method="representative", representative="B")
        assert outcome.used == ["B"]

    def test_세_방법이_서로_다른_답을_낸다(self) -> None:
        """**같은 답이 나오면 셋을 둘 이유가 없다.**

        ## 진폭만 다른 시편으로는 갈리지 않는다

        `MEMBERS` 는 같은 곡선을 배율만 바꾼 것이다(τ 가 같다). 그러면

            averaged      계수의 평균 = 평균 진폭
            pooled        같은 모양을 모아 맞추므로 역시 평균 진폭

        **둘이 수학적으로 같아진다.** 게다가 `MEMBERS` 는 대칭이라(0, +0.05, -0.05)
        평균이 가운데 시편과도 같아져 `representative` 까지 붙는다. 이 시험은 그
        상태에서 부동소수 마지막 자리(4999999.999999999 vs 5000000.0)로만 갈려
        **우연히** 통과하고 있었고, CI 에서 그 자리가 붙자 빨개졌다(2026-08-29).

        ## 실제로 갈리는 것은 **모양이 다를 때**다

        시편마다 완화 시간 분포가 다르다. 그때 공통 τ 격자에 맞추는 방식이 셋이
        서로 다른 답을 낸다 — 그것이 셋을 둔 이유다. 여기서는 τ 를 흩어 준다.

        ## 「다르다」 는 자릿수가 아니라 크기로 본다

        `set()` 으로 세면 1 ULP 차이도 「다른 답」 이 된다. 사람이 보는 뜻은 그것이
        아니므로 **상대 차이**로 잰다.
        """
        answers = {
            method: run(SHAPED, method=method, terms=3).values["equilibrium_pa"]
            for method in ("pooled", "averaged", "representative")
        }
        values = list(answers.values())
        for one, other in ((0, 1), (0, 2), (1, 2)):
            gap = abs(values[one] - values[other]) / max(abs(values[one]), abs(values[other]))
            assert gap > 0.05, f"두 방법이 사실상 같은 답을 낸다: {answers}"


class Test막는_자리:
    def test_모르는_방법은_거절한다(self) -> None:
        with pytest.raises(groups.GroupError):
            run([member("A"), member("B")], method="mean")

    def test_맞춰_둔_것이_없으면_대표를_못_고른다(self) -> None:
        with pytest.raises(groups.GroupError) as caught:
            run([member("A"), member("B")], method="representative")
        assert "먼저 맞추세요" in str(caught.value)

    def test_곡선이_없으면_무엇이_없는지_말한다(self) -> None:
        empty = groups.Member(label="A", values={"reference_temperature_k": 293.15})
        with pytest.raises(groups.GroupError) as caught:
            run([empty, member("B")], method="pooled")
        assert "A" in str(caught.value)

    def test_기준_온도를_모르면_먼저_만들라고_한다(self) -> None:
        naked = groups.Member(
            label="A",
            columns={
                "frequency_hz": FREQUENCY_HZ,
                "storage_pa": STORAGE_PA,
                "loss_pa": LOSS_PA,
            },
        )
        with pytest.raises(groups.GroupError) as caught:
            run([naked, member("B")])
        assert "마스터커브를 먼저" in str(caught.value)
