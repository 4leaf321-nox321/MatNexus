"""선형 점탄성 카드의 블록 — Prony 급수.

**이 파일이 D7 의 수용 기준을 재는 자리다.** 새 물성 1종을 카드에 더하는 데 든
것이 이 파일 하나인지, 아니면 마이그레이션과 스키마와 화면이 또 딸려 오는지.

## 순간 탄성률은 탄성 블록이 든다

`*ELASTIC` 에 들어갈 E₀ 를 여기서 내지 않는다. **한 자리는 한 블록이 채운다** —
둘이 채우면 어느 값이 실릴지 정해져 있지 않고, Abaqus 는 `*VISCOELASTIC` 이
있을 때 `*ELASTIC` 을 순간 탄성률로 읽으므로 평형 탄성률이 실리면 재료가 통째로
무르게 계산된다. 그런데 덱은 멀쩡히 돌고 결과도 그럴듯하다.

그래서 점탄성 카드를 만들 때 E₀ 를 **탄성 블록에** 출처 `prony` 로 넣는다.
`cards.card_kwargs` 가 자리 겹침을 막으므로, 이 규칙을 어기면 조용히 넘어가지
않고 거절된다.
"""

from __future__ import annotations

from typing import Any

from matcore.cards import BlockSpec, register_block, rows_of, values_of
from matcore.registry import Produced


def _to_card(payload: Any) -> dict[str, Any]:
    """`(gᵢ, τᵢ)` 와 기준 온도를 낸다.

    `gᵢ` 는 **상대** 탄성률이라 이미 정규화되어 저장된다 — 여기서 다시 나누면
    무엇으로 나눈 것인지가 두 곳에 적히게 된다.
    """
    values = values_of(payload)
    terms = tuple(
        (float(row["relative_modulus"]), float(row["relaxation_time_s"]))
        for row in rows_of(payload)
    )
    out: dict[str, Any] = {"prony": terms}
    reference = values.get("reference_temperature_k")
    if reference is not None:
        out["prony_reference_temperature"] = float(reference)
    return out


VISCOELASTIC = register_block(
    BlockSpec(
        key="viscoelastic",
        label="점탄성",
        help=(
            "마스터커브에 맞춘 일반화 Maxwell 계수. **기준 온도 하나에서만 유효하다** — "
            "다른 온도의 해석에 그대로 쓰면 안 된다."
        ),
        produces=(
            Produced(
                key="equilibrium_pa",
                label="평형 탄성률",
                si_unit="Pa",
                help="완화가 끝난 뒤(t→∞) 남는 탄성률. E∞ 다.",
            ),
            Produced(
                key="instantaneous_pa",
                label="순간 탄성률",
                si_unit="Pa",
                help="t=0 의 탄성률. E₀ = E∞ + ΣEᵢ 이고, 덱의 *ELASTIC 이 이 값이다.",
            ),
            Produced(
                key="reference_temperature_k",
                label="기준 온도",
                si_unit="K",
                help="마스터커브를 겹친 온도. **이 카드가 유효한 온도다.**",
            ),
            Produced(
                key="normalized_rmse",
                label="정규화 RMSE",
                si_unit="1",
                help="E'·E'' 를 함께 맞춘 잔차. 작을수록 잘 맞는다.",
            ),
            Produced(
                key="bic",
                label="BIC",
                si_unit="1",
                help="항 수를 고른 근거. 후보를 여럿 맞춰 이 값이 가장 작은 것을 골랐다.",
            ),
            Produced(
                key="shift_method",
                label="이동 방법",
                si_unit="1",
                help="WLF·Arrhenius·수동 중 마스터커브를 겹칠 때 쓴 것.",
            ),
        ),
        rows=(
            Produced(key="relaxation_time_s", label="완화시간 τᵢ", si_unit="s"),
            Produced(key="modulus_pa", label="탄성률 Eᵢ", si_unit="Pa"),
            Produced(
                key="relative_modulus",
                label="상대 탄성률 gᵢ",
                si_unit="1",
                help="Eᵢ/E₀. Abaqus *VISCOELASTIC 이 그대로 먹는 값이다.",
            ),
        ),
        to_card=_to_card,
        order=40,
    )
)
