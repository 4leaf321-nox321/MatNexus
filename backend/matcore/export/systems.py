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

import re
from collections.abc import Mapping
from dataclasses import dataclass

from matcore import units

#: 카드 블록이 실제로 들고 오는 SI 단위 전부(`matcore/cards/*.py` 의 `si_unit`).
#: 여기 없는 것이 나타나면 `symbols_for` 가 멈춘다 — 그것이 규율 셋이다.
#: 카드 블록이 드는 SI 단위 전부. **블록에 새 단위가 생기면 여기와 두 계의 기호에 함께
#: 적는다** — `tests/unit/test_export_units.py` 가 블록 선언과 대조한다. 실측(2026-09-05):
#: 속도 의존(`1/s`)·선형탄성구간(`Hz`) 카드가 기본 계(mm·N·tonne)로 내려받기가 전부
#: 422 였다. 기본 계를 SI 에서 바꾼 날 드러났다.
DECLARED = ("1", "Pa", "K", "s", "kg/m3", "1/K", "J/(kg.K)", "W/(m.K)", "1/s", "Hz")


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

    factors: Mapping[str, float] | None = None
    """SI 단위 → 이 계의 인수(SI 값 ÷ 인수 = 이 계의 값). 붙박이 계는 비워 두고 기호로
    `matcore.units` 표를 찾는다. **유도한 계**(`derive`)는 기호가 표에 없을 수 있어(예:
    kg/mm3) 기본 단위의 인수에서 차원식으로 만든 인수를 든다."""

    builtin: bool = True

    def symbol(self, si_unit: str) -> str:
        """이 계에서 그 물리량을 무엇으로 쓰나. 모르면 멈춘다."""
        found = self.symbols.get(si_unit)
        if found is None:
            raise KeyError(si_unit)
        return found

    def convert(self, value: float, si_unit: str) -> float:
        """SI 값을 이 계의 숫자로. **인수는 `matcore.units` 가 만든다** — 유도한 계는
        기본 단위의 인수를 표에서 읽어 차원식으로 곱한 것이다."""
        if self.factors is not None:
            factor = self.factors.get(si_unit)
            if factor is None:
                raise KeyError(si_unit)
            return value / factor
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
        # 시간이 s 라 변형률 속도·주파수는 SI 와 같다.
        "1/s": "1/s",
        "Hz": "Hz",
    },
)

SYSTEMS: tuple[UnitSystem, ...] = (SI, MM_N_TONNE)


#: 카드가 드는 SI 단위의 차원 지수 — (질량, 길이, 시간). 온도는 K 그대로다(오프셋 없음).
#: 절대온도의 역수·비열·전도도의 K 는 지수에 안 들어가고 기호에만 붙는다.
EXPONENTS: dict[str, tuple[int, int, int]] = {
    "1": (0, 0, 0),
    "Pa": (1, -1, -2),
    "K": (0, 0, 0),
    "s": (0, 0, 1),
    "kg/m3": (1, -3, 0),
    "1/K": (0, 0, 0),
    "J/(kg.K)": (0, 2, -2),
    "W/(m.K)": (1, 1, -3),
    "1/s": (0, 0, -1),
    "Hz": (0, 0, -1),
}

#: 분모에 K 가 드는 것. 지수로는 0 이지만 기호에는 있어야 한다 — mm2/(ms2.K).
_PER_KELVIN = frozenset({"J/(kg.K)", "W/(m.K)"})


def _power(symbol: str, exponent: int) -> str:
    if exponent == 1:
        return symbol
    return f"{symbol}{exponent}"


def _compose(mass: str, length: str, time: str, si_unit: str) -> str:
    """기본 단위로 기호를 짓는다 — `kg/(mm.ms2)`. 표에 있는 기호를 못 찾았을 때만."""
    m, l_, t = EXPONENTS[si_unit]
    above = [_power(base, e) for base, e in ((mass, m), (length, l_), (time, t)) if e > 0]
    below = [_power(base, -e) for base, e in ((mass, m), (length, l_), (time, t)) if e < 0]
    if si_unit in _PER_KELVIN:
        below.append("K")
    top = ".".join(above) if above else "1"
    if not below:
        return top
    if len(below) == 1:
        return f"{top}/{below[0]}"
    return f"{top}/({'.'.join(below)})"


def derive(
    key: str,
    label: str,
    *,
    mass: str,
    length: str,
    time: str,
    builtin: bool = False,
) -> UnitSystem:
    """질량·길이·시간 셋으로 계 하나를 만든다(2026-09-05).

    두 계가 코드에 박혀 있어 LS-DYNA 의 mm·ms·kg(GPa) 같은 조합은 배포가 필요했다.
    기본 단위 셋만 정하면 나머지 인수는 차원식(`EXPONENTS`)으로 따라온다 — 인수를 손으로
    적지 않는다는 규율 그대로다: 기본 단위의 인수는 `matcore.units` 표에서 읽는다.

    기호는 표에서 같은 차원·같은 인수인 것을 찾아 쓰고(응력 1e9 → GPa), 없으면 기본 단위로
    짓는다(kg/mm3). 값이 같은 기호가 여럿이면 기본 단위 이름이 든 것을 고른다 —
    mm·N·tonne 의 전도도는 W/(m.K) 이 아니라 mW/(mm.K) 로 적혀야 「이 덱은 SI 다」 로
    안 읽힌다.
    """
    bases = {}
    for name, symbol, dimension in (
        ("mass", mass, "mass"),
        ("length", length, "length"),
        ("time", time, "time"),
    ):
        unit = units.unit_of(symbol)
        if unit.dimension != dimension or unit.offset != 0:
            raise ValueError(f"{name} 단위가 아닙니다: {symbol}")
        bases[name] = float(unit.factor)
    symbols: dict[str, str] = {}
    factors: dict[str, float] = {}
    for si_unit, (m, l_, t) in EXPONENTS.items():
        factor = (bases["mass"] ** m) * (bases["length"] ** l_) * (bases["time"] ** t)
        factors[si_unit] = factor
        symbols[si_unit] = _symbol_for(si_unit, factor, (mass, length, time))
    return UnitSystem(
        key=key,
        label=label,
        mass=mass,
        length=length,
        time=time,
        symbols=symbols,
        factors=factors,
        builtin=builtin,
    )


def _tokens(symbol: str) -> set[str]:
    return set(re.findall(r"[A-Za-z]+", symbol))


def _symbol_for(si_unit: str, factor: float, bases: tuple[str, str, str]) -> str:
    if EXPONENTS[si_unit] == (0, 0, 0):
        # 무차원·온도는 어느 계나 같다. 표에서 찾으면 mm 계가 `mm/mm` 를 집는다.
        return si_unit
    dimension = units.unit_of(si_unit).dimension
    candidates = [
        symbol
        for symbol in units.units_for(dimension)
        if units.unit_of(symbol).offset == 0
        and abs(float(units.unit_of(symbol).factor) - factor) <= 1e-9 * max(factor, 1e-30)
    ]
    if not candidates:
        return _compose(*bases, si_unit)
    # **기본 단위 이름이 든 기호가 먼저.** 같은 값이라도 mm 계에서는 mW/(mm.K) 가 W/(m.K)
    # 보다 「이 덱이 어느 계인지」 를 말한다. 표의 정본 표기(ASCII, 점 곱)를 고른다.
    ascii_only = [one for one in candidates if one.isascii()] or candidates
    with_base = [one for one in ascii_only if _tokens(one) & set(bases)]
    return (with_base or ascii_only)[0]


def get(key: str | None) -> UnitSystem:
    """key 로 고른다. 비면 SI — **고르지 않으면 전과 같은 것이 나간다.**"""
    if not key:
        return SI
    for system in SYSTEMS:
        if system.key == key:
            return system
    raise KeyError(key)
