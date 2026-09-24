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

카드 블록이 안 드는 역학 물리량(선하중 N/mm · 표면에너지 mJ/mm² · 파괴인성
MPa·mm^0.5 …)도 같은 식으로 따라온다 — 재료·문헌 내보내기가 쓴다(`EXCHANGED`).
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
DECLARED = ("1", "Pa", "K", "s", "kg/m3", "1/K", "J/(kg.K)", "W/(m.K)", "1/s", "Hz", "Pa.s")

#: **나가는 파일이 드는 역학 물리량**(ADR 0036, 2026-09-24). 카드 블록은 안 들지만 재료·문헌
#: 내보내기가 기본 계로 나가면서 옮기게 됐다. 기준은 하나다 — **질량·길이·시간(과 온도)으로
#: 짜인 SI 단위.** 계가 정하는 것이 그 셋이라 인수가 차원식으로 정해진다. 전기·자기(전류가
#: 든다)·물질량(mol)·로그(dB)·눈금(HV·Shore)은 계가 정하지 않아 여기 없다 — 내보내기가 받은
#: 그대로 두고 파일 머리에 적는다(`app/shared/unit_systems`).
EXCHANGED = (
    "m",
    "m2",
    "kg",
    "N",
    "rad",
    "rad/s",
    "N/m",
    "J",
    "J/m",
    "J/m2",
    "J/m3",
    "J/kg",
    "W/m2",
    "K.m2/W",
    "m/s",
    "m2/s",
    "1/Pa",
    "Pa.m0.5",
    "kg/(m2.s)",
    "kg/(m.s)",
    "kg/m2",
    "m2/kg",
    "m3/kg",
    "Pa.s/m",
    "m/cycle",
    "m3/(m2.s)",
    "m3/(N.m)",
    "1/m3",
    "m3/(m2.s.Pa)",
)

#: 계가 기호를 아는 SI 단위 전부 — 붙박이 계도, 유도한 계도 이 전부에 기호를 든다.
KNOWN = DECLARED + EXCHANGED


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
    symbols={item: item for item in KNOWN},
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
        # 점도(유변 카드). 1 Pa·s = 1e-6 N·s/mm²(= MPa·s). 기호를 `MPa.s` 로 두면
        # 단위표의 대소문자 없는 찾기가 `mPa.s` 로 읽는다 — 1e9 배 사고라 피한다.
        "Pa.s": "N.s/mm2",
        # --- 나가는 파일이 드는 역학 물리량(`EXCHANGED`) — m·kg·Pa·J·W 를 이 계의 것으로.
        "m": "mm",
        "m2": "mm2",
        "kg": "tonne",
        "N": "N",
        "rad": "rad",
        "rad/s": "rad/s",
        "N/m": "N/mm",
        "J": "mJ",
        # 값이 같다(인수 1) — 전도도와 같은 함정이라 기호는 바꿔 적는다.
        "J/m": "mJ/mm",
        "J/m2": "mJ/mm2",
        "J/m3": "mJ/mm3",
        "J/kg": "mJ/tonne",
        "W/m2": "mW/mm2",
        "K.m2/W": "K.mm2/mW",
        "m/s": "mm/s",
        "m2/s": "mm2/s",
        "1/Pa": "1/MPa",
        "Pa.m0.5": "MPa.mm0.5",
        "kg/(m2.s)": "tonne/(mm2.s)",
        "kg/(m.s)": "tonne/(mm.s)",
        "kg/m2": "tonne/mm2",
        "m2/kg": "mm2/tonne",
        "m3/kg": "mm3/tonne",
        # 음향 임피던스. `MPa.s/mm` 는 사람이 `mPa.s` 로 읽는다 — 점도와 같은 이유.
        "Pa.s/m": "N.s/mm3",
        "m/cycle": "mm/cycle",
        "m3/(m2.s)": "mm3/(mm2.s)",
        "m3/(N.m)": "mm3/(N.mm)",
        "1/m3": "1/mm3",
        "m3/(m2.s.Pa)": "mm3/(mm2.s.MPa)",
    },
)

SYSTEMS: tuple[UnitSystem, ...] = (SI, MM_N_TONNE)


#: 계가 아는 SI 단위의 차원 지수 — (질량, 길이, 시간). 온도는 K 그대로다(오프셋 없음).
#: 절대온도의 역수·비열·전도도의 K 는 지수에 안 들어가고 기호에만 붙는다. 각(rad)·주기
#: (cycle)도 그렇다. **손으로 적는 표라** 시험이 기호를 밑기호로 풀어 다시 세어 대조한다 —
#: mm·N·tonne 은 시간이 s 라 시간 지수가 틀려도 숫자가 같게 나와서 그 계로는 안 드러난다.
EXPONENTS: dict[str, tuple[float, float, float]] = {
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
    "Pa.s": (1, -1, -1),
    "m": (0, 1, 0),
    "m2": (0, 2, 0),
    "kg": (1, 0, 0),
    "N": (1, 1, -2),
    "rad": (0, 0, 0),
    "rad/s": (0, 0, -1),
    "N/m": (1, 0, -2),
    "J": (1, 2, -2),
    "J/m": (1, 1, -2),
    "J/m2": (1, 0, -2),
    "J/m3": (1, -1, -2),
    "J/kg": (0, 2, -2),
    "W/m2": (1, 0, -3),
    "K.m2/W": (-1, 0, 3),
    "m/s": (0, 1, -1),
    "m2/s": (0, 2, -1),
    "1/Pa": (-1, 1, 2),
    "Pa.m0.5": (1, -0.5, -2),
    "kg/(m2.s)": (1, -2, -1),
    "kg/(m.s)": (1, -1, -1),
    "kg/m2": (1, -2, 0),
    "m2/kg": (-1, 2, 0),
    "m3/kg": (-1, 3, 0),
    "Pa.s/m": (1, -2, -1),
    "m/cycle": (0, 1, 0),
    "m3/(m2.s)": (0, 1, -1),
    "m3/(N.m)": (-1, 1, 2),
    "1/m3": (0, -3, 0),
    "m3/(m2.s.Pa)": (-1, 2, 1),
}

#: 지수로는 0 이지만 기호에는 있어야 하는 것 — 기본 단위로 지을 때(`_compose`) 붙인다.
#: 분모에 K(mm2/(ms2.K)) · 분자에 K(K.ms3/kg) · 분자에 rad(rad/ms) · 분모에 cycle(mm/cycle).
_PER_KELVIN = frozenset({"J/(kg.K)", "W/(m.K)"})
_TIMES_KELVIN = frozenset({"K.m2/W"})
_TIMES_RADIAN = frozenset({"rad/s"})
_PER_CYCLE = frozenset({"m/cycle"})


def _power(symbol: str, exponent: float) -> str:
    if exponent == 1:
        return symbol
    # `mm2` · `mm0.5` — 정수 지수에 `.0` 이 붙으면 표가 못 읽는다.
    return f"{symbol}{exponent:g}"


def _compose(mass: str, length: str, time: str, si_unit: str) -> str:
    """기본 단위로 기호를 짓는다 — `kg/(mm.ms2)`. 표에 있는 기호를 못 찾았을 때만."""
    m, l_, t = EXPONENTS[si_unit]
    above = [_power(base, e) for base, e in ((mass, m), (length, l_), (time, t)) if e > 0]
    below = [_power(base, -e) for base, e in ((mass, m), (length, l_), (time, t)) if e < 0]
    if si_unit in _TIMES_KELVIN:
        above.insert(0, "K")
    if si_unit in _TIMES_RADIAN:
        above.insert(0, "rad")
    if si_unit in _PER_KELVIN:
        below.append("K")
    if si_unit in _PER_CYCLE:
        below.append("cycle")
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


#: 계가 정하는 차원 — 기호에 든 이 차원의 단위는 그 계의 기본 단위여야 한다.
_BASE_DIMENSIONS = frozenset({"mass", "length", "time"})


def _foreign(symbol: str, bases: tuple[str, str, str]) -> bool:
    """그 계의 것이 아닌 질량·길이·시간 단위가 기호에 드는가.

    kg·mm·ms 계의 질량 플럭스는 인수가 `tonne/(mm2.s)` 와 같다(1e9). 인수만 보고 그 기호를
    집으면 받는 사람이 「이 파일은 tonne·s 계인가」 를 묻는다 — 기본 단위로 짓는 편이
    (`kg/(mm2.ms)`) 그 파일이 어느 계인지를 말한다(2026-09-24, 기호표를 넓히다 드러났다).
    """
    for token in _tokens(symbol):
        unit = units.UNITS.get(token)
        if unit is not None and unit.dimension in _BASE_DIMENSIONS and token not in bases:
            return True
    return False


def _symbol_for(si_unit: str, factor: float, bases: tuple[str, str, str]) -> str:
    if EXPONENTS[si_unit] == (0, 0, 0):
        # 무차원·온도는 어느 계나 같다. 표에서 찾으면 mm 계가 `mm/mm` 를 집는다.
        return si_unit
    dimension = units.unit_of(si_unit).dimension
    # **여기서는 차원 이름이 같은 것만 본다**(2026-09-24). `units_for` 는 별칭까지
    # 편다 — 변형률 속도와 주파수는 같은 `1/s` 라 검증에서는 하나로 봐야 하지만,
    # 덱에 적히는 기호는 그렇지 않다. 열어 두면 mm 계의 주파수가 `Hz` 대신 `1/s` 로
    # 적힌다(아래 「기본 단위 이름이 든 기호」 규칙이 `s` 를 보고 집는다).
    candidates = [
        symbol
        for symbol, unit in units.UNITS.items()
        if unit.dimension == dimension
        and unit.offset == 0
        and abs(float(unit.factor) - factor) <= 1e-9 * max(factor, 1e-30)
        and not _foreign(symbol, bases)
    ]
    if not candidates:
        return _compose(*bases, si_unit)
    # **SI 계에서는 정본 기호다.** `N/m2` 가 표에 들어오면서(2026-09-20) 인수 1 후보가 둘이
    # 됐고, 아래 「기본 단위 이름이 든 기호」 규칙이 `m` 을 보고 `N/m2` 를 집었다 — SI 덱의
    # 응력이 `Pa` 에서 `N/m2` 로 바뀌는 것은 규약 변경이지 개선이 아니다. 정본이 인수까지
    # 맞으면 그것이다. mm 계에서는 정본의 인수가 안 맞으니(mW/(mm.K) 만 1) 아래로 간다.
    canonical = units.SI_UNITS.get(dimension)
    if canonical in candidates and bases == ("kg", "m", "s"):
        return canonical
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
