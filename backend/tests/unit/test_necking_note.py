"""네킹 경고가 **얼마나 섞였는지** 세는 산술.

## 왜 단위 시험으로 따로 두나

이 계산은 조용히 틀릴 수 있다. 경계를 잘못 잡아도 문장은 그럴듯하게 나오고,
그 문장을 읽은 사람은 「16% 면 그냥 쓰자」 나 「괜찮네」 로 판단한다 — 그리고 그
판단은 덱까지 그대로 간다. API 시험은 **문장이 붙는지**를 보고, 여기서는
**숫자가 맞는지**를 본다.

## 무는 것 넷

    공칭 → 진소성으로 옮긴다      후보 단계는 공칭으로 재고 표는 진소성이다
    경계는 **가장 이른** 후보     평균 곡선은 한 시편이 네킹한 순간 이미 오염된다
    탄성계수는 잰 값에서 읽는다    옵션은 `@youngs_modulus` 같은 참조일 수 있다
    못 세면 못 셌다고 말한다      숫자가 없는 이유가 없으면 「괜찮아서」 로 읽힌다
"""

from __future__ import annotations

import math
from types import SimpleNamespace
from typing import Any

from app.modules.fitting.routes import _necking_plastic_strain, _uncut_necking


def _member(
    name: str,
    *,
    strain: float | None = 0.156444,
    stress: float | None = 481.3e6,
    modulus: float | None = 205e9,
    policy: str | None = None,
    option_modulus: Any = "@youngs_modulus",
) -> Any:
    """시편 하나를 흉내낸다. `policy` 를 주면 「자른 것」 이 된다."""
    scalars: list[dict[str, Any]] = []
    if strain is not None:
        scalars.append({"key": "necking_candidate_strain", "value": strain})
    if stress is not None:
        scalars.append({"key": "necking_candidate_stress", "value": stress})
    if modulus is not None:
        scalars.append({"key": "youngs_modulus", "value": modulus})
    options: dict[str, Any] = {"youngs_modulus": option_modulus}
    if policy:
        options["necking_policy"] = policy
    return SimpleNamespace(
        run=SimpleNamespace(record_name=name),
        result=SimpleNamespace(
            steps_snapshot=[{"plugin": "tensile.true_plastic", "options": options}],
            scalars=scalars,
        ),
    )


def _group(*members: Any) -> Any:
    return SimpleNamespace(members=list(members))


#: 소성변형률 0 ~ 0.17 을 200점으로. 실제 카드 표와 같은 모양이다.
TABLE = [index * 0.17 / 199 for index in range(200)]


class Test공칭을_진소성으로:
    def test_변환식이_처리_단계와_같다(self) -> None:
        """**두 벌로 두면 언젠가 서로 다른 경계를 말한다.**

        `tensile.true_plastic` 이 쓰는 식 그대로다:
        `ln(1+ε) - σ(1+ε)/E`.
        """
        got = _necking_plastic_strain(_member("하나"))
        assert got is not None
        expected = math.log1p(0.156444) - (481.3e6 * 1.156444) / 205e9
        assert abs(got - expected) < 1e-12

    def test_옵션이_참조면_잰_값을_쓴다(self) -> None:
        """실측(2026-09-10): 옵션이 `@youngs_modulus` 라 float 변환이 터졌고,
        그 바람에 경계를 못 세고 「단계가 없다」 고 답했다."""
        assert _necking_plastic_strain(_member("하나")) is not None

    def test_옵션에_숫자가_있으면_그것도_쓴다(self) -> None:
        """잰 값이 없어도 사람이 직접 넣은 탄성계수가 있으면 셀 수 있다."""
        got = _necking_plastic_strain(_member("하나", modulus=None, option_modulus=205e9))
        assert got is not None

    def test_후보가_없으면_None(self) -> None:
        assert _necking_plastic_strain(_member("하나", strain=None)) is None
        assert _necking_plastic_strain(_member("하나", stress=None)) is None

    def test_탄성계수가_없으면_None(self) -> None:
        assert (
            _necking_plastic_strain(_member("하나", modulus=None, option_modulus=None)) is None
        )

    def test_말이_안_되는_값은_None(self) -> None:
        """0 으로 나누지 않는다. 여기서 안 막으면 경고가 통째로 터진다."""
        assert _necking_plastic_strain(_member("하나", modulus=0.0)) is None
        assert _necking_plastic_strain(_member("하나", strain=-1.5)) is None


class Test얼마나_섞였나:
    def test_경계는_가장_이른_후보다(self) -> None:
        """**대표 곡선은 평균이다.**

        한 시편이 0.14 에서 네킹했고 다른 시편이 0.16 이면, 0.14 를 넘는 구간의
        평균에는 이미 네킹 뒤 자료가 섞여 있다. 늦은 쪽을 경계로 잡으면 그 사이
        구간이 「깨끗하다」 고 잘못 말하게 된다.
        """
        early = _member("이른", strain=0.10)
        late = _member("늦은", strain=0.16)
        note = _uncut_necking(_group(early, late), TABLE)[0]

        boundary = _necking_plastic_strain(early)
        assert boundary is not None
        assert f"{boundary:.4g}" in note, note
        # 늦은 쪽 경계는 안 쓴다.
        later = _necking_plastic_strain(late)
        assert later is not None
        assert f"{later:.4g}" not in note, note

    def test_센_점_수가_맞는다(self) -> None:
        one = _member("하나")
        boundary = _necking_plastic_strain(one)
        assert boundary is not None
        beyond = sum(1 for value in TABLE if value > boundary)
        assert beyond > 0, "표본이 잘못됐다 — 경계 뒤 점이 있어야 세는 것을 시험한다"

        note = _uncut_necking(_group(one), TABLE)[0]
        assert f"마지막 {beyond}점" in note, note
        assert f"({beyond / len(TABLE):.0%})" in note, note

    def test_경계_뒤가_없으면_없다고_말한다(self) -> None:
        """**늘 겁주면 그 문장이 경고로 안 읽힌다.** 표가 경계 앞에서 끝나면
        섞인 것이 없고, 그때는 그렇게 말한다."""
        note = _uncut_necking(_group(_member("하나")), [0.0, 0.01, 0.02])[0]
        assert "네킹 뒤 점은 없습니다" in note, note
        assert "마지막" not in note, note

    def test_후보를_안_쟀으면_못_센다고_말한다(self) -> None:
        """숫자가 없는 이유를 적는다 — 안 적으면 「괜찮아서 안 적었나」 로 읽힌다."""
        note = _uncut_necking(_group(_member("하나", strain=None, stress=None)), TABLE)[0]
        assert "세지 못했습니다" in note, note
        assert "'네킹 후보' 단계가 없어" in note, note

    def test_자른_곡선에는_아무_말도_안_한다(self) -> None:
        assert _uncut_necking(_group(_member("하나", policy="manual_index")), TABLE) == []

    def test_섞여_있으면_안_자른_것만_센다(self) -> None:
        """한 건만 안 잘랐어도 표는 오염된다 — 자른 것을 세면 건수가 부풀려진다."""
        note = _uncut_necking(
            _group(_member("자름", policy="manual_index"), _member("안 자름")), TABLE
        )[0]
        assert "1건 섞여" in note, note
        assert "자름," not in note, note
