"""덱을 **어느 단위계로 쓸 것인가.**

## 왜 고르게 되었나

원래는 SI 하나였다. 그 판단은 이 패키지 머리말에 있다 — 우리가 환산해서
내보내면 **그 덱에 이미 들어 있는 다른 재료가 SI 인지 확인할 길이 없고**,
단위계가 섞인 덱은 조용히 1000배 틀린 답을 낸다.

그런데 실무에서 두 계를 다 쓴다. 판재 CAE 는 관행이 mm·N·tonne 이고, 화면도
그 단위계로 보여 준다(v1.88.0). SI 덱만 내면 해석자가 매번 손으로 환산하게
되는데, **그 손이 바로 위에서 막으려던 사고의 자리**다.

그래서 고르게 하되, 원래의 걱정을 규율로 옮겼다.

## 규율 넷

**하나 — 덱이 자기 단위계를 크게 말한다.** 솔버가 단위 블록을 주면 그것으로
(OpenRadioss `/UNIT/1`), 없으면 주석으로(Abaqus). 파일 이름에도 들어간다.

**둘 — 인수를 손으로 적지 않는다.** 이 파일은 「이 SI 단위는 저 기호로 쓴다」
만 정하고, 숫자는 `matcore.units` 가 만든다. `1e-12` 를 여기 적어 두면 그것이
표와 갈라지는 날이 온다.

**셋 — 모르는 단위는 거절한다.** 새 블록이 이 표에 없는 SI 단위를 들고 오면
환산하지 않고 멈춘다. 그대로 내보내면 그 값 하나만 SI 로 남은 덱이 나가는데,
그 덱은 **읽어서는 티가 안 난다.** 이 패키지의 태도가 「모르면 쓰지 않는다」 다.

**넷 — 기본은 SI 다.** 고르지 않으면 전과 같은 것이 나간다.

## mm·N·tonne 이 무엇인가

질량 tonne · 길이 mm · 시간 s 를 기본으로 두면 나머지가 따라온다.

    힘      tonne·mm/s² = 1e3 kg · 1e-3 m/s² = **N**       (그대로)
    응력    N/mm²                              = **MPa**
    밀도    tonne/mm³                          = 1e-12 kg/m³
    에너지  N·mm                               = **mJ**
    일률    mJ/s                               = **mW**
    비열    mJ/(tonne·K)                       = 1e-6 J/(kg·K)
    전도도  mW/(mm·K)                          = **W/(m·K)** (값이 같다)

전도도의 값이 같은 것이 함정이다 — 숫자를 안 바꾼다고 기호까지 안 바꾸면,
받는 사람이 그 덱을 SI 로 읽는다.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from matcore import units

#: 카드 블록이 실제로 들고 오는 SI 단위 전부(`matcore/cards/*.py` 의 `si_unit`).
#: 여기 없는 것이 나타나면 `symbols_for` 가 멈춘다 — 그것이 규율 셋이다.
DECLARED = ("1", "Pa", "K", "s", "kg/m3", "1/K", "J/(kg.K)", "W/(m.K)")


@dataclass(frozen=True)
class UnitSystem:
    """덱 하나가 쓰는 단위계."""

    key: str
    label: str
    """사람이 고르는 자리에 뜨는 이름."""
    mass: str
    length: str
    time: str
    """솔버에 선언할 기본 단위 셋. `/UNIT/1` 과 Abaqus 주석이 이것을 쓴다."""
    symbols: Mapping[str, str]
    """SI 단위 → 이 단위계의 기호. **값이 같아도 기호는 적는다.**"""

    def symbol(self, si_unit: str) -> str:
        """이 계에서 그 물리량을 무엇으로 쓰나. 모르면 멈춘다."""
        found = self.symbols.get(si_unit)
        if found is None:
            raise KeyError(si_unit)
        return found

    def convert(self, value: float, si_unit: str) -> float:
        """SI 값을 이 계의 숫자로. **인수는 `matcore.units` 가 만든다.**"""
        return units.from_si(value, self.symbol(si_unit))

    @property
    def declaration(self) -> str:
        """`kg, m, s, Pa` 처럼 한 줄로. 덱 머리에 그대로 들어간다."""
        return f"{self.mass}, {self.length}, {self.time}, {self.symbol('Pa')}"


SI = UnitSystem(
    key="si",
    label="SI (kg · m · s · Pa)",
    mass="kg",
    length="m",
    time="s",
    symbols={item: item for item in DECLARED},
)

MM_N_TONNE = UnitSystem(
    key="mm_n_tonne",
    label="mm · N · tonne (MPa)",
    mass="tonne",
    length="mm",
    time="s",
    symbols={
        "1": "1",
        "Pa": "MPa",
        # 절대온도는 두 계가 같다. **오프셋이 없다** — 덱에 섭씨를 쓰면
        # 솔버가 절대온도로 읽어 273 만큼 어긋난다.
        "K": "K",
        "s": "s",
        "kg/m3": "tonne/mm3",
        "1/K": "1/K",
        "J/(kg.K)": "mJ/(tonne.K)",
        # 값은 같고 기호만 다르다. 위 머리말의 함정.
        "W/(m.K)": "mW/(mm.K)",
    },
)

SYSTEMS: tuple[UnitSystem, ...] = (SI, MM_N_TONNE)


def get(key: str | None) -> UnitSystem:
    """key 로 고른다. 비면 SI — **고르지 않으면 전과 같은 것이 나간다.**"""
    if not key:
        return SI
    for system in SYSTEMS:
        if system.key == key:
            return system
    raise KeyError(key)
