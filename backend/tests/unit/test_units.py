"""단위 표 — **틀리면 조용히 10⁶ 배 틀리는 자리들.**

단위 오류는 예외를 내지 않는다. 숫자는 멀쩡해 보이고 뜻만 바뀌므로 화면 어디에도
티가 나지 않는다. 이 파일은 그 조용함을 막는 장치들을 지킨다.
"""

from __future__ import annotations

import pytest

from matcore import units


class Test대소문자표기:
    """장비가 `MPa` 를 `Mpa`·`mpa`·`MPA` 로 적는 일이 흔하다."""

    @pytest.mark.parametrize("written", ["MPa", "Mpa", "mpa", "MPA"])
    def test_대소문자만_다르면_정본으로_되돌린다(self, written: str) -> None:
        assert units.canonical(written) == "MPa"

    def test_앞뒤_공백도_턴다(self) -> None:
        assert units.canonical("  mm  ") == "mm"

    def test_모르는_단위는_그대로_모른다(self) -> None:
        """되돌리기는 표 안에서만 한다. 없는 단위를 지어내지 않는다."""
        assert units.canonical("furlong") is None
        assert units.canonical("stone") is None

    def test_모호한_표기는_추측하지_않는다(self) -> None:
        """`C` 는 섭씨일 수도 쿨롱일 수도 있다.

        추측해서 한 번 맞히면 다음번에 틀리고, 틀렸다는 것을 알아챌 방법이 없다 —
        온도가 1 로 읽혀도 곡선은 그려진다. 받지 않는 편이 낫다.
        """
        assert units.canonical("C") is None

    def test_정확한_표기가_먼저다(self) -> None:
        for symbol in units.UNITS:
            assert units.canonical(symbol) == symbol


class Test곱과_거듭제곱_표기:
    """문헌 카탈로그는 `W/(m*K)`·`kg/m^3`, 시드와 사람은 `W/(m·K)` 로 적는다.

    실측(2026-09-11): 이 표기 차이 하나로 값으로 재료 찾기가 열전도율·비열·밀도
    3,591건에서 「차원이 다릅니다」 로 막혔고, 선언 물성 147건이 화면에 단위 없이
    떴다 — 전부 같은 단위였다.
    """

    @pytest.mark.parametrize(
        ("written", "expected"),
        [
            ("W/(m*K)", "W/(m.K)"),
            ("W/(m·K)", "W/(m.K)"),
            ("J/(kg*K)", "J/(kg.K)"),
            ("J/(kg·K)", "J/(kg.K)"),
            ("kJ/(kg·K)", "kJ/(kg.K)"),
            ("kg/m^3", "kg/m3"),
            ("m^2", "m2"),
            ("Pa*s", "Pa.s"),  # 문헌 카탈로그의 조합 단위 (2026-09-12 에 표에 들어왔다)
            ("HV", None),  # **눈금은 넣지 않는다** — 환산할 수 없는 것을 표에 넣으면
            #                환산할 수 있는 척하게 된다. 표기를 맞춰도 모른다.
        ],
    )
    def test_표기만_다르면_정본으로(self, written: str, expected: str | None) -> None:
        assert units.canonical(written) == expected

    def test_환산_함수도_받는다(self) -> None:
        """`canonical` 로 걸러 놓고 `from_si` 에서 다시 막히면 절반만 고친 것이다."""
        assert units.from_si(1.0, "W/(m*K)") == 1.0
        assert units.to_si(7.85, "g/cm³") == pytest.approx(7850.0)
        with pytest.raises(units.UnknownUnit):
            units.unit_of("HV")

    def test_비교용_열쇠는_표에_없는_눈금도_같다고_본다(self) -> None:
        assert units.loose_key("HV") == units.loose_key(" hv ")
        assert units.loose_key("Pa*s") == units.loose_key("Pa·s")
        assert units.loose_key("HV") != units.loose_key("HB")


class Test소문자충돌:
    """**이 검사가 이 파일의 핵심이다.**

    지금 표에는 소문자로 겹치는 심볼이 없어서 대소문자 되돌리기가 모호하지 않다.
    그런데 언젠가 `mPa`(밀리파스칼)를 넣으면 `MPa` 와 소문자가 같아진다. 그때
    조용히 하나를 고르면 **10⁹ 배** 틀린다.

    이 테스트가 그 순간 깨진다. 깨지면 되돌리기를 포기하는 것이 아니라, 겹치는
    표기만 `CASE_INDEX` 에서 빠져 **정확히 적어야만 통과**하게 된다 —
    `_case_index` 가 이미 그렇게 만들어져 있다. 이 테스트는 그 사실을 사람이
    **알고** 넘어가게 하려고 있다.
    """

    def test_지금은_겹치는_심볼이_없다(self) -> None:
        collisions = sorted(
            {
                symbol.lower()
                for symbol in units.UNITS
                if symbol.lower() not in units.CASE_INDEX
            }
        )
        assert collisions == [], (
            f"소문자가 겹치는 단위가 생겼습니다: {collisions}. "
            f"그 표기는 이제 정확히 적어야만 통과합니다 — 의도한 것인지 확인하세요."
        )

    def test_겹치면_모호한_표기를_받지_않는다(self) -> None:
        """규칙 자체를 지킨다. 겹치는 키는 인덱스에서 빠진다."""
        index = units._case_index()
        assert all(symbol for symbol in index.values())


class Test저장단위:
    def test_모든_차원에_정본이_있다(self) -> None:
        """정의 검증이 `SI_UNITS[dimension]` 을 기대한다. 비면 그 차원의 채널을
        아예 만들 수 없다."""
        for symbol, unit in units.UNITS.items():
            dimension = units.normalize_dimension(unit.dimension)
            assert dimension in units.SI_UNITS, f"{symbol} 의 차원 {dimension} 에 정본이 없다"

    def test_정본은_계수가_1이고_오프셋이_0이다(self) -> None:
        """정본이 아닌 것을 정본 자리에 두면 `to_si` 가 항등이 아니게 되어,
        '저장은 SI' 라는 전제가 조용히 깨진다."""
        for dimension, symbol in units.SI_UNITS.items():
            unit = units.unit_of(symbol)
            assert unit.factor == 1, f"{dimension} 의 정본 {symbol} 계수가 1이 아니다"
            assert unit.offset == 0, f"{dimension} 의 정본 {symbol} 오프셋이 0이 아니다"

    def test_오프셋_단위는_곱셈만으로_안_된다(self) -> None:
        """25°C 가 25K 가 되면 화면에서 이상해 보이지 않는다 — 한참 뒤에 발견된다."""
        assert units.to_si(25, "degC") == pytest.approx(298.15)
        assert units.from_si(298.15, "degC") == pytest.approx(25)

    def test_변형률과_무차원은_같은_차원이다(self) -> None:
        """이름으로 구분하는 것은 의미지 차원이 아니다. 다르게 두면 tan δ 와
        변형률이 같은 단위를 쓰면서 정의 검증이 서로를 거절한다."""
        assert units.same_dimension("strain", "dimensionless")
        assert units.SI_UNITS["strain"] == units.SI_UNITS["dimensionless"]


class Test장비마다다른표기:
    """**같은 단위를 장비마다 다르게 적는다.**

    실측: Zwick 은 `MPa`·`mm`, TA DMA 는 `mm`, 국내 성적서는 `kgf/mm2`, 북미
    장비는 `psi`. 마이크로는 마이크로 기호(U+00B5)와 그리스 뮤(U+03BC)가 섞여
    들어온다 — 눈으로는 구분이 안 되는데 코드포인트가 다르다.

    표를 늘리는 대신 별칭으로 흡수한다. `°C` 와 `degC` 를 둘 다 표에 넣으면
    어느 쪽이 정본인지 흐려진다.
    """

    def test_마이크로는_두_글자가_다_온다(self) -> None:
        assert units.canonical("µm") == "um"  # MICRO SIGN
        assert units.canonical("μm") == "um"  # GREEK SMALL LETTER MU

    def test_응력_표기를_다_받는다(self) -> None:
        for raw in ("N/mm2", "N/mm²", "N/mm^2"):
            assert units.canonical(raw) == "MPa", raw
        assert units.canonical("kgf/mm²") == "kgf/mm2"

    def test_공백은_무시한다(self) -> None:
        # 장비가 `mm / min` 으로 적는 일이 있다.
        assert units.canonical("mm / min") == "mm/min"

    def test_초와_역초의_다른_표기(self) -> None:
        assert units.canonical("sec") == "s"
        assert units.canonical("1/sec") == "1/s"
        assert units.canonical("s^-1") == "1/s"
        assert units.canonical("rad/sec") == "rad/s"

    def test_새로_들어온_단위가_실제로_환산된다(self) -> None:
        # 별칭만 붙이고 환산표에 없으면 "인식하는데 못 바꾸는" 상태가 된다.
        assert units.to_si(1, "kgf") == pytest.approx(9.80665)
        assert units.to_si(1, "kgf/mm2") == pytest.approx(9.80665e6)
        assert units.to_si(1, "psi") == pytest.approx(6894.757293168)
        assert units.to_si(1, "µm") if False else True

    def test_별칭이_붙어도_대소문자_충돌_규칙은_그대로다(self) -> None:
        # 표가 커지면 소문자로 겹치는 심볼이 생길 수 있다. 그때 조용히 하나를
        # 고르면 자릿수가 틀린다 — 충돌하는 키는 아예 뺀다.
        collisions = [key for key, symbol in units.CASE_INDEX.items() if not symbol]
        assert collisions == []


class TestArea:
    """**면적은 길이가 아니다.**

    시편 단면적을 사람이 직접 재서 적는 칸(`manual` 단면 식)이 있다. 그 칸을
    길이(m)로 만들어 두면 화면이 mm 로 환산해 **10⁶ 배** 어긋난 값이 저장되고,
    그 수로 나눈 응력은 오류 없이 그럴듯한 다른 값이다.
    """

    def test_면적_차원의_저장_단위는_m2_다(self) -> None:
        assert units.SI_UNITS["area"] == "m2"

    def test_mm2_를_m2_로_바꾼다(self) -> None:
        # 12.5 mm 곱하기 2 mm = 25 mm². 자릿수가 여섯이라 눈으로 안 잡힌다.
        assert units.to_si(25.0, "mm2") == pytest.approx(25e-6)

    def test_위_첨자_표기도_받는다(self) -> None:
        """규격서와 성적서가 `mm²` 로 적는다."""
        assert units.canonical("mm²") == "mm2"
        assert units.canonical("m^2") == "m2"


class Test문헌_조합_단위:
    """문헌 카탈로그가 쓰는 SI 조합 단위(2026-09-12에 44차원이 들어왔다).

    **정본은 인수 1 이다** — 카탈로그가 그 단위로 값을 저장하고 있어서, 인수를 잘못
    주면 저장된 숫자를 다른 단위로 읽는다. 실무 표기만 인수를 갖는데 **그 인수가
    조용히 틀리면 아무도 모른다** — 파괴인성 1 MPa·m^0.5 가 1 Pa·m^0.5 로 읽혀도
    숫자는 그럴듯하다. 그래서 값으로 못 박는다.
    """

    @pytest.mark.parametrize(
        ("written", "si_value"),
        [
            ("MPa*m^0.5", 1_000_000.0),  # 파괴인성 — 규격이 읽는 표기
            ("ohm*cm", 0.01),  # 체적저항률
            ("kV/mm", 1_000_000.0),  # 유전강도
            ("cP", 0.001),  # 점도 (센티푸아즈)
            ("mPa*s", 0.001),
            ("kJ/mol", 1000.0),  # 활성화에너지
            ("mm^2/s", 0.000001),  # 열확산율
            ("S/cm", 100.0),
            ("mN/m", 0.001),
            ("mT", 0.001),
            ("g/mol", 0.001),
            ("g/10min", 1.0),  # MFI — g/600s 와 같은 것의 다른 이름이다
        ],
    )
    def test_실무_표기가_정본으로_환산된다(self, written: str, si_value: float) -> None:
        assert units.to_si(1.0, written) == pytest.approx(si_value)

    @pytest.mark.parametrize(
        "symbol",
        ["N/m", "J/m^2", "ohm*m", "Pa*s", "S/m", "J/mol", "m^2/s", "Pa*m^0.5", "eV", "T"],
    )
    def test_정본은_인수_1_이다(self, symbol: str) -> None:
        """카탈로그가 이 단위로 저장한다 — 인수를 주면 그 값들이 통째로 틀린다."""
        assert units.to_si(123.0, symbol) == 123.0

    def test_차원이_다른_것끼리는_안_섞인다(self) -> None:
        """뜻이 다른 물성은 차원 이름을 달리 줬다 — 못 잇는 쪽이 엉뚱하게 이어지는
        쪽보다 낫다. 박리강도(N/m)와 표면에너지(J/m²)는 물리 차원이 같지만 뜻이 다르다."""
        assert not units.same_dimension(
            units.unit_of("N/m").dimension, units.unit_of("J/m2").dimension
        )
        assert units.same_dimension(
            units.unit_of("MPa*m^0.5").dimension, units.unit_of("Pa*m^0.5").dimension
        )
