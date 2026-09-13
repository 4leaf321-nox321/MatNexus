"""유변 — 점도-전단율 곡선에 Cross·Carreau 를 맞춘다. **확장 폴더 하나로.**

레오미터 유동 시험(`rheometer_flow`, TRIOS 프로파일 `ta_hr_flow`)이 채택한 결과의
`shear_rate`·`viscosity` 열이 축이다. 식은 `equations.py`, 카드 블록과 Abaqus
`*VISCOSITY` 덱은 `card.py`. 중심 코드에 이 폴더의 이름은 없다.

점도는 0.1~1000 1/s 에서 수십 배 내려가므로 **로그 잔차**로 맞춘다
(`Family.residual="log"`) — 선형이면 큰 점도 몇 점이 적합을 지배한다.
"""

from __future__ import annotations

from matcore import fitting

from . import card, equations  # noqa: F401  (card 는 import 만으로 블록·렌더러를 등록한다)

#: 유변 식이 뜻을 갖는 재료군. 용융 고분자·잉크·슬러리 — 재료군 축은 열려 있어 부서가
#: 더 만들 수 있고, 아무 식도 그 군을 선언하지 않았으면 전부 보인다(`families_for`).
FLUIDS = ("Polymer", "Plastic", "Fluid", "Adhesive", "Ink", "Slurry")

_COMMON = {
    "x_label": "전단율",
    "y_label": "점도",
    "x_column": "shear_rate",
    "y_column": "viscosity",
    "block": "rheology",
    "applies_to": FLUIDS,
    "prepare": equations.prepare,
    "extras": equations.zero_shear,
    "residual": "log",
}

fitting.register_family(
    fitting.Family(
        key="cross",
        label="Cross",
        parameter_names=("eta_0", "eta_inf", "lambda", "m"),
        parameter_units=("Pa.s", "Pa.s", "s", "1"),
        evaluate=equations.cross_evaluate,
        guess=equations.cross_guess,
        bounds=equations.cross_bounds,
        describe=(
            "eta = eta_inf + (eta_0 - eta_inf) / (1 + (lambda*rate)^m) — 영전단 점도 "
            "eta_0 에서 1/lambda 근처에서 꺾여 기울기 -m 으로 박화한다. Abaqus *VISCOSITY, "
            "DEFINITION=CROSS 는 지수를 1-n 으로 받는다(n = 1 - m)."
        ),
        **_COMMON,
    )
)

fitting.register_family(
    fitting.Family(
        key="carreau",
        label="Carreau",
        parameter_names=("eta_0", "eta_inf", "lambda", "n"),
        parameter_units=("Pa.s", "Pa.s", "s", "1"),
        evaluate=equations.carreau_evaluate,
        guess=equations.carreau_guess,
        bounds=equations.carreau_bounds,
        describe=(
            "eta = eta_inf + (eta_0 - eta_inf)(1 + (lambda*rate)^2)^((n-1)/2) — "
            "Carreau-Yasuda 의 a=2. 높은 전단율에서 기울기 n-1 로 박화한다."
        ),
        **_COMMON,
    )
)
