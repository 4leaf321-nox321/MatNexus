"""Johnson-Cook 준정적 항을 등록한다 — 확장 폴더 하나로.

계산은 `equation.py`, 이 식이 나가는 솔버 카드는 `card.py` 에 있다. 중심 코드는
한 줄도 안 고친다(`ghosh_hardening` 과 같은 모양).

이름에 `_static` 을 붙인 이유는 그 파일 머리말에 있다 — **속도항·온도항이 빠진
것을 이름이 말하게** 한다.
"""

from __future__ import annotations

from matcore import fitting

from . import card, equation  # noqa: F401  (card 는 import 만으로 렌더러를 등록한다)

fitting.register_family(
    fitting.Family(
        key="johnson_cook_static",
        label="Johnson-Cook (준정적 항)",
        parameter_names=("a", "b", "n"),
        parameter_units=("Pa", "Pa", "1"),
        evaluate=equation.evaluate,
        guess=equation.guess,
        bounds=equation.bounds,
        tangent=equation.tangent,
        describe=(
            "sigma = A + B·eps^n — Johnson-Cook 의 첫 괄호만. "
            "속도항·온도항은 1 로 둔 값이라 이 셋만으로는 속도·온도 의존을 말하지 "
            "못한다. A 는 항복강도로 바로 읽힌다. 속도항 C 는 「속도별 소성 곡선」 "
            "묶음이 따로 낸다 — 둘이 다 있어야 완전한 Johnson-Cook 카드가 된다."
        ),
        applies_to=fitting.METALLIC,
    )
)
