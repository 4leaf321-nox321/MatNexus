"""표준 시편 규격 카탈로그 — **칸과 기호는 심고, 치수 값은 안 심는다.**

규격 하나를 쓸모 있게 만들려면 칸을 만들고, 기호를 적고, 값을 넣고, 단면적 식을
고르는 네 단계를 손으로 해야 한다. 규격이 스물이면 여든 번이다.

## 값을 왜 안 심는가

이 카탈로그의 근거인 규격 정리 문서는 **본문이 유료라 2차 출처 기반**이고, 스스로
이렇게 적어 두었다.

    "이 표는 어떤 변수가 존재하는지를 빠르게 파악하는 용도입니다. 실제 도면
     작성·시편 발주에는 해당 규격의 최신판 원문을 확인하세요."

실제로 출처끼리 어긋난 곳이 있다 — D5766 전체 길이가 152 mm 와 250 mm 로,
D6693 두께 범위가 초록끼리 상충한다. **그 숫자를 심으면 검증 안 된 값이 시스템의
정본이 된다.** 치수는 자릿수 하나만 틀려도 응력이 통째로 어긋나는데 숫자는
그럴듯해 보인다.

칸과 기호는 그런 위험이 없다. **판이 바뀌어도 `게이지 길이 = G` 는 그대로다** —
바뀌는 것은 그 값이다. 그래서 구조만 깔고 숫자는 사람이 규격서를 보고 넣는다.

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


#: 가져올 수 있는 표준 규격.
#:
#: `attributes` 는 **비운다.** 치수 값은 사람이 규격서를 보고 넣는다.
CATALOG: list[dict[str, Any]] = [
    # ── 금속 인장 ─────────────────────────────────────────────────────────
    {
        "key": "astm_e8_plate",
        "value": "ASTM E8/E8M 판재형",
        "category": TENSILE,
        "family": "금속 인장",
        "fields": _E8_FLAT,
        "cross_section": "rectangle",
        "help": "게이지 길이 200 mm 계열. A370·B557·E345·E646 이 같은 기호계를 씁니다.",
    },
    {
        "key": "astm_e8_sheet",
        "value": "ASTM E8/E8M 박판형",
        "category": TENSILE,
        "family": "금속 인장",
        "fields": _E8_FLAT,
        "cross_section": "rectangle",
        "help": "게이지 길이 50 mm 계열. 금속 판재에서 가장 널리 쓰입니다.",
    },
    {
        "key": "astm_e8_subsize",
        "value": "ASTM E8/E8M 소형",
        "category": TENSILE,
        "family": "금속 인장",
        "fields": _E8_FLAT,
        "cross_section": "rectangle",
        "help": "게이지 길이 25 mm 계열.",
    },
    {
        "key": "astm_e8_round",
        "value": "ASTM E8/E8M 환봉",
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
        "help": "E8 은 게이지가 4D, E8M 은 5D 입니다 — 연신율을 직접 비교할 수 없습니다.",
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
        "value": "ASTM D638 Type I",
        "category": TENSILE,
        "family": "고분자 인장",
        "fields": _D638,
        "cross_section": "rectangle",
        "help": "강성·반강성의 기본(두께 7 mm 이하). D 는 직경이 아니라 그립 간 거리입니다.",
    },
    {
        "key": "astm_d638_type4",
        "value": "ASTM D638 Type IV",
        "category": TENSILE,
        "family": "고분자 인장",
        "fields": [*_D638, field("outer_radius", "외측 반경", symbol="RO")],
        "cross_section": "rectangle",
        "help": "비강성용(두께 4 mm 이하). D6693 이 이 형상을 그대로 씁니다.",
    },
    {
        "key": "astm_d638_type5",
        "value": "ASTM D638 Type V",
        "category": TENSILE,
        "family": "고분자 인장",
        "fields": _D638,
        "cross_section": "rectangle",
        "help": "재료가 부족할 때 쓰는 소형(두께 4 mm 이하).",
    },
    {
        "key": "astm_d412_die",
        "value": "ASTM D412 덤벨 다이",
        "category": TENSILE,
        "family": "고분자 인장",
        "fields": _D412_DIE,
        "cross_section": "rectangle",
        "help": "Die C 가 사실상 표준입니다. 좁은 부분 길이 L 과 표점 게이지는 다른 값입니다.",
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
]
