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
    # 시편 단면적을 사람이 직접 재서 적는 자리가 있다(식으로 안 되는 모양).
    # 길이로 두면 화면이 mm 로 환산해 10⁶ 배 틀린다.
    "area": "m2",
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
    # **열해석 물성.** 시험이 주지 않고 핸드북·규격에서 온다 — 그래서 「선언
    # 물성」으로 들어온다(v1.71.0). 차원을 여기 적어 두면 값을 넣을 때 단위가
    # 검사되고, 「비열 자리에 열전도율」 같은 것이 막힌다.
    "specific_heat": "J/(kg.K)",
    "thermal_conductivity": "W/(m.K)",
    "compliance": "1/Pa",
    "mass": "kg",
    "density": "kg/m3",
    "angle": "rad",
    "dimensionless": "1",
    # --- 문헌 카탈로그가 쓰는 SI 조합 단위 (2026-09-12) ----------------------
    #
    # **왜 한꺼번에 늘었나.** 문헌 정의 271종 가운데 77종(값 7,325건)의 단위를 이 표가
    # 몰랐다 — 박리강도 N/m(1,017건) · 체적저항률 ohm·m(661) · 표면에너지 J/m²(458)
    # 같은 멀쩡한 SI 조합이다. 표가 모르면 그 물성은 **사내 물성 항목에 못 이어지고**
    # (차원 검사가 막는다), 값으로 찾기에서 환산이 안 되고, 새 정의도 그 단위로는 못
    # 만든다. 즉 7천 건이 검색·매핑·채우기에서 조용히 빠져 있었다.
    #
    # **정본 기호는 인수 1 이다.** 카탈로그가 그 단위로 값을 저장하고 있어서, 다른
    # 인수를 주면 저장된 숫자를 다른 단위로 읽는다. 실무 표기(MPa·m^0.5 · ohm·cm ·
    # kV/mm · cP)만 인수를 갖는다.
    #
    # **차원 이름은 물리량으로 짓는다.** 차원이 같아도(N/m 과 J/m² 는 같다) 뜻이 다른
    # 물성은 다른 이름을 준다 — 잇지 못하는 쪽이 엉뚱한 것끼리 이어지는 쪽보다 낫다.
    # 눈금(HV·Shore·HR·HBW·HK·GU)은 **넣지 않는다** — 환산할 수 없는 것을 표에 넣으면
    # 환산할 수 있는 척하게 된다.
    "line_force": "N/m",  # 선하중 (박리·택)
    "energy_per_area": "J/m2",  # 단위면적당 에너지
    "resistivity": "ohm.m",  # 체적저항률
    "resistance": "ohm",  # 저항
    "electric_conductivity": "S/m",  # 전기전도율
    "viscosity": "Pa.s",  # 점도
    "photon_energy": "eV",  # 준위 에너지
    "gas_permeability": "mol/(m.s.Pa)",  # 기체 투과도
    "molar_energy": "J/mol",  # 몰당 에너지
    "diffusivity": "m2/s",  # 확산율
    "fracture_toughness": "Pa.m0.5",  # 파괴인성
    "electric_field": "V/m",  # 전계 강도
    "magnetic_field": "A/m",  # 자계 강도
    "mass_flux": "kg/(m2.s)",  # 질량 플럭스
    "magnetic_flux_density": "T",  # 자속밀도
    "specific_area": "m2/kg",  # 비표면적
    "voltage": "V",  # 전위
    "energy": "J",  # 에너지
    "molar_mass": "kg/mol",  # 몰질량
    "energy_density": "J/m3",  # 에너지 밀도
    "thermal_resistance": "K.m2/W",  # 열저항
    "specific_volume": "m3/kg",  # 비체적
    "acoustic_impedance": "Pa.s/m",  # 음향 임피던스
    "energy_per_length": "J/m",  # 길이당 에너지
    "decibel": "dB",  # 데시벨
    "concentration": "mol/m3",  # 농도
    "charge_per_force": "C/N",  # 전하/힘 (압전상수)
    "specific_energy": "J/kg",  # 질량당 에너지
    "crack_growth_rate": "m/cycle",  # 균열성장률
    "molar_absorptivity": "m2/mol",  # 몰흡광계수
    "gas_solubility": "mol/(m3.Pa)",  # 기체 용해도
    "volumetric_flux": "m3/(m2.s)",  # 부피 플럭스
    "melt_flow_rate": "g/600s",  # 용융흐름지수
    "mass_permeability": "kg/(m.s)",  # 질량 투과율
    "carrier_mobility": "m2/(V.s)",  # 캐리어 이동도
    "gas_permeance": "mol/(m2.s.Pa)",  # 기체 투과계수 (몰)
    "specific_wear_rate": "m3/(N.m)",  # 비마모율
    "number_density": "1/m3",  # 수밀도
    "areal_density": "kg/m2",  # 단위면적당 질량
    "gas_permeance_volumetric": "m3/(m2.s.Pa)",  # 기체 투과계수 (부피)
    "molar_volume": "m3/mol",  # 몰부피
    "hall_coefficient": "m3/C",  # 홀 계수
    "rate_constant": "m3/(mol.s)",  # 반응속도상수
    "heat_flux": "W/m2",  # 열유속
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
        _u("m2", "area", "1"),
        _u("mm2", "area", "0.000001"),
        _u("cm2", "area", "0.0001"),
        _u("N", "force", "1"),
        _u("kN", "force", "1000"),
        # 국내 현장 표기. 시험기 설정이 kgf 인 곳이 아직 있다.
        _u("kgf", "force", "9.80665"),
        _u("Pa", "stress", "1"),
        _u("kPa", "stress", "1000"),
        _u("MPa", "stress", "1000000"),
        _u("GPa", "stress", "1000000000"),
        # kgf/mm2 는 국내 성적서에, psi 는 북미 장비에 나온다.
        _u("kgf/mm2", "stress", "9806650"),
        _u("psi", "stress", "6894.757293168"),
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
        _u("J/(kg.K)", "specific_heat", "1"),
        # 실무 표기. `J/kgK` 는 규격서에서 흔하고 `kJ/(kg.K)` 는 폴리머 자료에서 흔하다.
        _u("J/kgK", "specific_heat", "1"),
        _u("kJ/(kg.K)", "specific_heat", "1000"),
        # **mm·N·tonne 계의 비열.** 그 계에서 에너지는 mJ, 질량은 tonne 이다.
        # 1 J/(kg·K) = 1e3 mJ / (1e-3 tonne · K) = 1e6 mJ/(tonne·K).
        # 덱을 그 단위계로 내보낼 때만 쓰인다(`matcore/export/systems.py`).
        _u("mJ/(tonne.K)", "specific_heat", "0.000001"),
        _u("W/(m.K)", "thermal_conductivity", "1"),
        _u("W/mK", "thermal_conductivity", "1"),
        # **mm·N·tonne 계의 열전도율.** 그 계에서 일률은 mW, 길이는 mm 이라
        # 1 W/(m·K) = 1e3 mW / (1e3 mm · K) = 1 mW/(mm·K) — **인수가 1 이다.**
        # 값이 같아도 기호는 달라야 한다. 덱에 `W/(m.K)` 라고 적어 두면 받는
        # 사람이 그 덱을 SI 로 읽는다.
        _u("mW/(mm.K)", "thermal_conductivity", "1"),
        _u("kg/m3", "density", "1"),
        _u("g/cm3", "density", "1000"),
        # 기존 앱이 쓰던 단위. 흡수 경로에서 그대로 들어온다.
        _u("tonne/mm3", "density", "1000000000000"),
        _u("1/K", "inverse_temperature", "1"),
        _u("1/Pa", "compliance", "1"),
        _u("1/MPa", "compliance", "0.000001"),
        _u("rad", "angle", "1"),
        _u("deg", "angle", "0.0174532925199433"),
        # --- 문헌 카탈로그의 SI 조합 단위. 정본은 인수 1(위 SI_UNITS 의 설명) ---
        _u("N/m", "line_force", "1"),  # 선하중 (박리·택)
        _u("mN/m", "line_force", "0.001"),
        _u("J/m2", "energy_per_area", "1"),  # 단위면적당 에너지
        _u("mJ/m2", "energy_per_area", "0.001"),
        _u("ohm.m", "resistivity", "1"),  # 체적저항률
        _u("ohm.cm", "resistivity", "0.01"),
        _u("ohm", "resistance", "1"),  # 저항
        _u("S/m", "electric_conductivity", "1"),  # 전기전도율
        _u("S/cm", "electric_conductivity", "100"),
        _u("Pa.s", "viscosity", "1"),  # 점도
        _u("mPa.s", "viscosity", "0.001"),
        _u("cP", "viscosity", "0.001"),
        _u("eV", "photon_energy", "1"),  # 준위 에너지
        _u("mol/(m.s.Pa)", "gas_permeability", "1"),  # 기체 투과도
        _u("J/mol", "molar_energy", "1"),  # 몰당 에너지
        _u("kJ/mol", "molar_energy", "1000"),
        _u("m2/s", "diffusivity", "1"),  # 확산율
        _u("mm2/s", "diffusivity", "0.000001"),
        _u("Pa.m0.5", "fracture_toughness", "1"),  # 파괴인성
        _u("MPa.m0.5", "fracture_toughness", "1000000"),
        _u("V/m", "electric_field", "1"),  # 전계 강도
        _u("kV/mm", "electric_field", "1000000"),
        _u("A/m", "magnetic_field", "1"),  # 자계 강도
        _u("kg/(m2.s)", "mass_flux", "1"),  # 질량 플럭스
        _u("T", "magnetic_flux_density", "1"),  # 자속밀도
        _u("mT", "magnetic_flux_density", "0.001"),
        _u("m2/kg", "specific_area", "1"),  # 비표면적
        _u("V", "voltage", "1"),  # 전위
        _u("J", "energy", "1"),  # 에너지
        _u("kJ", "energy", "1000"),
        _u("kg/mol", "molar_mass", "1"),  # 몰질량
        _u("g/mol", "molar_mass", "0.001"),
        _u("J/m3", "energy_density", "1"),  # 에너지 밀도
        _u("kJ/m3", "energy_density", "1000"),
        _u("K.m2/W", "thermal_resistance", "1"),  # 열저항
        _u("m3/kg", "specific_volume", "1"),  # 비체적
        _u("Pa.s/m", "acoustic_impedance", "1"),  # 음향 임피던스
        _u("J/m", "energy_per_length", "1"),  # 길이당 에너지
        _u("kJ/m", "energy_per_length", "1000"),
        _u("dB", "decibel", "1"),  # 데시벨
        _u("mol/m3", "concentration", "1"),  # 농도
        _u("C/N", "charge_per_force", "1"),  # 전하/힘 (압전상수)
        _u("pC/N", "charge_per_force", "0.000000000001"),
        _u("J/kg", "specific_energy", "1"),  # 질량당 에너지
        _u("kJ/kg", "specific_energy", "1000"),
        _u("m/cycle", "crack_growth_rate", "1"),  # 균열성장률
        _u("m2/mol", "molar_absorptivity", "1"),  # 몰흡광계수
        _u("mol/(m3.Pa)", "gas_solubility", "1"),  # 기체 용해도
        _u("m3/(m2.s)", "volumetric_flux", "1"),  # 부피 플럭스
        _u("g/600s", "melt_flow_rate", "1"),  # 용융흐름지수
        _u("g/10min", "melt_flow_rate", "1"),
        _u("kg/(m.s)", "mass_permeability", "1"),  # 질량 투과율
        _u("m2/(V.s)", "carrier_mobility", "1"),  # 캐리어 이동도
        _u("mol/(m2.s.Pa)", "gas_permeance", "1"),  # 기체 투과계수 (몰)
        _u("m3/(N.m)", "specific_wear_rate", "1"),  # 비마모율
        _u("1/m3", "number_density", "1"),  # 수밀도
        _u("kg/m2", "areal_density", "1"),  # 단위면적당 질량
        _u("m3/(m2.s.Pa)", "gas_permeance_volumetric", "1"),  # 기체 투과계수 (부피)
        _u("m3/mol", "molar_volume", "1"),  # 몰부피
        _u("m3/C", "hall_coefficient", "1"),  # 홀 계수
        _u("m3/(mol.s)", "rate_constant", "1"),  # 반응속도상수
        _u("W/m2", "heat_flux", "1"),  # 열유속
    )
}


class UnknownUnit(ValueError):
    """표에 없는 단위. 조용히 통과시키지 않기 위해 예외로 만든다."""

    def __init__(self, symbol: str) -> None:
        super().__init__(f"모르는 단위입니다: {symbol!r}")
        self.symbol = symbol


#: 같은 단위의 다른 표기. **표를 늘리지 않고 여기서 흡수한다** — `°C` 와 `degC`
#: 를 둘 다 표에 넣으면 어느 쪽이 정본인지 흐려진다.
#:
#: **`units` 에 두는 이유:** 예전에는 `readers/profile.py` 에만 있어서 장비 파일을
#: 읽을 때만 통했다. 사람이 입력 폼에 `sec` 이라고 치면 "모르는 단위" 였다 —
#: 같은 기호가 경로에 따라 되기도 하고 안 되기도 하는 상태였다.
#:
#: 키는 **소문자·공백 제거** 뒤에 맞춘다.
NOTATION_ALIASES = {
    # 마이크로: 마이크로 기호(U+00B5)와 그리스 뮤(U+03BC)가 둘 다 쓰인다.
    "µm": "um",
    "μm": "um",
    # 섭씨
    "°c": "degC",
    "℃": "degC",
    "degc": "degC",
    "°": "deg",
    # 응력
    # 면적. 위 첨자 표기가 성적서·규격서에 그대로 나온다.
    "m²": "m2",
    "mm²": "mm2",
    "cm²": "cm2",
    "m^2": "m2",
    "mm^2": "mm2",
    "n/mm2": "MPa",
    "n/mm²": "MPa",
    "n/mm^2": "MPa",
    "kgf/mm²": "kgf/mm2",
    "kg/mm2": "kgf/mm2",
    # 시간·속도
    "sec": "s",
    "1/sec": "1/s",
    "s^-1": "1/s",
    "s-1": "1/s",
    "rad/sec": "rad/s",
    # 밀도
    "g/cc": "g/cm3",
    "g/cm³": "g/cm3",
    "kg/m³": "kg/m3",
}


def _normalize(symbol: str) -> str:
    """공백을 없애고 소문자로. `mm / min` 과 `mm/min` 은 같은 것이다."""
    return "".join(symbol.split()).lower()


def _styled(symbol: str) -> str:
    """곱·거듭제곱 표기를 이 표의 것으로. **물리량은 안 바뀐다.**

    문헌 카탈로그(MaterialTwin 이관)는 `W/(m*K)`·`kg/m^3` 로 적고, 시드 스크립트와
    사람은 `W/(m·K)` 로 적었다. 이 표는 `W/(m.K)`·`kg/m3` 다. 실측(2026-09-11):
    그 차이 때문에 값으로 재료 찾기가 열전도율·비열·밀도(3,591건)에서 「차원이
    다릅니다」 로 막혔고, 선언 물성 147건이 화면에 단위 없이 떴다 — 전부 같은
    단위였다. 곱 기호 셋과 캐럿을 지우는 것뿐이라 다른 단위로 바뀔 길이 없다.
    """
    return symbol.replace("*", ".").replace("·", ".").replace("⋅", ".").replace("^", "")


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
        key = _normalize(symbol)
        index[key] = "" if key in index else symbol
    return {key: symbol for key, symbol in index.items() if symbol}


CASE_INDEX = _case_index()


def loose_key(symbol: str) -> str:
    """표기 차이를 다 지운 비교용 열쇠. **환산에는 안 쓴다** — 같은 글자인지만 본다."""
    return _normalize(_styled(symbol.strip()))


def canonical(symbol: str) -> str | None:
    """표기가 조금 다른 단위를 정본 심볼로. 모르면 `None`.

    순서가 있다. **정확히 맞는 것이 먼저다** — 아래로 갈수록 추측이 섞이므로,
    위에서 걸리면 아래를 보지 않는다.

    1. 표에 그대로 있는가
    2. 알려진 다른 표기인가 (`N/mm2`, `sec`, `µm`)
    3. 대소문자만 다른가 (`mpa` → `MPa`, 충돌하면 안 함)

    **모르면 `None` 이다. 비슷한 것을 고르지 않는다.** `C` 는 섭씨일 수도
    쿨롱일 수도 있어서 받지 않는다 — 추측해서 맞히면 다음번에 틀린다.
    """
    text = symbol.strip()
    if text in UNITS:
        return text
    key = _normalize(text)
    alias = NOTATION_ALIASES.get(key)
    if alias:
        return alias
    found = CASE_INDEX.get(key)
    if found:
        return found
    # 4. 곱·거듭제곱 표기만 다른가 (`W/(m*K)`·`kg/m^3`·`J/(kg·K)`)
    styled = _styled(text)
    if styled != text:
        return canonical(styled)
    return None


def unit_of(symbol: str) -> Unit:
    """기호로 단위를. **표기가 조금 달라도 받는다** — `canonical` 이 아는 만큼.

    전에는 정본 기호만 받았다. 그래서 `canonical` 로 걸러 둔 값도 환산 함수에
    원래 기호를 넘기면 거기서 다시 막혔고(값으로 찾기 — `bounds` 는 통과하고
    `from_si` 가 던졌다), 시드가 넣은 `W/(m·K)` 는 읽을 때마다 단위가 지워졌다.
    모르는 것은 여전히 모른다 — 추측은 `canonical` 이 안 한다.
    """
    exact = UNITS.get(symbol)
    if exact is not None:
        return exact
    found = canonical(symbol)
    if found is None:
        raise UnknownUnit(symbol)
    return UNITS[found]


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
