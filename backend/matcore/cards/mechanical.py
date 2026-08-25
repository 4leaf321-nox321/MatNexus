"""금속 소성 카드의 블록 — 탄성·경화식·소성 표.

인장 한 줄기가 파일에서 솔버 덱까지 닫히면서 굳은 셋이다. 전에는 이것이
`property_cards` 의 컬럼 이름이었다 — 여기로 옮기면서 **데이터가 됐다.**
"""

from __future__ import annotations

from matcore.cards import BlockSpec, register_block
from matcore.registry import Produced

ELASTIC = register_block(
    BlockSpec(
        key="elastic",
        label="탄성",
        help=(
            "탄성계수·푸아송비·밀도. 푸아송비와 밀도는 인장시험이 주지 않는다 — "
            "재료나 시료에서 물려받거나 사람이 넣는다."
        ),
        produces=(
            Produced(
                key="youngs_modulus",
                label="탄성계수",
                si_unit="Pa",
                help=(
                    "대표 곡선의 탄성 구간에서 잰 값. 점탄성 카드에서는 순간(t=0) 탄성률이다."
                ),
            ),
            Produced(
                key="poisson_ratio",
                label="푸아송비",
                si_unit="1",
                help="인장시험이 주지 않는다. 재료에서 물려받거나 사람이 넣는다.",
            ),
            Produced(
                key="density",
                label="밀도",
                si_unit="kg/m3",
                help="동적 해석에 필요하다. 시료의 실측값이 있으면 그것을 쓴다.",
            ),
        ),
        rows=(
            Produced(
                key="temperature",
                label="온도",
                si_unit="K",
                help="이 줄의 값들이 유효한 온도.",
            ),
            Produced(key="youngs_modulus", label="탄성계수", si_unit="Pa", help=None),
            Produced(key="poisson_ratio", label="푸아송비", si_unit="1", help=None),
        ),
        # 표가 있으면 **온도에 따라 변한다는 뜻**이다. 강판 탄성계수는 상온
        # 206 GPa 가 400 °C 에서 170 GPa 쯤으로 떨어지고, 열간 성형·용접·화재
        # 해석은 그 곡선이 필요하다.
        #
        # **`values` 는 그때도 남는다** — 첫 줄(가장 낮은 온도)의 값이다. 표를
        # 못 먹는 형식이 그것을 쓰고, 목록이 대푯값 하나를 보일 때도 쓴다.
        order=10,
    )
)


HARDENING = register_block(
    BlockSpec(
        key="hardening",
        label="경화식",
        help=(
            "적합한 경화식과 그 적합도. **덱에는 안 실린다** — 소성은 표로 나가고 "
            "식은 주석에만 남는다. 이 표가 어디까지 검증된 것인지가 여기에 있다."
        ),
        produces=(
            Produced(
                key="label",
                label="식",
                si_unit="1",
                help="Voce·Swift·Hockett-Sherby 중 고른 것.",
            ),
            Produced(
                key="relative_rmse",
                label="상대 RMSE",
                si_unit="1",
                help="적합 구간에서 데이터와 얼마나 벌어지는가. 작을수록 잘 맞는다.",
            ),
            Produced(key="r_squared", label="R²", si_unit="1", help="결정계수."),
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
                help="진소성변형률. **그 밖은 검증되지 않았다.**",
            ),
            Produced(
                key="strain_max", label="적합 구간 끝", si_unit="1", help="진소성변형률."
            ),
        ),
        rows=(
            Produced(key="name", label="파라미터", si_unit="1", help="식 안에서의 이름."),
            Produced(key="value", label="값", si_unit="1", help="행이 자기 단위를 들고 있다."),
        ),
        # **덱에 안 실린다.** 실리지 않는다고 쓸모없는 것이 아니라 실리는 자리가
        order=20,
    )
)


TABLE = register_block(
    BlockSpec(
        key="table",
        label="소성 표",
        help=(
            "진소성변형률·진응력의 점 목록. **많은 솔버가 식보다 표를 그대로 받고**, "
            "식이 안 맞는 재료에서는 표가 더 정확하다."
        ),
        produces=(
            Produced(
                key="source",
                label="표를 만든 방법",
                si_unit="1",
                help="`측정` 이면 대표 곡선 그대로, `외삽` 이면 그 뒤를 적합식으로 이었다.",
            ),
            Produced(
                key="measured_max",
                label="측정이 끝난 변형률",
                si_unit="1",
                help="**여기까지가 시험이 답한 범위다.** 그 위는 식이 답한 것이다.",
            ),
            Produced(
                key="extrapolated_to",
                label="늘린 한계",
                si_unit="1",
                help="어디까지 늘렸나. 얼마까지 필요한지는 무슨 해석을 하느냐가 정한다.",
            ),
            Produced(
                key="family",
                label="늘릴 때 쓴 식",
                si_unit="1",
                help="적합 구간에서 비슷한 두 식이 외삽에서 크게 갈린다.",
            ),
            Produced(
                key="junction_gap",
                label="이음매 벌어짐",
                si_unit="1",
                help=(
                    "이음매에서 식이 측정과 벌어진 정도. "
                    "크면 그 식이 곡선의 끝을 못 따라간 것이다."
                ),
            ),
        ),
        rows=(
            Produced(key="plastic_strain", label="진소성변형률", si_unit="1"),
            Produced(key="true_stress", label="진응력", si_unit="Pa"),
        ),
        order=30,
    )
)
