"""사람이 읽는 이름을 값에서 결정적으로 조합한다.

이름은 **참조 키가 아니다.** 참조는 UUID가 맡고, 여기서 만드는 문자열은 목록과
로그에서 사람이 알아보는 용도, 그리고 "같은 것을 두 번 등록했는가"를 DB가
막는 용도(유니크 제약)만 맡는다.

기존 앱(MaterialAppVer2 `generateIdFromLabels`)을 읽고 확인한 함정을 여기서
막는다. 24줄짜리 함수였는데 아래가 전부 거기서 나왔다.

1. **빈 값이 자리를 남기지 않고 사라졌다** (`.filter(v => v)`).
   두께를 비워 두고 등록하면 `SECC_MDOI_MD`, 나중에 채우면 `SECC_MDOI_1.0_MD`.
   그런데 그 이름은 하위 시험 ID에 통째로 복사돼 있어서 연결이 끊어졌다.
   → 빈 값은 자리표시자 `-` 로 채운다. **칸 수가 절대 변하지 않는다.**

2. **이름 끝에 타임스탬프와 6자리 난수가 붙었다.**
   같은 파일을 다시 올리면 다른 이름이 나와, 중복인지 이름으로 판정할 수 없었다.
   게다가 `Record Name` 과 `Data ID` 가 규칙이 같은데 난수를 각자 뽑아,
   같은 시험을 가리키는 두 값이 달랐다(`..._316791` vs `..._666427`).
   → 이 모듈의 함수는 전부 순수하다. 같은 입력이면 같은 이름이다.

3. **정제가 `trim()` 뿐이었다.** 생산일 `2025/06/19` 가 그대로 들어가 ID에
   슬래시가 섞였다(`SampleType_8_9_..._2025/06/19`). 파일 경로로 못 쓴다.
   → 구분자와 경로 금지문자를 `-` 로 바꾼다.

4. **값을 화면(DOM)에서 라벨 텍스트로 찾아 읽었다.** 그래서 화면 없이는 이름을
   만들 수 없었고, 탭이 안 그려졌으면 값이 조용히 빠져 1번으로 이어졌다.
   → 이 모듈은 값만 받는다. DB도 HTTP도 화면도 모른다.
"""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

#: 한 계층 안에서 필드를 나눈다.
FIELD_SEP = "_"

#: 계층을 나눈다. 값에서 `_` 를 없애므로 이 경계는 절대 모호해지지 않는다.
LAYER_SEP = "__"

#: 값이 없는 칸. 칸을 없애지 않고 채우는 것이 핵심이다(위 1번).
PLACEHOLDER = "-"

#: 이름에 남길 문자. 나머지는 전부 `-` 가 된다.
#: `_` 를 뺀 것이 의도다 — 값이 구분자를 만들어 내면 계층 경계가 무너진다.
_ALLOWED = r"0-9A-Za-z가-힣.+-"
_INVALID = re.compile(rf"[^{_ALLOWED}]+")
_REPEATED_DASH = re.compile(r"-{2,}")


def sanitize(value: object) -> str:
    """값 하나를 이름 조각으로 바꾼다. 비어 있으면 빈 문자열을 준다.

    호출부가 빈 결과를 자리표시자로 바꿀지 판단해야 하므로, 여기서는 채우지
    않는다. `field()` 가 그 판단을 한다.
    """
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    text = _INVALID.sub("-", text)
    text = _REPEATED_DASH.sub("-", text).strip("-")
    return text


def field(value: object) -> str:
    """이름의 한 칸. 값이 없어도 칸은 남는다."""
    return sanitize(value) or PLACEHOLDER


def join_fields(*values: object) -> str:
    return FIELD_SEP.join(field(value) for value in values)


def append_layer(parent: str, *values: object) -> str:
    """상위 이름 뒤에 계층을 하나 붙인다.

    상위 이름을 그대로 품는 것은 기존 앱과 같다. 다르게 만든 부분은, 상위 이름이
    바뀌어도 **참조가 UUID라 아무것도 깨지지 않는다**는 점이다. 하위 이름은
    필요할 때 다시 계산해 갱신하면 된다.
    """
    return f"{parent}{LAYER_SEP}{join_fields(*values)}"


def format_number(value: float | Decimal | str, *, digits: int = 3) -> str:
    """치수를 이름에 넣을 문자열로 만든다.

    부동소수 그대로 쓰면 안 된다. SI(m)로 저장한 0.45mm 를 mm로 되돌리면
    `0.44999999999999996` 이 나오고, 그러면 같은 재료가 저장 경로에 따라 다른
    이름을 받는다. Decimal로 반올림해 그 흔들림을 없앤다.

    정수여도 소수점을 남긴다 — 두께 `1` 보다 `1.0` 이 현장 표기에 가깝다.
    """
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return PLACEHOLDER
    if not number.is_finite():
        return PLACEHOLDER

    quantum = Decimal(1).scaleb(-digits)
    number = number.quantize(quantum, rounding=ROUND_HALF_UP).normalize()
    if number == number.to_integral_value():
        return f"{number:.1f}"
    return format(number, "f")


def format_seq(value: int) -> str:
    """일련번호. 두 자리로 맞춰 목록 정렬이 사람 눈과 일치하게 한다."""
    return f"{value:02d}" if 0 <= value < 100 else str(value)


# --- 계층별 이름 -----------------------------------------------------------
#
# Family·Category 는 이름에 넣지 않는다. Grade 가 이미 그것을 함의하고, 기존 앱의
# `Technical Data Record Name` 도 같은 선택을 했다(ID 쪽에만 넣었다).
#
# Orientation 도 재료 이름에 없다. 방향은 **시편을 자를 때** 정해지므로 시편의
# 속성이다. 재료에 두면 MD/TD/DD 가 서로 다른 재료가 되어, 한 재료의 r값이나
# Hill48 파라미터를 구할 때 서로 다른 재료 셋을 묶어야 한다.


def material_name(*, grade: object, details: object, thickness_mm: object) -> str:
    """`SECC_MDOI_1.0`"""
    return join_fields(grade, details, format_number(thickness_mm))  # type: ignore[arg-type]


def sample_name(*, material: str, seq_no: int) -> str:
    """`SECC_MDOI_1.0__02`

    로트번호는 넣지 않는다. 시료를 먼저 등록하고 로트를 나중에 확인하는 일이
    흔한데, 그때 이름이 바뀌면 위 1번과 같은 상황이 된다. 로트는 표시·검색·통계
    축으로만 쓴다.
    """
    return append_layer(material, format_seq(seq_no))


def specimen_name(*, sample: str, orientation: object, seq_no: int) -> str:
    """`SECC_MDOI_1.0__02__MD_03`"""
    return append_layer(sample, orientation, format_seq(seq_no))


def test_run_name(*, specimen: str, type_abbr: object, seq_no: int) -> str:
    """`SECC_MDOI_1.0__02__MD_03__TEN_01`

    끝자리가 **회차**다. 기존 앱이 타임스탬프+난수를 쓰던 자리인데, 회차로
    바꾸면 같은 시험을 다시 올려도 같은 이름이 나온다(위 2번).
    """
    return append_layer(specimen, type_abbr, format_seq(seq_no))
