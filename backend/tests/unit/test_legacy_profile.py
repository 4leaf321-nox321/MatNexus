"""옛 앱 파일을 읽는 기본 프로파일 — **실파일 107개에서 정해진 것들.**

MatNexus 를 쓰기 시작한다는 것은 옛 앱(`MaterialAppVer2`)에 쌓인 것을 옮긴다는
뜻이다. 그 파일 형식은 하나이고 모양이 정해져 있으므로, 설치마다 사람이 40줄짜리
정의를 손으로 다시 적게 두지 않는다.

실측(`002_Material` 의 `.mtet` 107개): 데이터가 든 88개 전부 경고 없이 채널 3개로
읽혔고, 나머지 19개는 Raw Data 가 없는 껍데기라 옳게 거절됐다.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.modules.tests.legacy_profiles import LEGACY_TENSILE_DEFINITION
from app.shared.curvedata import instrument_dimensions
from matcore.parsers import Channel, ParseError, SummaryValue
from matcore.readers import profile as profiles
from matcore.readers import sniff

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
WITH_UNITS = FIXTURES / "legacy_tensile.mtet"
WITHOUT_UNITS = FIXTURES / "legacy_tensile_nounit.mtet"


def channels(path: Path) -> dict[str, Channel]:
    parsed = profiles.apply(LEGACY_TENSILE_DEFINITION, path.read_bytes())
    return {channel.key: channel for channel in parsed.curves[0].channels}


class Test지문:
    def test_확장자와_열_이름을_함께_본다(self) -> None:
        structure = sniff(WITH_UNITS.read_bytes())
        assert profiles.matches(
            LEGACY_TENSILE_DEFINITION, filename="Test1.mtet", structure=structure
        )

    def test_확장자가_다르면_안_잡는다(self) -> None:
        """`.csv` 는 어느 장비나 쓴다. 지문이 헐거우면 남의 파일을 읽는다."""
        structure = sniff(WITH_UNITS.read_bytes())
        assert not profiles.matches(
            LEGACY_TENSILE_DEFINITION, filename="Test1.csv", structure=structure
        )


class Test채널매핑:
    def test_세_채널이_SI_로_들어온다(self) -> None:
        found = channels(WITH_UNITS)
        assert set(found) == {"displacement", "force", "specimen_width"}
        assert found["displacement"].si_unit == "m"
        assert found["force"].si_unit == "N"
        # 12.473 mm → 0.012473 m
        assert found["specimen_width"].values[0] == pytest.approx(0.012473)

    def test_행_번호_열은_버린다(self) -> None:
        """**안 버리면 단위 모르는 채널이 하나 낀다.** 곡선 고르는 자리에 뜻 없는
        계열이 뜨고, 그게 무엇인지 매번 묻게 된다. 실측 파일 전부에 이 열이 있다."""
        assert "unnamed" not in channels(WITH_UNITS)

    def test_단위가_열_이름에_없어도_읽는다(self) -> None:
        """**같은 열이 파일에 따라 단위를 달고도 안 달고도 온다**(실측 55회 대 33회).
        하나만 적으면 나머지가 "단위를 알 수 없는 열" 로 등록을 거부당한다."""
        found = channels(WITHOUT_UNITS)
        assert set(found) == {"displacement", "force", "specimen_width"}
        assert found["specimen_width"].values[0] == pytest.approx(0.012473)


class Test옛_앱의_답을_버리지_않는다:
    """같은 곡선을 MatNexus 가 처리한 결과와 나란히 놓고 볼 수 있어야 한다 —
    실파일로 하는 교차검증이고, 합성 데이터로는 못 사는 확신이다."""

    def summary(self, path: Path) -> dict[str, SummaryValue]:
        parsed = profiles.apply(LEGACY_TENSILE_DEFINITION, path.read_bytes())
        return {item.key: item for item in parsed.summary}

    def test_계산값이_SI_로_들어온다(self) -> None:
        found = self.summary(WITH_UNITS)
        # 282.128 MPa → 282128000 Pa. **10⁶ 배 틀리면 숫자는 멀쩡해 보인다.**
        assert found["legacy_tensile_strength"].value == pytest.approx(282.128e6)
        assert found["legacy_proof_stress"].value == pytest.approx(159.979e6)

    def test_우리_값과_이름이_안_섞인다(self) -> None:
        """`legacy_` 를 붙이는 이유. `proof_stress` 로 들어오면 우리가 계산한
        항복강도와 한 칸에서 만나 어느 쪽인지 알 수 없게 된다."""
        assert all(key.startswith("legacy_") for key in self.summary(WITH_UNITS))

    def test_모르는_값을_0_으로_만들지_않는다(self) -> None:
        """옛 앱은 못 구한 값을 `Unknown` 으로 적는다. 숫자로 바꾸면 '항복강도
        0 MPa' 인 재료가 생긴다."""
        found = self.summary(WITH_UNITS)
        assert found["legacy_yield_strain"].value is None
        assert found["legacy_yield_strain"].text == "Unknown"


class Test시편치수:
    def test_시험이_실제로_쓴_값을_쓴다(self) -> None:
        """`a0`·`b0` 는 그 시험이 쓴 치수다. 시험 조건에 적힌 입력값이 아니다 —
        치수는 시편의 것이다(ADR 0004)."""
        parsed = profiles.apply(LEGACY_TENSILE_DEFINITION, WITH_UNITS.read_bytes())
        assert parsed.metadata["specimen_thickness"] == "0.986"
        assert parsed.metadata["specimen_width"] == "12.473"

    def test_치수가_시편까지_닿는다(self) -> None:
        """**여기까지 봐야 한다.** 전에는 위 시험 하나뿐이었고, 메타에 값이
        들어간 것만 확인했다. 그래서 그 값이 시편으로 못 가는 것을 못 잡았다 —
        읽는 쪽은 숫자만 있고 단위를 모르면 포기하는데(`_as_metres`), 이 파일은
        단위를 **열 이름 안에**만 갖고 있다.

        증상이 조용하다: 치수가 안 채워져도 오류가 없고, 세 단계 뒤 처리
        1단계의 `@specimen_area` 가 "그 값이 없습니다" 로 멈춘다.
        """
        parsed = profiles.apply(LEGACY_TENSILE_DEFINITION, WITH_UNITS.read_bytes())
        found = instrument_dimensions(parsed.metadata)
        assert found["thickness"] == pytest.approx(0.000986)
        assert found["width"] == pytest.approx(0.012473)

    def test_단위를_안_적으면_안_채운다(self) -> None:
        """**mm 라고 가정하지 않는다.** m 로 적은 파일에서 1000배 틀린 시편이
        만들어지고, 그 뒤 응력이 통째로 어긋나는데 숫자는 그럴듯해 보인다."""
        bare = {**LEGACY_TENSILE_DEFINITION}
        bare["specimen"] = {"Specimen thickness a0 (mm)": "specimen_thickness"}
        parsed = profiles.apply(bare, WITH_UNITS.read_bytes())
        assert parsed.metadata["specimen_thickness"] == "0.986"
        assert "thickness" not in instrument_dimensions(parsed.metadata)

    def test_파일에_붙어_온_단위가_선언을_이긴다(self) -> None:
        """선언은 힌트이고 **파일이 증거다.** 값에 단위가 붙어 오는 장비가 있다
        (TA DMA850 의 `50.0 mm`) — 그때 프로파일의 선언이 이기면, 소프트웨어
        설정을 바꿔 단위가 달라진 파일을 옛 단위로 읽는다."""
        told = {**LEGACY_TENSILE_DEFINITION}
        told["specimen"] = {
            "Specimen thickness a0 (mm)": {"key": "specimen_thickness", "unit": "m"}
        }
        parsed = profiles.apply(told, WITH_UNITS.read_bytes())
        # 파일은 `"0.986"` 하나뿐이라 선언(m)이 쓰인다.
        assert instrument_dimensions(parsed.metadata)["thickness"] == pytest.approx(0.986)


class Test껍데기파일:
    def test_데이터가_없으면_거절한다(self) -> None:
        """실측 107개 중 19개가 이것이다 — Raw Data 가 없는 템플릿."""
        empty = b'{"tensile-test": {"Test Condition": {"Specimen Number": "1"}}}'
        with pytest.raises((ParseError, ValueError)):
            profiles.apply(LEGACY_TENSILE_DEFINITION, empty)
