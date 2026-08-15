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
    "strain": "1",
    "strain_rate": "1/s",
    "velocity": "m/s",
    "time": "s",
    "temperature": "K",
    "frequency": "Hz",
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
        _u("1", "strain", "1"),
        _u("%", "strain", "0.01"),
        _u("mm/mm", "strain", "1"),
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
        _u("Hz", "frequency", "1"),
        _u("kHz", "frequency", "1000"),
        _u("kg", "mass", "1"),
        _u("g", "mass", "0.001"),
        _u("tonne", "mass", "1000"),
        _u("kg/m3", "density", "1"),
        _u("g/cm3", "density", "1000"),
        # 기존 앱이 쓰던 단위. 흡수 경로에서 그대로 들어온다.
        _u("tonne/mm3", "density", "1000000000000"),
        _u("rad", "angle", "1"),
        _u("deg", "angle", "0.0174532925199433"),
    )
}


class UnknownUnit(ValueError):
    """표에 없는 단위. 조용히 통과시키지 않기 위해 예외로 만든다."""

    def __init__(self, symbol: str) -> None:
        super().__init__(f"모르는 단위입니다: {symbol!r}")
        self.symbol = symbol


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


def units_for(dimension: str) -> list[str]:
    """그 차원에서 고를 수 있는 단위. 화면의 단위 선택기가 쓴다."""
    return [symbol for symbol, unit in UNITS.items() if unit.dimension == dimension]
