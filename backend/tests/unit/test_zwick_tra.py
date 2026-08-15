"""Zwick `.tra` 파서 — 실측 코퍼스에서 나온 함정들.

`002_Material` 전체를 훑어 얻은 사실이 근거다: 확장자 `.tra`/`.TRA` 파일이 44개
있지만 **내용은 단 2종**이고, 그중 하나(`Example2.tra`)는 하중 열 9곳의 앞자리가
잘려 나간 손상본이다. 손상본은 **문법상 완전히 정상이라 파싱에 성공한다** —
그래서 파서로는 막을 수 없고, 그 사실을 알고 다음 단계에서 걸러야 한다.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from matcore.parsers import ParsedTest, ParseError, zwick_tra

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
GOOD = FIXTURES / "Example.tra"
CORRUPT = FIXTURES / "Example2_corrupt.tra"


def _parse(path: Path) -> ParsedTest:
    return zwick_tra.parse(path.read_bytes())


class TestRealFile:
    def test_구조를_줄번호로_고정하지_않는다(self) -> None:
        """요약 항목 수는 장비 설정에 따라 달라진다. 줄 번호를 박으면 항목이
        하나 늘어난 파일에서 **채널 이름 자리에 요약값이 들어와도 파싱은
        성공한다** — 그런 실패가 가장 나쁘다."""
        parsed = _parse(GOOD)
        assert parsed.row_count == 18  # 파일 끝에 개행이 없어도 마지막 행이 산다
        assert [c.key for c in parsed.channels] == ["displacement", "force", "specimen_width"]

    def test_단위를_SI_로_바꾼다(self) -> None:
        parsed = _parse(GOOD)
        displacement = parsed.channel("displacement")
        assert displacement is not None
        assert displacement.source_unit == "mm"
        assert displacement.si_unit == "m"
        assert displacement.values[-1] == pytest.approx(0.0200037)  # 20.0037 mm

    def test_지수표기를_읽는다(self) -> None:
        """`1.46484e-007` — MSVC 서식(3자리 지수)이 데이터 첫 행에 실재한다."""
        parsed = _parse(GOOD)
        displacement = parsed.channel("displacement")
        assert displacement is not None
        assert displacement.values[0] == pytest.approx(1.46484e-10)  # mm → m

    def test_단위_칸이_없는_줄을_견딘다(self) -> None:
        """`"Yield strain","Unknown"` — 값이 Unknown 이면 단위 칸 자체가 없다.
        `row[2]` 를 무조건 읽으면 IndexError 가 난다."""
        parsed = _parse(GOOD)
        unknowns = [s for s in parsed.summary if s.text == "Unknown"]
        assert {s.key for s in unknowns} == {"yield_strain", "upper_yield", "lower_yield"}
        assert all(s.value is None for s in unknowns)

    def test_따옴표_유무가_값_종류를_뜻하지_않는다(self) -> None:
        """같은 숫자 0.234727 이 한 줄에서는 `"0.234727"`, 다음 줄에서는 맨값이다."""
        parsed = _parse(GOOD)
        by_key = {s.key: s for s in parsed.summary}
        assert by_key["hardening_n"].value == pytest.approx(0.234727)
        assert by_key["anisotropy_r"].value == pytest.approx(0.234727)

    def test_이름이_Force_여도_단위가_MPa_면_응력이다(self) -> None:
        """282.128 MPa 는 Fmax/A0 와 0.1% 안에서 맞는다
        (3466.4 N / (0.986 * 12.473) mm2 = 281.9 MPa). 힘이 아니다."""
        parsed = _parse(GOOD)
        by_key = {s.key: s for s in parsed.summary}
        assert "force_maximum" not in by_key
        assert by_key["tensile_strength"].value == pytest.approx(282_128_000.0)
        assert by_key["tensile_strength"].si_unit == "Pa"

    def test_시편_치수는_결과가_아니라_입력이다(self) -> None:
        """`Specimen thickness a0` 는 시험 결과가 아니다. 요약값에 섞으면
        나중에 '우리가 계산한 두께' 같은 것이 생긴다.

        키에 `_a0`·`_b0` 를 붙이는 이유는 **채널 이름과 겹치기 때문**이다 —
        곡선의 `specimen_width` 는 시험 중 계속 변하는 값이고, `b0` 는 초기값이다.
        """
        parsed = _parse(GOOD)
        assert parsed.metadata["specimen_thickness_a0"] == "0.986"
        assert parsed.metadata["specimen_width_b0"] == "12.473"
        assert "specimen_width" not in parsed.metadata
        assert not any(s.key.startswith("specimen_") for s in parsed.summary)

    def test_센서가_놓친_구간을_경고한다(self) -> None:
        """마지막 두 행의 폭이 0.0 이다. 진응력은 폭으로 나눈다."""
        parsed = _parse(GOOD)
        assert any("specimen_width" in w for w in parsed.warnings)


class TestCorruptVariant:
    def test_손상본도_문법상_정상이라_파싱에_성공한다(self) -> None:
        """`Example2.tra` 는 하중 열 9곳의 앞자리가 잘려 있다(486.745 → 6.745).
        파서는 이것을 막을 수 없다 — 막으려 하면 정상 파일도 걸린다."""
        parsed = _parse(CORRUPT)
        assert parsed.row_count == 18

    def test_피크_이전_하중_감소로만_갈린다(self) -> None:
        """**단조증가로 검증하면 안 된다.** 정상 파일도 피크 이후에는 하중이
        내려간다(네킹). 쓸 수 있는 규칙은 '최대 하중 이전 구간에서 비감소' 뿐이고,
        그 규칙으로 두 파일이 깨끗이 갈린다.

        이 검사 자체는 Phase 3(처리)의 몫이다. 여기서는 그 규칙이 실제로
        성립한다는 사실만 못박는다.
        """

        def drops_before_peak(path: Path) -> int:
            channel = _parse(path).channel("force")
            assert channel is not None
            force = [v for v in channel.values if v is not None]
            peak = force.index(max(force))
            return sum(1 for i in range(1, peak + 1) if force[i] < force[i - 1])

        assert drops_before_peak(GOOD) == 0
        assert drops_before_peak(CORRUPT) == 5


class TestFailures:
    @pytest.mark.parametrize(
        ("label", "data"),
        [
            ("빈 파일", b""),
            ("형식이 아예 다름", b"garbage,not,a,tra\nmore garbage\n"),
            ("헤더 없이 숫자만", b"1,2\n3,4\n5,6\n"),
        ],
    )
    def test_읽을_수_없으면_이유와_함께_실패한다(self, label: str, data: bytes) -> None:
        """조용히 잘못 읽는 쪽이 훨씬 나쁘다. 잘못 읽힌 곡선은 그럴듯해 보여서
        나중에 찾아낼 수 없고, 그 곡선으로 적합한 물성이 해석에 들어간다."""
        with pytest.raises(ParseError) as caught:
            zwick_tra.parse(data)
        assert str(caught.value)  # 메시지가 비어 있으면 사람이 볼 것이 없다

    def test_이름_단위_열_개수가_어긋나면_실패한다(self) -> None:
        mismatched = b'"A","B","C"\n"mm","N"\n1,2,3\n4,5,6\n'
        with pytest.raises(ParseError, match="맞지 않습니다"):
            zwick_tra.parse(mismatched)


class TestEuropeanLocale:
    """독일 로케일 장비는 `;` 로 나누고 소수점에 `,` 를 쓴다.

    코퍼스에 사례가 0건이라 **미검증 경로**였다. 여기서 픽스처로 고정한다 —
    검증되지 않은 코드가 계약처럼 보이는 것이 위험하기 때문이다.
    """

    EURO = (
        b'"Force maximum";282,128;"MPa"\n'
        b'"Standard extensometer";"Standard load cell"\n'
        b'"mm";"N"\n'
        b"1,5;19,4\n"
        b"2,5;486,7\n"
        b"1.234,5;913,8\n"
    )

    def test_쉼표_소수점을_읽는다(self) -> None:
        parsed = zwick_tra.parse(self.EURO)
        displacement = parsed.channel("displacement")
        assert displacement is not None
        assert displacement.values[0] == pytest.approx(0.0015)  # 1,5 mm → m
        assert displacement.values[2] == pytest.approx(1.2345)  # 1.234,5 mm → m

    def test_천단위_점이_지수표기를_망가뜨리지_않는다(self) -> None:
        """`text.replace('.', '')` 를 조건 없이 하면 `1.46484e-007` 이
        `146484e-007` 이 되어 값이 10^5 배 어긋난 채로 **파싱은 성공한다.**"""
        assert zwick_tra._to_float("1.46484e-007", ";") == pytest.approx(1.46484e-7)
        assert zwick_tra._to_float("1.234,5", ";") == pytest.approx(1234.5)


class TestSummaryKeys:
    def test_같은_항목이_두_번_오면_구분한다(self) -> None:
        """`{...}` 를 떼서 key 를 만들기 때문에 `k{lo 5 - 10}` 과 `k{lo 10 - 15}`
        가 함께 오면 둘 다 `hardening_k` 가 된다. 그러면
        `uq_test_summaries_run_key` 를 위반해 **파일 전체가 저장되지 않는다.**
        """
        data = (
            b'"Work hardening coefficient k{lo  5 - 10}","400.0","MPa"\n'
            b'"Work hardening coefficient k{lo  10 - 15}","501.871","MPa"\n'
            b'"Standard extensometer","Standard load cell"\n'
            b'"mm","N"\n'
            b"0.1,10\n0.2,20\n"
        )
        parsed = zwick_tra.parse(data)
        keys = [s.key for s in parsed.summary]
        assert keys[0] == "hardening_k"  # 첫 번째는 안정적인 key 를 유지한다
        assert len(set(keys)) == len(keys)
        assert any("구분했습니다" in w for w in parsed.warnings)


class TestEncoding:
    """**인코딩은 자동으로 판정할 수 없다.**

    실측으로 확인한 것: cp949 는 `\\x81\\x8d` 같은 바이트쌍을 멀쩡히 받아들이고
    cp1252 는 정의되지 않은 5바이트를 빼면 무엇이든 받는다. 폴백 사슬 끝에
    단일바이트 코덱을 두면 UnicodeDecodeError 는 사실상 나지 않는다.

    그래서 판정하는 척하지 않고, 추측했다는 사실을 경고로 드러낸다.
    """

    HEADER = b'"Standard extensometer","Standard load cell"\n"mm","N"\n0.1,10\n0.2,20\n'

    def test_UTF8_이면_경고가_없다(self) -> None:
        assert zwick_tra.parse(self.HEADER).warnings == ()

    def test_UTF8_이_아니면_추측했다고_알린다(self) -> None:
        """조용히 통과하면 숫자는 멀쩡한데 라벨만 깨지고, 그런 실패는 발견이
        가장 늦다. 경고는 시험 상세 화면에 그대로 뜬다."""
        latin = '"Prüfer";"Kraft"\n"mm";"N"\n0,1;10\n0,2;20\n'.encode("cp1252")
        parsed = zwick_tra.parse(latin)
        assert any("CP1252" in w for w in parsed.warnings)

    def test_어느_쪽으로도_못_읽으면_거절한다(self) -> None:
        undecodable = b"\x81\x8d\x90\x9d" * 8  # cp1252 에 정의되지 않은 바이트들
        with pytest.raises(ParseError, match="인코딩"):
            zwick_tra.parse(undecodable)
