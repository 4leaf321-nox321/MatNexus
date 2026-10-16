"""표준 시편 규격 카탈로그 — **구조는 확실하고, 값은 시작점이다.**

규격 하나를 쓸모 있게 만들려면 칸을 만들고, 기호를 적고, 값을 넣고, 단면적 식을
고르는 네 단계를 손으로 해야 한다. 규격이 스물이면 여든 번이다.

## 값은 **딱 정해진 것만** 심는다

같은 치수표 안에서도 성격이 섞여 있다.

    고정값      G 200.0 ± 0.2        규격이 그 숫자로 정한다        → 심는다
    최소값만    R >= 25, L >= 450    실제 값은 시편마다 다르다      → 안 심는다
    근사        C ~= 50 (그립부 폭)  "근사" 라고 적혀 있다          → 안 심는다
    재료가 정함 T = 재료 두께         시편마다 다르다                → 안 심는다
    범위        ISO 6721-2 40~120    권장이 있어도 범위다            → 안 심는다
    권장        D3039 "변경 가능"     규격이 스스로 그렇게 적었다     → 안 심는다

**규격을 다 채워도 시편 치수가 다 정해지지는 않는다.** 두께는 늘 재료가 정하고,
최소값만 있는 칸은 실제 값이 시편마다 다르다.

## 값을 그대로 믿으면 안 된다

이 카탈로그의 근거인 규격 정리 문서는 **본문이 유료라 2차 출처 기반**이고, 스스로
이렇게 적어 두었다.

    "이 표는 어떤 변수가 존재하는지를 빠르게 파악하는 용도입니다. 실제 도면
     작성·시편 발주에는 해당 규격의 최신판 원문을 확인하세요."

실제로 출처끼리 어긋난 곳이 있다 — D5766 전체 길이가 152 mm 와 250 mm 로,
D6693 두께 범위가 초록끼리 상충한다. **여기 심는 값은 시작점이지 정본이 아니다.**
상충한 항목은 아예 안 심었고(D5766 전체 길이), 관리자가 규격서를 보고 고치는 것을
전제한다.

칸과 기호에는 그런 위험이 없다. **판이 바뀌어도 `게이지 길이 = G` 는 그대로다** —
바뀌는 것은 값이다. 그래서 구조는 확실하고 값은 확인이 필요하다.

## 판을 함께 적는다

E8 과 E8M 은 **환산 관계가 아니라 별개의 단위계 규격**이고, 환봉 게이지가 4D 대
5D 라 연신율을 직접 비교할 수 없다. 그래서 값을 심는 항목은 **어느 판의 값인지**를
이름에 담는다.

## 기호를 왜 함께 심는가

**같은 글자가 규격마다 다른 뜻이다.** E8 의 `D` 는 직경이고 D638 의 `D` 는 그립
간 거리다. `L` 은 E8 에서 전체 길이, D638 에서 좁은 부분 길이, ISO 527 에서 그립
간 거리로 셋 다 다르다.

그리고 **장비 파일의 항목 이름이 곧 그 글자다** — Zwick 이 두께를 `a0`, 폭을
`b0`, 직경을 `d0` 로 적는다. 기호를 담아 두면 파일 채우기가 저절로 이어진다
(`curvedata.instrument_dimensions`).
"""

from __future__ import annotations

from typing import Any

#: 이 카탈로그가 기대는 시편 분류. 없으면 그 항목은 안 보여 준다.
TENSILE = "인장"
DMA = "DMA"
FLEXURAL = "굽힘"
COMPRESSION = "압축"


def field(
    key: str,
    label: str,
    *,
    symbol: str | None = None,
    kind: str = "number",
    dimension: str = "length",
    si_unit: str = "m",
    choices: list[str] | None = None,
    help: str | None = None,
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "kind": kind,
        "choices": choices or [],
        "symbol": symbol,
        "dimension": dimension if kind == "number" else "dimensionless",
        "si_unit": si_unit if kind == "number" else "1",
        "is_required": False,
        "help": help,
    }


def ratio(
    numerator: str,
    denominator: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
    help: str | None = None,
) -> dict[str, Any]:
    return {
        "numerator": numerator,
        "denominator": denominator,
        "minimum": minimum,
        "maximum": maximum,
        "help": help,
    }


# --- 금속 인장: E8/E8M 기호계 -------------------------------------------------
#
# A370·B557·E345·E646 이 같은 문자 집합을 그대로 물려받는다. 금속 쪽은 사실상
# 하나의 체계다.

_E8_FLAT = [
    field("gauge_length", "게이지 길이", symbol="G"),
    field("width", "평행부 폭", symbol="W"),
    field("parallel_length", "평행부 길이", symbol="A"),
    field("thickness", "두께", symbol="T", help="재료 두께 그대로입니다."),
    field("fillet_radius", "필렛 반경", symbol="R"),
    field("overall_length", "전체 길이", symbol="L"),
    field("grip_length", "그립부 길이", symbol="B"),
    field("grip_width", "그립부 폭", symbol="C"),
]

_E8_ROUND = [
    field("gauge_length", "게이지 길이", symbol="G"),
    field("diameter", "직경", symbol="D"),
    field("fillet_radius", "필렛 반경", symbol="R"),
    field("parallel_length", "평행부 길이", symbol="A"),
    field("grip_length", "그립부 길이", symbol="B"),
    field("grip_width", "그립부 폭", symbol="C"),
]

# --- 고분자 인장: D638 기호계 -------------------------------------------------
#
# **같은 글자가 다른 뜻이다.** D638 의 `D` 는 직경이 아니라 그립 간 거리이고,
# `L` 은 전체 길이가 아니라 좁은 부분의 길이다.

_D638 = [
    field("width", "좁은 부분 폭", symbol="W"),
    field("narrow_length", "좁은 부분 길이", symbol="L"),
    field("overall_width", "전체 폭", symbol="WO"),
    field("overall_length", "전체 길이", symbol="LO"),
    field("gauge_length", "게이지 길이", symbol="G"),
    field(
        "grip_separation",
        "그립 간 거리",
        symbol="D",
        help="E8 의 D(직경)와 정반대입니다 — 도면을 옮길 때 가장 주의할 곳입니다.",
    ),
    field("fillet_radius", "필렛 반경", symbol="R"),
    field("thickness", "두께", symbol="T"),
]

_D412_DIE = [
    field("end_width", "단부 폭", symbol="A"),
    field("overall_length", "전체 길이", symbol="C"),
    field("narrow_length", "좁은 부분 길이", symbol="L"),
    field("width", "좁은 부분 폭", symbol="W"),
    field("gauge_length", "표점 게이지 길이"),
    field("thickness", "두께"),
]

_D412_RING = [
    field("width", "반경방향 폭"),
    field("thickness", "두께"),
    field("inner_diameter", "내경"),
    field(
        "circumference",
        "내부 원주",
        help="링은 표점이 아니라 내부 원주로 초기 길이를 정의합니다.",
    ),
]

_D882 = [
    field("width", "폭"),
    field("thickness", "두께"),
    field(
        "grip_separation",
        "그립 간 거리",
        help="박막은 표점을 안 새깁니다 — 그립 간 거리가 곧 게이지입니다.",
    ),
    field("overall_length", "전체 길이"),
]

# --- 복합재: 기호 없이 이름으로 -----------------------------------------------
#
# 이 분야는 문자 기호를 쓰지 않고 표의 열 이름으로 치수를 지정한다. 그리고
# **평행부도 필렛도 없다** — 축소부를 만들면 그 자리에서 섬유가 끊긴다.

_D3039 = [
    field("width", "폭"),
    field("overall_length", "전체 길이"),
    field("thickness", "두께"),
    field("tab_length", "탭 길이"),
    field("tab_thickness", "탭 두께"),
    field(
        "tab_bevel",
        "탭 베벨각",
        dimension="angle",
        si_unit="rad",
        help="7° 또는 90°. 길이가 아니라 각도입니다.",
    ),
    field(
        "grip_separation",
        "그립 간 거리",
        help="게이지 길이를 시편에 새기지 않습니다 — 이 거리가 곧 게이지입니다.",
    ),
]

_D5766 = [
    *_D3039,
    field("hole_diameter", "구멍 지름", symbol="d"),
    field(
        "width_to_hole",
        "폭/구멍 지름",
        dimension="dimensionless",
        si_unit="1",
        help="w/d = 6 이 표준입니다.",
    ),
]

# --- DMA: 치수를 안 정하고 모드와 비율만 주는 것이 대부분 ----------------------

_DMA_BAR = [
    field("free_length", "자유 길이"),
    field("width", "폭"),
    field("thickness", "두께"),
    field(
        "blank_length",
        "블랭크 길이",
        help="클램프 스팬이 아니라 실제로 잘라야 하는 길이입니다 — 물림 여유를 더합니다.",
    ),
]


# --- 굽힘: b · h · L · Lᵢ ------------------------------------------------------
#
# 직사각형 단면 보. 3점과 4점은 **하중 스팬이 있느냐**로만 갈린다 — 처리(`flexural.*`)도
# 그 칸으로 가른다. 스팬은 대개 두께의 배수로 정해져 값이 아니라 비율 조건으로 건다.

_FLEX_3PT = [
    field("width", "폭", symbol="b"),
    field("thickness", "두께", symbol="h"),
    field("span", "지지 스팬", symbol="L", help="받침 사이 거리입니다."),
    field("total_length", "전체 길이", symbol="l"),
]

_FLEX_4PT = [
    *_FLEX_3PT,
    field(
        "load_span",
        "하중 스팬 (4점)",
        symbol="Li",
        help="누르는 두 노즈 사이 거리입니다. 3점이면 비웁니다.",
    ),
]

# --- 압축: 높이 h₀ 와 하중 면 ---------------------------------------------------

_COMP_CYLINDER = [
    field("diameter", "직경", symbol="d"),
    field("height", "초기 높이", symbol="h0"),
]

_COMP_BLOCK = [
    field("width", "하중면 가로", symbol="a"),
    field("thickness", "하중면 세로", symbol="b"),
    field("height", "초기 높이", symbol="h0"),
]


#: 가져올 수 있는 표준 규격.
#:
#: `attributes` 는 **비운다.** 치수 값은 사람이 규격서를 보고 넣는다.
CATALOG: list[dict[str, Any]] = [
    # ── 금속 인장 ─────────────────────────────────────────────────────────
    {
        "key": "astm_e8_plate",
        # G·W 만 고정값이다. R·L·A·B 는 "최소", C 는 "근사", T 는 재료 두께다.
        "attributes": {"gauge_length": 0.200, "width": 0.040},
        "value": "ASTM E8/E8M 판재형",
        "category": TENSILE,
        "family": "금속 인장",
        "fields": _E8_FLAT,
        "cross_section": "rectangle",
        "help": "게이지 길이 200 mm 계열. A370·B557·E345·E646 이 같은 기호계를 씁니다.",
    },
    {
        "key": "astm_e8_sheet",
        # G·W 만 고정값이다. R·L·A·B 는 "최소", C 는 "근사", T 는 재료 두께다.
        "attributes": {"gauge_length": 0.050, "width": 0.0125},
        "value": "ASTM E8/E8M 박판형",
        "category": TENSILE,
        "family": "금속 인장",
        "fields": _E8_FLAT,
        "cross_section": "rectangle",
        "help": "게이지 길이 50 mm 계열. 금속 판재에서 가장 널리 쓰입니다.",
    },
    {
        "key": "astm_e8_subsize",
        # G·W 만 고정값이다. R·L·A·B 는 "최소", C 는 "근사", T 는 재료 두께다.
        "attributes": {"gauge_length": 0.025, "width": 0.006},
        "value": "ASTM E8/E8M 소형",
        "category": TENSILE,
        "family": "금속 인장",
        "fields": _E8_FLAT,
        "cross_section": "rectangle",
        "help": "게이지 길이 25 mm 계열.",
    },
    {
        "key": "astm_e8_round",
        "value": "ASTM E8M 환봉 (12.5 mm)",
        # E8M 표준: D 12.5 → G 62.5 (5D). **E8(inch-pound)은 4D 라 값이 다르다.**
        "attributes": {"diameter": 0.0125, "gauge_length": 0.0625},
        "category": TENSILE,
        "family": "금속 인장",
        "fields": [
            *_E8_ROUND,
            field(
                "grip_end",
                "단부 형식",
                kind="choice",
                choices=["나사", "숄더", "평행", "버튼헤드"],
                help="Fig. 9 에서 따로 정의됩니다.",
            ),
        ],
        "cross_section": "circle",
        "help": "E8M 미터계 표준입니다. E8(inch-pound)은 게이지가 4D 라 값이 "
        "다르고, 연신율을 직접 비교할 수 없습니다.",
    },
    {
        "key": "astm_e8_tube_strip",
        "value": "ASTM E8/E8M 관재 스트립",
        "category": TENSILE,
        "family": "금속 인장",
        "fields": [item for item in _E8_FLAT if item["key"] != "fillet_radius"]
        + [field("fillet_radius", "필렛 반경", symbol="R")],
        "cross_section": "rectangle",
        "help": "두께는 관 두께입니다.",
    },
    # ── 고분자 인장 ───────────────────────────────────────────────────────
    {
        "key": "astm_d638_type1",
        # WO·LO 는 "최소", 두께는 범위(7 mm 이하)라 안 심는다.
        "attributes": {
            "width": 0.013,
            "narrow_length": 0.057,
            "gauge_length": 0.050,
            "grip_separation": 0.115,
            "fillet_radius": 0.076,
        },
        "value": "ASTM D638 Type I",
        "category": TENSILE,
        "family": "고분자 인장",
        "fields": _D638,
        "cross_section": "rectangle",
        "help": "강성·반강성의 기본(두께 7 mm 이하). D 는 직경이 아니라 그립 간 거리입니다.",
    },
    {
        "key": "astm_d638_type4",
        "attributes": {
            "width": 0.006,
            "narrow_length": 0.033,
            "gauge_length": 0.025,
            "grip_separation": 0.065,
            "fillet_radius": 0.014,
            "outer_radius": 0.025,
        },
        "value": "ASTM D638 Type IV",
        "category": TENSILE,
        "family": "고분자 인장",
        "fields": [*_D638, field("outer_radius", "외측 반경", symbol="RO")],
        "cross_section": "rectangle",
        "help": "비강성용(두께 4 mm 이하). D6693 이 이 형상을 그대로 씁니다.",
    },
    {
        "key": "astm_d638_type5",
        "attributes": {
            "width": 0.00318,
            "narrow_length": 0.00953,
            "gauge_length": 0.00762,
            "grip_separation": 0.0254,
            "fillet_radius": 0.0127,
        },
        "value": "ASTM D638 Type V",
        "category": TENSILE,
        "family": "고분자 인장",
        "fields": _D638,
        "cross_section": "rectangle",
        "help": "재료가 부족할 때 쓰는 소형(두께 4 mm 이하).",
    },
    {
        "key": "astm_d412_die_a",
        "value": "ASTM D412 Die A",
        "category": TENSILE,
        "family": "고분자 인장",
        "fields": _D412_DIE,
        "cross_section": "rectangle",
        "attributes": {
            "end_width": 0.025,
            "overall_length": 0.14,
            "narrow_length": 0.059,
            "width": 0.012,
            "gauge_length": 0.05,
            "thickness": 0.002,
        },
        "help": "좁은 부분 길이 L 과 표점 게이지는 다른 값입니다.",
    },
    {
        "key": "astm_d412_die_b",
        "value": "ASTM D412 Die B",
        "category": TENSILE,
        "family": "고분자 인장",
        "fields": _D412_DIE,
        "cross_section": "rectangle",
        "attributes": {
            "end_width": 0.025,
            "overall_length": 0.14,
            "narrow_length": 0.059,
            "width": 0.006,
            "gauge_length": 0.05,
            "thickness": 0.002,
        },
        "help": "좁은 부분 길이 L 과 표점 게이지는 다른 값입니다.",
    },
    {
        "key": "astm_d412_die_c",
        "value": "ASTM D412 Die C",
        "category": TENSILE,
        "family": "고분자 인장",
        "fields": _D412_DIE,
        "cross_section": "rectangle",
        "attributes": {
            "end_width": 0.025,
            "overall_length": 0.115,
            "narrow_length": 0.033,
            "width": 0.006,
            "gauge_length": 0.025,
            "thickness": 0.002,
        },
        "help": "사실상의 표준 다이입니다. 좁은 부분 길이 L(33 mm)과 표점 "
        "게이지(25 mm)는 다른 값입니다 — 인터넷에 도는 표가 이 둘을 자주 섞습니다.",
    },
    {
        "key": "astm_d412_die_d",
        "value": "ASTM D412 Die D",
        "category": TENSILE,
        "family": "고분자 인장",
        "fields": _D412_DIE,
        "cross_section": "rectangle",
        "attributes": {
            "end_width": 0.016,
            "overall_length": 0.1,
            "narrow_length": 0.033,
            "width": 0.003,
            "gauge_length": 0.025,
            "thickness": 0.002,
        },
        "help": "좁은 부분 길이 L 과 표점 게이지는 다른 값입니다.",
    },
    {
        "key": "astm_d412_die_e",
        "value": "ASTM D412 Die E",
        "category": TENSILE,
        "family": "고분자 인장",
        "fields": _D412_DIE,
        "cross_section": "rectangle",
        "attributes": {
            "end_width": 0.016,
            "overall_length": 0.125,
            "narrow_length": 0.059,
            "width": 0.003,
            "gauge_length": 0.05,
            "thickness": 0.002,
        },
        "help": "좁은 부분 길이 L 과 표점 게이지는 다른 값입니다.",
    },
    {
        "key": "astm_d412_die_f",
        "value": "ASTM D412 Die F",
        "category": TENSILE,
        "family": "고분자 인장",
        "fields": _D412_DIE,
        "cross_section": "rectangle",
        "attributes": {
            "end_width": 0.016,
            "overall_length": 0.125,
            "narrow_length": 0.059,
            "width": 0.006,
            "gauge_length": 0.05,
            "thickness": 0.002,
        },
        "help": "좁은 부분 길이 L 과 표점 게이지는 다른 값입니다.",
    },
    {
        "key": "astm_d412_ring",
        "value": "ASTM D412 링",
        "category": TENSILE,
        "family": "고분자 인장",
        "fields": _D412_RING,
        "cross_section": "ring",
        "help": "두 가닥이 하중을 받습니다 — 평판 식으로 내면 강도가 두 배로 나옵니다.",
    },
    {
        "key": "astm_d882_film",
        "value": "ASTM D882 박막 스트립",
        "category": TENSILE,
        "family": "고분자 인장",
        "fields": _D882,
        "cross_section": "rectangle",
        "help": "두께 1 mm 미만 박막. 표점을 안 새기고 그립 간 거리를 씁니다.",
    },
    # ── 복합재 ────────────────────────────────────────────────────────────
    {
        "key": "astm_d3039",
        "value": "ASTM D3039",
        "category": TENSILE,
        "family": "복합재",
        "fields": _D3039,
        "cross_section": "rectangle",
        "help": "평행부도 필렛도 없는 등단면 스트립에 탭을 붙입니다. "
        "공차가 비율입니다(폭 ±1 %).",
    },
    {
        "key": "astm_d3518",
        "value": "ASTM D3518 (±45° 전단)",
        "category": TENSILE,
        "family": "복합재",
        "fields": _D3039,
        "cross_section": "rectangle",
        "help": "D3039 와 같은 형상을 씁니다.",
    },
    {
        "key": "astm_d5766",
        # **전체 길이는 안 심는다** — 출처가 152 mm 와 250 mm 로 상충한다.
        "attributes": {"width": 0.036, "hole_diameter": 0.006, "width_to_hole": 6},
        "value": "ASTM D5766 (오픈홀)",
        "category": TENSILE,
        "family": "복합재",
        "fields": _D5766,
        "cross_section": "rectangle",
        "ratio_checks": [
            ratio(
                "width", "hole_diameter", minimum=6, maximum=6, help="w/d = 6 이 표준입니다."
            ),
        ],
        "help": "구멍이 있는 등단면 스트립. 단면적은 구멍을 뺀 값이 아니라 총폭 기준입니다.",
    },
    # ── DMA ───────────────────────────────────────────────────────────────
    {
        "key": "iso_6721_2",
        "value": "ISO 6721-2 (비틀림 진자)",
        "category": DMA,
        "family": "DMA",
        "fields": [
            field("length", "길이"),
            field("width", "폭"),
            field("thickness", "두께"),
        ],
        "help": "숫자를 실제로 주는 몇 안 되는 파트입니다(권장 50 x 10 x 1 mm).",
    },
    {
        "key": "iso_6721_3",
        "value": "ISO 6721-3 (굽힘 공진)",
        "category": DMA,
        "family": "DMA",
        "fields": [field("length", "길이"), field("width", "폭"), field("thickness", "두께")],
        "ratio_checks": [
            ratio("length", "thickness", minimum=50, help="저장탄성률 ±5 % 정확도 확보"),
        ],
    },
    {
        "key": "iso_6721_4",
        "value": "ISO 6721-4 (인장 비공진)",
        "category": DMA,
        "family": "DMA",
        "fields": [
            field("free_length", "클램프 간 길이", symbol="La"),
            field("width", "폭", symbol="b"),
            field("thickness", "두께", symbol="h"),
        ],
        "ratio_checks": [
            ratio("free_length", "width", minimum=6, help="클램프의 횡수축 구속 영향 배제"),
        ],
        "help": "권장 클램프 간 50~100 mm 인데 어느 장비도 그 값을 못 줍니다 — "
        "실제 값을 함께 보고하세요.",
    },
    {
        "key": "iso_6721_6",
        "value": "ISO 6721-6 (전단 비공진)",
        "category": DMA,
        "family": "DMA",
        "fields": [
            field("thickness", "고분자 두께", symbol="L"),
            field("height", "하중 방향 높이", symbol="h"),
        ],
        "ratio_checks": [
            ratio("height", "thickness", minimum=4, help="굽힘 성분 기여를 무시할 수준으로"),
        ],
        "help": "동일 시편 2장이 필요합니다. 고무·접착제의 1순위 모드입니다.",
    },
    {
        "key": "iso_6721_10",
        "value": "ISO 6721-10 (평행판)",
        "category": DMA,
        "family": "DMA",
        "fields": [
            field("diameter", "지름", symbol="D"),
            field("gap", "갭", symbol="d"),
            field("charge", "시료량", dimension="mass", si_unit="kg"),
        ],
        "ratio_checks": [ratio("diameter", "gap", minimum=10, maximum=50)],
    },
    {
        "key": "iso_6721_12",
        "value": "ISO 6721-12 (압축 비공진)",
        "category": DMA,
        "family": "DMA",
        "fields": [field("height", "높이", symbol="h"), field("diameter", "지름", symbol="D")],
        "ratio_checks": [
            ratio(
                "height", "diameter", minimum=1, maximum=2, help="프리로드 하 좌굴·배럴링 방지"
            ),
        ],
    },
    {
        "key": "astm_d5023",
        "value": "ASTM D5023 (3점 굽힘)",
        "category": DMA,
        "family": "DMA",
        "fields": [
            *_DMA_BAR,
            field("overhang", "오버행", help="지지점 바깥으로 남는 길이입니다."),
        ],
        "ratio_checks": [
            ratio(
                "free_length",
                "thickness",
                minimum=16,
                maximum=16,
                help="스팬 = 16 곱하기 두께",
            ),
        ],
    },
    {
        "key": "astm_d5418",
        "value": "ASTM D5418 (이중 캔틸레버)",
        "category": DMA,
        "family": "DMA",
        "fields": _DMA_BAR,
        "help": '"specimen size is not fixed by this practice" — '
        "치수를 장비 클램프에 위임합니다.",
    },
    {
        "key": "astm_d7028",
        "value": "ASTM D7028 (복합재 Tg)",
        "category": DMA,
        "family": "DMA",
        "fields": _DMA_BAR,
        "ratio_checks": [
            ratio("free_length", "thickness", minimum=10, help="전단 변형 기여 억제"),
        ],
    },
    # ── 굽힘 ──────────────────────────────────────────────────────────────
    #
    # 처리는 규격 이름을 모른다 — 규격마다 다른 것(3점 · 4점, 탄성률을 재는 방법과 구간)은
    # 처리 단계에서 고른다. 무엇을 고르는지는 `help` 와 가이드에 적는다.
    {
        "key": "iso_178",
        # 권장 시편 80 x 10 x 4 와 그때의 스팬 16h = 64 만 고정값이다.
        "attributes": {
            "total_length": 0.080,
            "width": 0.010,
            "thickness": 0.004,
            "span": 0.064,
        },
        "value": "ISO 178 (플라스틱 3점 굽힘)",
        "category": FLEXURAL,
        "family": "플라스틱 굽힘",
        "fields": _FLEX_3PT,
        "cross_section": "rectangle",
        "processing": {
            "flexural.engineering": {"load_span": None},
            "flexural.modulus": {
                "method": "chord",
                "minimum_strain": 0.0005,
                "maximum_strain": 0.0025,
            },
        },
        "ratio_checks": [
            ratio("span", "thickness", minimum=15, maximum=17, help="스팬 = (16 ± 1) x 두께"),
        ],
        "help": "탄성률은 현(변형률 0.05% ~ 0.25%). 규정 처짐(변형률 3.5%)의 응력 σfC 를 "
        "함께 봅니다. JIS K 7171 이 같은 방법입니다.",
    },
    {
        "key": "astm_d790",
        # 성형 시편 127 x 12.7 x 3.2 와 스팬 50.8(16:1)을 규격이 정한다(규격 정리 문서 03 절).
        "attributes": {
            "total_length": 0.127,
            "width": 0.0127,
            "thickness": 0.0032,
            "span": 0.0508,
        },
        "value": "ASTM D790 (플라스틱 3점 굽힘)",
        "category": FLEXURAL,
        "family": "플라스틱 굽힘",
        "fields": _FLEX_3PT,
        "cross_section": "rectangle",
        "processing": {
            "flexural.engineering": {"load_span": None},
            "flexural.modulus": {"method": "tangent"},
        },
        # 최대는 안 건다 — 저전단강도 재료는 32 · 40 · 60 : 1 을 고른다.
        "ratio_checks": [
            ratio(
                "span", "thickness", minimum=15, help="16 : 1 (±1) 기본, 32 · 40 · 60 : 1 선택"
            ),
        ],
        "help": "탄성률은 처음 직선 구간의 접선. 처짐이 스팬의 10% 를 넘으면 큰 처짐 보정을 "
        "켭니다. 절차 A 는 변형률 속도 0.01 /min.",
    },
    {
        "key": "astm_d6272",
        "value": "ASTM D6272 (플라스틱 4점 굽힘)",
        "category": FLEXURAL,
        "family": "플라스틱 굽힘",
        "fields": _FLEX_4PT,
        "cross_section": "rectangle",
        "processing": {
            "flexural.engineering": {"load_span": "@specimen_load_span"},
            "flexural.modulus": {"method": "tangent"},
        },
        "ratio_checks": [
            ratio(
                "span", "thickness", minimum=15, maximum=17, help="스팬 : 두께 = 16 : 1 (±1)"
            ),
            ratio(
                "load_span", "span", minimum=0.33, maximum=0.5, help="하중 스팬 = L/3 또는 L/2"
            ),
        ],
        "help": "하중 스팬은 지지 스팬의 1/3 또는 1/2. 탄성률은 접선.",
    },
    {
        "key": "iso_14125",
        "value": "ISO 14125 (섬유강화 복합재 굽힘)",
        "category": FLEXURAL,
        "family": "복합재 굽힘",
        "fields": _FLEX_4PT,
        "cross_section": "rectangle",
        "processing": {
            "flexural.modulus": {
                "method": "chord",
                "minimum_strain": 0.0005,
                "maximum_strain": 0.0025,
            },
        },
        "ratio_checks": [
            ratio(
                "span",
                "thickness",
                minimum=16,
                maximum=40.5,
                help="등급(I ~ IV)에 따라 16 · 20 · 40 : 1",
            ),
        ],
        "help": "등급 I 80 x 10 x 4(스팬 64), II 80 x 15 x 4(64), III 60 x 15 x 2(40), "
        "IV 100 x 15 x 2(80). 등급은 재료가 아니라 Ef1/G13 비로 정함. 3점(방법 A) · "
        "4점(방법 B, 하중 스팬 = L/3). 탄성률은 현(변형률 0.05% ~ 0.25%).",
    },
    {
        "key": "astm_d7264",
        # 표준 형상의 폭 13 · 두께 4 와 32 : 1 스팬 128 이 고정값이다(다른 비도 허용).
        "attributes": {"width": 0.013, "thickness": 0.004, "span": 0.128},
        "value": "ASTM D7264 (고분자 복합재 굽힘)",
        "category": FLEXURAL,
        "family": "복합재 굽힘",
        "fields": _FLEX_4PT,
        "cross_section": "rectangle",
        "processing": {
            "flexural.modulus": {
                "method": "chord",
                "minimum_strain": 0.001,
                "maximum_strain": 0.003,
            },
        },
        "ratio_checks": [
            ratio(
                "span", "thickness", minimum=16, help="표준 32 : 1 (16 · 20 · 40 · 60 도 허용)"
            ),
        ],
        "help": "절차 A 는 3점, 절차 B 는 4점(하중 스팬 = L/2). "
        "탄성률은 현(변형률 0.1% ~ 0.3%).",
    },
    {
        "key": "astm_c1161_b",
        # 형상 B 는 치수가 전부 정해져 있다.
        "attributes": {
            "width": 0.004,
            "thickness": 0.003,
            "span": 0.040,
            "load_span": 0.020,
            "total_length": 0.045,
        },
        "value": "ASTM C1161 형상 B (세라믹 굽힘 강도)",
        "category": FLEXURAL,
        "family": "세라믹 굽힘",
        "fields": _FLEX_4PT,
        "cross_section": "rectangle",
        "processing": {
            "flexural.engineering": {"load_span": "@specimen_load_span"},
            "flexural.modulus": {"method": "stress_window", "band_low": 0.1, "band_high": 0.4},
        },
        "ratio_checks": [
            ratio("load_span", "span", minimum=0.5, maximum=0.5, help="하중 스팬 = L/2"),
        ],
        "help": "강도가 목적인 규격. 탄성률을 함께 내려면 처짐계와 응력 띠 방법을 씁니다.",
    },
    {
        "key": "iso_14704",
        "attributes": {"width": 0.004, "thickness": 0.003, "span": 0.040},
        "value": "ISO 14704 (세라믹 굽힘 강도)",
        "category": FLEXURAL,
        "family": "세라믹 굽힘",
        "fields": _FLEX_4PT,
        "cross_section": "rectangle",
        "processing": {
            "flexural.modulus": {"method": "stress_window", "band_low": 0.1, "band_high": 0.4},
        },
        "help": "3점 · 4점(하중 스팬 20 mm). C1161 형상 B 와 시편이 같습니다.",
    },
    {
        "key": "inhouse_flexural_3pt",
        "value": "사내 3점 굽힘 (칩 · 모듈 등가 E)",
        "category": FLEXURAL,
        "family": "사내 굽힘",
        "fields": _FLEX_3PT,
        "cross_section": "rectangle",
        "processing": {
            "flexural.engineering": {"load_span": None},
            "flexural.modulus": {"method": "stress_window", "band_low": 0.1, "band_high": 0.4},
        },
        "help": "직사각형 단면을 균질한 보로 보고 등가 E 를 냅니다. "
        "스팬 / 두께가 16 보다 작으면 "
        "전단 처짐 때문에 E 가 작게 나올 수 있습니다 — 처짐계를 쓰거나 장비 컴플라이언스를 "
        "뺍니다.",
    },
    {
        "key": "inhouse_flexural_4pt",
        "value": "사내 4점 굽힘 (칩 · 모듈 등가 E)",
        "category": FLEXURAL,
        "family": "사내 굽힘",
        "fields": _FLEX_4PT,
        "cross_section": "rectangle",
        "processing": {
            "flexural.engineering": {"load_span": "@specimen_load_span"},
            "flexural.modulus": {"method": "stress_window", "band_low": 0.1, "band_high": 0.4},
        },
        "help": "두 하중점 사이가 순수 굽힘이라 전단 영향이 적습니다.",
    },
    # ── 압축 ──────────────────────────────────────────────────────────────
    {
        "key": "iso_7743_a",
        "attributes": {"diameter": 0.029, "height": 0.0125},
        "value": "ISO 7743 시험편 A (고무 압축)",
        "category": COMPRESSION,
        "family": "고무 압축",
        "fields": _COMP_CYLINDER,
        "cross_section": "circle",
        "processing": {
            "compression.engineering": {"cycle": 4},
            "compression.modulus": {"method": "secant", "maximum_strain": 0.1},
        },
        "help": "네 번 눌러 네 번째 하중 구간의 압축 응력 · 할선 탄성률을 봅니다"
        "(처리의 사이클 "
        "= 4). 방법 A 윤활 · B 접착 · C 사포.",
    },
    {
        "key": "astm_d575",
        "attributes": {"diameter": 0.0286, "height": 0.0125},
        "value": "ASTM D575 (고무 압축)",
        "category": COMPRESSION,
        "family": "고무 압축",
        "fields": _COMP_CYLINDER,
        "cross_section": "circle",
        "processing": {
            "compression.modulus": {"method": "secant", "maximum_strain": 0.1},
        },
        "help": "방법 A 는 정한 변형에서의 하중, 방법 B 는 정한 하중에서의 변형.",
    },
    {
        "key": "iso_3386_1",
        "attributes": {"width": 0.100, "thickness": 0.100, "height": 0.050},
        "value": "ISO 3386-1 (연질 폼 압축 응력값)",
        "category": COMPRESSION,
        "family": "폼 압축",
        "fields": _COMP_BLOCK,
        "cross_section": "rectangle",
        "processing": {
            "compression.engineering": {"cycle": 4},
            "compression.modulus": {"method": "secant", "maximum_strain": 0.1},
        },
        "help": "70% 까지 네 번 눌러 네 번째 하중 구간의 40% 압축 응력"
        "(CV40, 처리의 사이클 = 4).",
    },
    {
        "key": "astm_d3574_c",
        "value": "ASTM D3574 시험 C (연질 폼 압축 하중)",
        "category": COMPRESSION,
        "family": "폼 압축",
        "fields": _COMP_BLOCK,
        "cross_section": "rectangle",
        "processing": {
            "compression.modulus": {"method": "secant", "maximum_strain": 0.1},
        },
        "help": "최소 50 x 50 x 25 mm. 두 번 미리 누른 뒤 세 번째의 50% 압축 응력(CFD, 처리의 "
        "사이클 = 3). 25 · 65% 도 봅니다.",
    },
    {
        "key": "iso_844",
        "value": "ISO 844 (경질 폼 압축)",
        "category": COMPRESSION,
        "family": "폼 압축",
        "fields": _COMP_BLOCK,
        "cross_section": "rectangle",
        "processing": {
            "compression.modulus": {"method": "tangent", "tangent_width": 0.01},
        },
        "help": "10% 변형 전에 최대가 있으면 그 응력, 없으면 10% 압축 응력이 압축 강도. "
        "탄성률은 처음 직선 구간의 접선.",
    },
    {
        "key": "astm_d1621",
        "value": "ASTM D1621 (경질 폼 압축)",
        "category": COMPRESSION,
        "family": "폼 압축",
        "fields": _COMP_BLOCK,
        "cross_section": "rectangle",
        "processing": {
            "compression.modulus": {"method": "tangent", "tangent_width": 0.01},
        },
        "ratio_checks": [ratio("height", "width", maximum=1, help="높이 ≤ 폭")],
        "help": "하중면 25.8 ~ 232 cm², 높이 25.4 mm 이상. ISO 844 와 같은 강도 정의"
        "(항복 또는 10%). 탄성률은 접선.",
    },
    {
        "key": "iso_604",
        # 탄성률 시편 50 x 10 x 4(강도 시편은 높이 10 mm).
        "attributes": {"width": 0.010, "thickness": 0.004, "height": 0.050},
        "value": "ISO 604 탄성률 시편 (플라스틱 압축)",
        "category": COMPRESSION,
        "family": "플라스틱 압축",
        "fields": _COMP_BLOCK,
        "cross_section": "rectangle",
        "processing": {
            "compression.modulus": {
                "method": "chord",
                "minimum_strain": 0.0005,
                "maximum_strain": 0.0025,
            },
        },
        "help": "탄성률은 현(변형률 0.05% ~ 0.25%) — 압축계 변형률이 있어야 맞습니다.",
    },
    {
        "key": "astm_d695",
        "attributes": {"width": 0.0127, "thickness": 0.0127, "height": 0.0254},
        "value": "ASTM D695 강도 시편 (경질 플라스틱 압축)",
        "category": COMPRESSION,
        "family": "플라스틱 압축",
        "fields": _COMP_BLOCK,
        "cross_section": "rectangle",
        "processing": {
            "compression.modulus": {"method": "tangent", "tangent_width": 0.001},
        },
        "ratio_checks": [
            ratio("height", "width", minimum=2, maximum=2, help="강도 시편 L = 2W"),
        ],
        "help": "프리즘 12.7 x 12.7 x 25.4 mm(탄성률 시편은 높이 50.8 mm). 탄성률은 접선.",
    },
    {
        "key": "astm_e9",
        "value": "ASTM E9 원통 (금속 압축)",
        "category": COMPRESSION,
        "family": "금속 압축",
        "fields": _COMP_CYLINDER,
        "cross_section": "circle",
        "processing": {
            "compression.modulus": {"method": "tangent", "tangent_width": 0.0005},
        },
        "ratio_checks": [
            ratio("height", "diameter", minimum=2, maximum=10, help="L/D 2 · 3 · 8 · 10 등급"),
        ],
        "help": "짧은 시편(L/D 2)은 강도, 긴 시편(L/D 8 · 10)은 탄성계수 · 항복. 짧은 시편은 "
        "단부 마찰이 탄성계수를 오염 — 탄성계수는 압축계 변형률로.",
    },
    {
        "key": "astm_d6641",
        "value": "ASTM D6641 (복합재 압축, CLC)",
        "category": COMPRESSION,
        "family": "복합재 압축",
        "fields": [
            *_COMP_BLOCK,
            field(
                "gauge_length", "게이지 길이(비지지 길이)", help="CLC 블록 사이 길이입니다."
            ),
        ],
        "cross_section": "rectangle",
        "processing": {
            "compression.engineering": {"source": "strain"},
            "compression.modulus": {
                "method": "chord",
                "minimum_strain": 0.001,
                "maximum_strain": 0.003,
            },
        },
        "help": "약 140 x 12 ~ 13 x 2 ~ 2.5 mm, 게이지 12 ~ 13 mm. 변형률은 스트레인 게이지"
        "(변형률 채널)로 — 크로스헤드 변위에는 지그 · 탭 변형이 섞임.",
    },
    {
        "key": "astm_d3410",
        "value": "ASTM D3410 (복합재 압축, 전단 하중)",
        "category": COMPRESSION,
        "family": "복합재 압축",
        "fields": [
            *_COMP_BLOCK,
            field("gauge_length", "게이지 길이(비지지 길이)", help="그립 사이 길이입니다."),
        ],
        "cross_section": "rectangle",
        "processing": {
            "compression.engineering": {"source": "strain"},
            "compression.modulus": {
                "method": "chord",
                "minimum_strain": 0.001,
                "maximum_strain": 0.003,
            },
        },
        "help": "SI 열과 인치-파운드 열이 환산이 아닌 별개 규격(폭 10 mm 와 12.7 mm) — 섞어 "
        "쓰지 않음. 변형률은 스트레인 게이지(변형률 채널)로.",
    },
    {
        "key": "inhouse_compression_cylinder",
        "value": "사내 압축 (원통)",
        "category": COMPRESSION,
        "family": "사내 압축",
        "fields": _COMP_CYLINDER,
        "cross_section": "circle",
    },
    {
        "key": "inhouse_compression_block",
        "value": "사내 압축 (직육면체)",
        "category": COMPRESSION,
        "family": "사내 압축",
        "fields": _COMP_BLOCK,
        "cross_section": "rectangle",
    },
]
