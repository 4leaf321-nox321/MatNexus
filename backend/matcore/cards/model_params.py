"""모델 파라미터 블록 — **여럿이 한 벌이어야 뜻이 있는 값**을 카드가 인용한다.

Anand 9개·Prony 항·Ogden 계수처럼, 낱개로는 못 쓰고 한 벌이 통째로 있어야 솔버가
읽는 값들이다(ADR 0029).

## 카드는 **인용**한다 — 소유하지 않는다

원본은 재료가 든다(`material_parameter_sets`). 카드는 그중 하나를 골라 실을 뿐이다
— 처리 결과가 남고 카드가 채택하는 것과 같은 모양이다(ADR 0007). 그래서 이 블록의
행은 `set` 을 함께 든다: 어느 벌에서 왔는지 카드만 봐도 되짚을 수 있어야 한다.

## 단위가 행에 붙는다

한 벌 안에서 `1`·`1/s`·`MPa`·`K` 가 섞이므로 블록 단위 하나로는 못 적는다. 경화식
파라미터가 식마다 단위가 다른 것과 같은 사정이고, `BlockSpec` 은 이미 **행이 든
단위가 이긴다**고 적어 두었다.

**환산하지 않는다.** 문헌의 이 값들은 SI 가 아니라 그 항의 원래 단위다 —
h0 = 2640.75 MPa 를 SI 로 고치면 모델이 기대하는 값과 달라진다.
"""

from __future__ import annotations

from matcore.cards import BlockSpec, register_block
from matcore.registry import Produced

MODEL_PARAMS = register_block(
    BlockSpec(
        key="model_params",
        label="모델 파라미터",
        help=(
            "Anand·Prony·Ogden 처럼 여럿이 한 벌이어야 뜻이 있는 값. 재료가 든 "
            "원본을 카드가 인용한다 — 단위는 항마다 다르고 환산하지 않는다."
        ),
        produces=(
            Produced(
                key="sets",
                label="벌 수",
                si_unit="1",
                help="이 카드가 인용한 파라미터 벌의 개수.",
            ),
            Produced(
                key="models",
                label="모델",
                si_unit="1",
                help="`anand` · `prony` 처럼 파라미터의 뜻을 정하는 이름들.",
            ),
        ),
        rows=(
            Produced(
                key="set",
                label="벌",
                si_unit="1",
                help="어느 벌에서 왔나 — `모델/출처`. **카드만 봐도 되짚을 수 있어야 한다.**",
            ),
            Produced(key="name", label="파라미터", si_unit="1", help="그 벌 안에서의 이름."),
            Produced(
                key="value",
                label="값",
                si_unit="1",
                help="**환산하지 않은 값.** 단위는 옆 칸이 든다.",
            ),
            Produced(
                key="unit",
                label="단위",
                si_unit="1",
                help="그 항의 단위. 한 벌 안에서 서로 다르다.",
            ),
        ),
        order=50,
        kind_priority=None,
    )
)
