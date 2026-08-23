"""고무 초탄성 카드의 블록.

**ADR 0012 를 재는 자리다.** 점탄성은 블록 구조를 만들면서 함께 넣은 것이라 공정한
측정이 아니었다. 이 물성은 구조가 굳은 뒤에 붙는 첫 번째다 — 정말 `BlockSpec`
하나로 끝나는지가 여기서 드러난다.
"""

from __future__ import annotations

from typing import Any

from matcore.cards import BlockSpec, register_block, rows_of, values_of
from matcore.registry import Produced


def _to_card(payload: Any) -> dict[str, Any]:
    """식 이름과 계수를 그대로 넘긴다.

    **환산하지 않는다.** Abaqus 의 `*HYPERELASTIC` 은 식마다 받는 계수의 이름과
    순서가 다르고, 그 매핑은 내보내기가 안다 — 여기서 섞으면 두 곳이 갈라진다.
    """
    values = values_of(payload)
    family = values.get("family")
    if not family:
        return {}
    return {
        "hyperelastic_family": str(family),
        "hyperelastic_parameters": tuple(
            (str(row["name"]), float(row["value"])) for row in rows_of(payload)
        ),
    }


HYPERELASTIC = register_block(
    BlockSpec(
        key="hyperelastic",
        label="초탄성",
        help=(
            "고무의 변형에너지 계수. **공칭 응력·공칭 변형률에 맞춘 값이다** — "
            "금속 경화식과 축이 다르다."
        ),
        produces=(
            Produced(
                key="label",
                label="식",
                si_unit="1",
                help="Neo-Hookean·Mooney-Rivlin·Yeoh·Ogden 중 고른 것.",
            ),
            Produced(
                key="mode",
                label="시험 모드",
                si_unit="1",
                help="맞춘 데이터의 변형 모드. **다른 모드에서는 빗나갈 수 있다.**",
            ),
            Produced(
                key="shear_modulus",
                label="초기 전단탄성률",
                si_unit="Pa",
                help=(
                    "변형이 0 에 가까울 때의 기울기에서 나온다. "
                    "식이 달라도 이 값은 비슷해야 한다."
                ),
            ),
            Produced(
                key="relative_rmse",
                label="상대 RMSE",
                si_unit="1",
                help="적합 구간에서 데이터와 얼마나 벌어지는가.",
            ),
            Produced(key="r_squared", label="R²", si_unit="1"),
            Produced(
                key="max_residual",
                label="최대 잔차",
                si_unit="Pa",
                help="가장 크게 벌어진 한 점. 평균이 좋아도 여기가 크면 국소적으로 안 맞는다.",
            ),
            Produced(
                key="strain_min",
                label="적합 구간 시작",
                si_unit="1",
                help="공칭 변형률. **그 밖은 검증되지 않았다.**",
            ),
            Produced(key="strain_max", label="적합 구간 끝", si_unit="1", help="공칭 변형률."),
        ),
        rows=(
            Produced(key="name", label="파라미터", si_unit="1"),
            Produced(key="value", label="값", si_unit="1", help="행이 자기 단위를 든다."),
        ),
        to_card=_to_card,
        order=25,
    )
)
