"""단위 변환 — 저장은 SI, 입력·표시·내보내기는 사람과 솔버의 단위.

기존 앱(MaterialAppVer2)은 밀도를 `tonne/mm³` 로 저장했다. Abaqus mm-tonne-s
단위계다. **내보낼 대상 솔버에 맞춘 단위로 원본을 저장**하면, 다른 솔버를 붙일 때
어디서 변환이 일어났는지 추적할 수 없다. 그래서 저장은 SI 기본단위로 고정하고,
변환은 이 모듈 한 곳에서만 일어나게 한다.

Decimal 로 계산한다. `0.45 * 0.001` 같은 이진 부동소수 연산은 눈에 안 보이는
꼬리를 남기고(`0.00045000000000000004`), 그 값이 이름 생성으로 흘러가면 같은
재료가 저장 경로에 따라 다른 이름을 받는다.

온도는 곱셈만으로 안 된다. `°C → K` 는 오프셋이 있다. 오프셋을 무시하고 계수만
두는 표를 만들면 25°C 가 25K 가 되는데, 그런 값은 화면에서 이상해 보이지 않아
한참 뒤에야 발견된다.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Unit:
    """SI = value * factor + offset."""

    symbol: str
    dimension: str
    factor: Decimal
    offset: Decimal = Decimal(0)


def _u(symbol: str, dimension: str, factor: str, offset: str = "0") -> Unit:
    return Unit(symbol, dimension, Decimal(factor), Decimal(offset))


#: 차원별 SI 기본단위. 저장할 때 쓰는 단위다.
SI_UNITS = {
    "length": "m",
    "force": "N",
    "stress": "Pa",
    "strain": "1",  # 무차원의 별칭. 화면·정의에서 뜻을 드러내려고 남긴다.
    "strain_rate": "1/s",
    "velocity": "m/s",
    "time": "s",
    "temperature": "K",
    "frequency": "Hz",
    "angular_frequency": "rad/s",
    "inverse_temperature": "1/K",
    "compliance": "1/Pa",
    "mass": "kg",
    "density": "kg/m3",
    "angle": "rad",
    "dimensionless": "1",
}

#: 받아들이는 단위. 표에 없는 단위는 **거부한다** — 조용히 계수 1로 통과시키면
#: 잘못된 값이 SI 인 척 저장되고, 나중에 어느 행이 틀렸는지 알 수 없다.
UNITS: dict[str, Unit] = {
    unit.symbol: unit
    for unit in (
        _u("m", "length", "1"),
        _u("cm", "length", "0.01"),
        _u("mm", "length", "0.001"),
        _u("um", "length", "0.000001"),
        _u("N", "force", "1"),
        _u("kN", "force", "1000"),
        _u("Pa", "stress", "1"),
        _u("kPa", "stress", "1000"),
        _u("MPa", "stress", "1000000"),
        _u("GPa", "stress", "1000000000"),
        # **변형률은 물리적으로 무차원이다.** `1` 을 strain 차원에 두면 tan δ 나
        # 비율 같은 다른 무차원 값과 같은 단위를 쓰면서 차원만 달라져, 정의
        # 검증이 서로를 거절한다. 실제로 DMA 정의를 만들다 걸렸다.
        # 이름으로 구분하는 것은 의미(semantics)지 차원이 아니다.
        _u("1", "dimensionless", "1"),
        _u("%", "dimensionless", "0.01"),
        _u("mm/mm", "dimensionless", "1"),
        _u("1/s", "strain_rate", "1"),
        _u("1/min", "strain_rate", "0.0166666666666667"),
        _u("m/s", "velocity", "1"),
        _u("mm/s", "velocity", "0.001"),
        _u("mm/min", "velocity", "0.0000166666666666667"),
        _u("s", "time", "1"),
        _u("ms", "time", "0.001"),
        _u("min", "time", "60"),
        _u("h", "time", "3600"),
        _u("K", "temperature", "1"),
        _u("degC", "temperature", "1", "273.15"),
        # **사람은 `°C` 라고 쓴다.** 화면이 그 기호를 보여 주는 이상 그대로
        # 돌아올 수 있어야 한다 — 안 받으면 "모르는 단위입니다: °C" 로 막힌다.
        # 65도 같은 별칭을 갖고 있었다(`aliases=("degC", "°C")`).
        _u("°C", "temperature", "1", "273.15"),
        # 한글 입력기가 만드는 합자. 사람이 친 것과 붙여넣은 것이 다르면 안 된다.
        _u("℃", "temperature", "1", "273.15"),
        _u("Hz", "frequency", "1"),
        _u("kHz", "frequency", "1000"),
        # **각주파수는 주파수로 환산하지 않는다.** 실측(TA DMA850): 한 파일에
        # 각주파수 126.289 rad/s 와 주파수 20.0 Hz 가 함께 있는데 126.289/2π =
        # 20.1 로 정확히 안 맞는다. 장비가 각각 실측한 별개 값이므로 같은 것의
        # 다른 표기가 아니다 — 환산하면 없는 관계를 만들어 낸다.
        _u("rad/s", "angular_frequency", "1"),
        _u("kg", "mass", "1"),
        _u("g", "mass", "0.001"),
        _u("tonne", "mass", "1000"),
        _u("kg/m3", "density", "1"),
        _u("g/cm3", "density", "1000"),
        # 기존 앱이 쓰던 단위. 흡수 경로에서 그대로 들어온다.
        _u("tonne/mm3", "density", "1000000000000"),
        _u("1/K", "inverse_temperature", "1"),
        _u("1/Pa", "compliance", "1"),
        _u("1/MPa", "compliance", "0.000001"),
        _u("rad", "angle", "1"),
        _u("deg", "angle", "0.0174532925199433"),
    )
}


class UnknownUnit(ValueError):
    """표에 없는 단위. 조용히 통과시키지 않기 위해 예외로 만든다."""

    def __init__(self, symbol: str) -> None:
        super().__init__(f"모르는 단위입니다: {symbol!r}")
        self.symbol = symbol


def _case_index() -> dict[str, str]:
    """소문자 → 정본 심볼. **충돌하면 둘 다 뺀다.**

    장비가 `MPa` 를 `Mpa`·`mpa`·`MPA` 로 적는 일이 흔하다. 단위 표기의 대소문자는
    물리적으로 뜻이 있으므로(`m` 미터 / `M` 메가) 통째로 무시할 수는 없지만,
    **지금 표 안에서 소문자로 겹치는 심볼이 하나도 없다면** 대소문자만 다른 표기를
    정본으로 되돌리는 것은 모호하지 않다.

    문제는 나중이다. 언젠가 `mPa`(밀리파스칼)를 표에 넣으면 `MPa` 와 소문자가
    같아지는데, 그때 조용히 하나를 고르면 **10⁹ 배** 틀린다. 그래서 충돌하는 키는
    아예 빼 버린다 — 그 표기는 정확히 적어야만 통과한다. `tests/unit/test_units`
    가 충돌이 생기는 순간 실패하므로 소리 없이 넘어가지 않는다.
    """
    index: dict[str, str] = {}
    for symbol in UNITS:
        key = symbol.lower()
        index[key] = "" if key in index else symbol
    return {key: symbol for key, symbol in index.items() if symbol}


CASE_INDEX = _case_index()


def canonical(symbol: str) -> str | None:
    """표기가 조금 다른 단위를 정본 심볼로. 모르면 `None`.

    정확히 맞는 것이 먼저다 — 대소문자 되돌리기는 그다음에만 한다.
    """
    text = symbol.strip()
    if text in UNITS:
        return text
    return CASE_INDEX.get(text.lower())


def unit_of(symbol: str) -> Unit:
    try:
        return UNITS[symbol]
    except KeyError:
        raise UnknownUnit(symbol) from None


def to_si(value: float | Decimal | str, symbol: str) -> float:
    """사람이 입력한 값을 저장할 값으로."""
    unit = unit_of(symbol)
    return float(Decimal(str(value)) * unit.factor + unit.offset)


def from_si(value: float | Decimal | str, symbol: str) -> float:
    """저장한 값을 보여 줄 값으로."""
    unit = unit_of(symbol)
    return float((Decimal(str(value)) - unit.offset) / unit.factor)


#: 이름은 다르지만 같은 차원. 변형률·무차원은 물리적으로 하나다 —
#: 구분해 부르는 것은 사람이 뜻을 알아보기 위해서지 단위가 다르기 때문이 아니다.
DIMENSION_ALIASES = {"strain": "dimensionless"}


def normalize_dimension(dimension: str) -> str:
    return DIMENSION_ALIASES.get(dimension, dimension)


def same_dimension(left: str, right: str) -> bool:
    """두 차원이 실질적으로 같은가. 정의 검증과 조건 환산이 함께 쓴다."""
    return normalize_dimension(left) == normalize_dimension(right)


def units_for(dimension: str) -> list[str]:
    """그 차원에서 고를 수 있는 단위. 화면의 단위 선택기가 쓴다."""
    wanted = normalize_dimension(dimension)
    return [
        symbol
        for symbol, unit in UNITS.items()
        if normalize_dimension(unit.dimension) == wanted
    ]
