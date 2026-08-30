"""기준정보의 기본 축.

**축은 데이터가 아니라 스키마에 가깝다.** 축이 하나 늘어난다는 것은 어딘가의
컬럼이 기준정보를 가리키게 된다는 뜻이고, 그건 코드가 바뀌는 일이다. 그래서 API 로
만들지 않고 여기 적는다 — 시험 종류의 `BUILTIN_TEST_TYPES` 와 같은 자리다.

마이그레이션도 같은 것을 심지만 거기 있는 것은 **그때의 스냅샷**이다. 이 파일은
새 DB(테스트·개발 초기화)를 위한 것이라 둘 다 필요하다.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.vocabulary.models import Vocabulary
from matcore.units import SI_UNITS

#: 물성 항목이 고를 수 있는 차원. `units` 가 아는 것만 — 모르는 차원을 적으면
#: 단위 검사가 못 돈다.
DIMENSIONS = tuple(sorted(SI_UNITS))

#: (slug, label, entry_policy, sort_order)
#:
#: `open` 은 사용자가 피커에서 즉석 추가할 수 있다. `closed` 는 관리자가 등록한
#: 값만 고른다 — 미리 정해야 하는 분류다.
#: (slug, label, entry_policy, sort_order, parent_slug, attribute_source)
#:
#: **분류는 사슬이다.** Metal → Steel → SECC. 평평하게 두면 Polymer + PP + SECC
#: 같은 조합을 아무도 안 막고, Grade 가 수만 개일 때 피커가 전체를 보여 준다.
BUILTIN_VOCABULARIES: list[tuple[str, str, str, int, str | None, str | None]] = [
    ("manufacturer", "제조사", "open", 10, None, None),
    # **유통사와 주 벤더가 한 축을 공유한다.** 같은 회사가 어떤 로트에서는
    # 유통사고 다른 로트에서는 주 벤더다. 축을 나누면 같은 회사가 두 목록에
    # 따로 쌓이고, 그 둘을 합칠 방법도 없다.
    ("vendor", "거래처", "open", 20, None, None),
    ("sales_type", "판매 유형", "open", 30, None, None),
    # **시편 분류가 기본 칸을 갖는다.** "인장 시편이면 늘 게이지 길이가
    # 필요하다" 처럼, 그 분류의 규격 전부가 갖는 치수다(`specimen_fields`).
    ("specimen_category", "시편 분류", "open", 38, None, None),
    # **규격은 분류 아래 산다.** 부모 축 기계를 그대로 쓴다(`grade` 의 부모가
    # `category` 이듯) — `kind` 같은 컬럼을 따로 두면 같은 것을 두 방식으로
    # 표현하게 된다.
    #
    # `attribute_source="parent"` 는 "기본 칸을 상위 값이 갖는다" 는 뜻이다.
    # 규격은 거기에 자기만의 칸을 더한다(`extra_fields`) — `ASTM E8 R1` 은
    # 환봉이라 직경이 필요하고 `JIS 5호` 는 평판이라 필요 없다.
    ("specimen_standard", "시편 규격", "open", 40, "specimen_category", "parent"),
    ("instrument", "장비", "open", 50, None, None),
    # **시험을 낸 사업부.** 부서(workspace)와 다르다 — 부서는 누가 볼 수 있는가를
    # 정하고, 이것은 누가 낸 데이터인가를 적는다. 한 부서 계정으로 여러 사업부의
    # 판을 올리는 일이 있고, 그때 부서로는 둘을 못 가른다.
    ("division", "사업부", "open", 45, None, None),
    # **가장 큰 축이고 이득도 가장 크다.** 지금은 SECC/secc/S.E.C.C 가 서로
    # 다른 재료 셋을 만든다. 다만 Grade 는 재료 이름을 만드는 값이라(ADR 0004)
    # 값 이름을 고치면 재료·시료·시편·시험 이름이 전부 따라 바뀐다.
    #
    # **「강종」이 아니라 「Grade」다.** 강종(鋼種)은 강(鋼)에만 쓰는 말인데 이
    # 축은 재료군을 안 가린다 — 개발 DB 에 Polymer/PP 의 Grade `S6F58` 이 있고,
    # 그것을 강종이라 부르면 틀린 말이다. 재료 화면은 처음부터 "Grade" 로
    # 부르고 있었으므로(`NewMaterialDialog`), 기준정보만 다른 이름을 쓰고 있었다.
    ("family", "Family", "open", 1, None, None),
    ("category", "Category", "open", 2, "family", None),
    ("grade", "Grade", "open", 5, "category", None),
    # **용도는 재료의 성질이다**(전에는 시료에 있었다). "도어 이너용 재료가 뭐가
    # 있나" 가 집계 질문이 되려면 자유 문자열이면 안 된다 — `도어`/`Door`/`도어 `
    # 가 갈리면 그 질문에 답이 셋 나온다.
    # **시험이 주지 않는 물성.** 탄성계수·열팽창계수·비열은 인장시험이 안 준다 —
    # 핸드북·규격·밀시트에서 온다. 어떤 항목을 받을지는 **부서가 정한다**(D7):
    # 열해석을 안 하는 부서에 비열 칸이 뜰 이유가 없고, 반대로 우리가 목록을
    # 코드에 박으면 필요한 항목을 넣으려고 배포를 기다려야 한다.
    #
    # 값마다 **차원**을 든다. 그래야 「비열 자리에 열전도도」가 막힌다 —
    # ADR 0013 이 "밀도 자리에 온도를 넣어도 아무도 모른다" 고 적어 둔 구멍이다.
    ("property_item", "물성 항목", "open", 55, None, None),
    ("product", "적용 제품", "open", 60, None, None),
    # **부위를 제품 아래에 두지 않는다.** 계층은 값 하나에 부모 하나인데(`grade`
    # 의 부모가 `category` 하나이듯), `이너 패널` 은 도어에도 후드에도 쓰인다.
    # 부모를 붙이면 먼저 들어온 제품이 이기고 나머지는 조용히 틀린 곳에 매달린다.
    ("part", "적용 파트", "open", 70, None, None),
]

#: **전부 `open` 이다.** `closed` 는 만들어 두고 안 켠다.
#:
#: 막았을 때 사람이 어디로 가는지가 문제다. 첫 발포재를 등록하려는데 `Foam` 이
#: 목록에 없으면 관리자를 찾아가거나 — 더 흔하게는 **`Metal` 로 대충 고르고
#: 넘어간다.** 그러면 분류가 지켜진 것이 아니라 조용히 틀린 것이다.
#:
#: `closed` 가 값을 하는 자리는 **외부 시스템이 정본을 주는 축**이다(ReportArchive
#: 는 모델·BOM 코드에 쓴다). 거기서는 정본에 없는 값을 만드는 것 자체가 오류다.
#: MatNexus 에는 아직 그런 축이 없다 — 모든 값을 사람이 친다. Phase 6 에서 장비
#: 커넥터가 붙으면 그때 켠다.


#: 칸 하나의 기본값. 종류·선택지·기호는 대개 안 쓰므로 여기서 채운다.
def _field(
    key: str,
    label: str,
    *,
    kind: str = "number",
    dimension: str = "length",
    si_unit: str = "m",
    choices: list[str] | None = None,
    symbol: str | None = None,
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


#: 축이 갖는 칸 — **그 축의 값이면 무엇이든 갖는다.**
#:
#: 지금은 시편 규격의 판(edition) 하나다. ASTM 문서가 못 박는다: *"규격 번호만
#: 으로는 부족하다. 판 연도와 시편 타입을 함께 지정해야 한다"*(`ASTM D638-22
#: Type I`). 판이 다르면 치수가 다르고, E8 과 E8M 은 환봉 게이지 길이가 4D 대
#: 5D 라 **연신율을 직접 비교할 수 없다.**
#:
#: **왜 분류가 아니라 축인가:** 분류마다 적으면 새 분류에서 빠뜨린다. 판은
#: 인장이든 DMA 든 모든 규격이 갖는다.
BUILTIN_AXIS_FIELDS: dict[str, list[dict[str, Any]]] = {
    "specimen_standard": [
        _field(
            "edition",
            "판(edition)",
            kind="text",
            help="규격의 판 연도. 판이 다르면 치수가 다릅니다 — "
            "`-22`, `-24`, `-17(2025)` 처럼 규격서 표기 그대로 적으세요.",
        )
    ],
    # **물성 항목이면 무엇이든 차원을 갖는다.** 단위가 아니라 차원인 이유:
    # 저장은 언제나 정본 SI 이고 사람이 보는 단위는 화면이 정한다(시험 채널과
    # 같은 규칙). `GPa` 로 적어도 저장은 `Pa` 다.
    "property_item": [
        _field(
            "dimension",
            "차원",
            kind="choice",
            choices=sorted(DIMENSIONS),
            help="이 물성이 무엇의 차원인가. 값을 넣을 때 단위가 이것으로 검사됩니다 — "
            "「비열 자리에 열전도도」 같은 것이 여기서 막힙니다.",
        ),
        _field(
            "symbol",
            "기호",
            kind="text",
            help="덱과 화면에 쓰는 기호. `E`·`alpha`·`Cp` 처럼 적으세요.",
        ),
        _field(
            "measured_key",
            "우리가 재는 값",
            kind="choice",
            choices=[],  # `ensure_builtin_axis_fields` 가 레지스트리에서 채운다
            help="같은 물성을 처리 결과가 낸다면 그 값의 키. 채우면 화면이 "
            "**적어 둔 값과 우리가 잰 값을 나란히** 보여 줍니다 — 밀시트가 말한 "
            "항복강도와 우리 인장시험이 낸 항복강도가 그렇습니다. 비워도 됩니다.",
        ),
        _field(
            "scales",
            "시험 척도",
            kind="text",
            help="**단위가 아니라 척도**인 물성에 적습니다. 쉼표로 나눠 적으세요 — "
            "`HV, HB, HRC`. 적으면 이 항목은 단위 대신 척도를 고르게 되고, "
            "**서로 환산하지 않습니다**: `HV 200` 과 `HB 200` 은 다른 값이고 "
            "환산식이 없습니다(규격의 참고표는 재료마다 다릅니다). 비워 두면 "
            "보통 물성처럼 '차원' 으로 단위를 검사합니다.",
        ),
        _field(
            "level",
            "붙는 곳",
            kind="choice",
            choices=["재료", "시료"],
            help="이 값이 어디에 붙는가. **Grade 가 같으면 같은 값**이면 재료입니다"
            "(탄성계수·열물성 — 문헌·규격에서 옵니다). **로트마다 다르면** 시료입니다"
            "(항복강도·인장강도 — 밀시트가 줍니다). 비우면 재료로 봅니다.",
        ),
    ],
}


#: 기본 시편 분류와 그 분류의 **기본 칸**.
#:
#: **최소로 둔다.** 그 분류의 규격이면 대개 갖는 것만 기본이다 — 인장 환봉에는
#: 폭·두께가 없고, DMA 인장 필름에는 지지 간격이 없다. 그런 것은 규격이 자기
#: 칸으로 더한다.
#:
#: **필수로 두지 않는다.** 전에는 "예외 없이 갖는 것" 이라 여겨 인장의 게이지
#: 길이와 DMA 의 자유길이·폭·두께를 필수로 두었는데, ASTM·ISO 규격표가 그것을
#: 반증했다.
#:
#:   인장 - D3039·D3518·D5766 은 게이지 길이를 시편에 새기지 않는다(그립 간
#:   거리가 곧 게이지다). D1708 은 표점 게이지를 두지 않고, D412 링은 표점이
#:   아니라 내부 원주로 초기 길이를 정의한다. D5083·D2290·D897·D2095 도 없다.
#:
#:   DMA - 자유길이·폭·두께 셋을 다 갖는 파트는 ISO 6721-4(인장) 하나뿐이다.
#:   -2·-3·-8·-10 은 자유길이가 없고, -6 전단·-10 평행판·-12 압축은 폭이 없다
#:   (직경이다). D4065 는 "specimen size is not fixed by this practice" 라고
#:   문장으로 못 박는다.
#:
#: 필수로 두면 그런 규격은 **저장 자체가 안 된다.** 필수 여부는 부서가 자기
#: 규격을 보고 화면에서 정한다.
BUILTIN_SPECIMEN_CATEGORIES: list[tuple[str, list[dict[str, Any]]]] = [
    (
        "인장",
        [
            _field(
                "gauge_length",
                "게이지 길이",
                help="변위를 이 길이로 나눠 변형률을 만듭니다. 복합재(D3039 계열)처럼 "
                "표점을 안 새기고 그립 간 거리를 쓰는 규격도 있습니다.",
            ),
            _field("total_length", "전체 길이"),
        ],
    ),
    (
        "DMA",
        [
            # **모드가 곧 시편 형상이다.** DMA 규격은 대개 치수를 안 정하고
            # 모드와 형상만 정한 뒤 장비 클램프에 넘긴다(D4065: "specimen size
            # is not fixed by this practice"). 그래서 모드를 안 적으면 그 시편이
            # 무엇이었는지 나중에 알 수 없다 — 같은 규격·같은 재료라도 모드가
            # 다르면 저장탄성률 절대값을 직접 비교할 수 없다.
            _field(
                "mode",
                "변형 모드",
                kind="choice",
                choices=[
                    "이중 캔틸레버",
                    "단일 캔틸레버",
                    "3점 굽힘",
                    "인장",
                    "압축",
                    "전단 샌드위치",
                    "비틀림",
                    "평행판",
                ],
                help="모드가 곧 시편 형상입니다. 보고서에는 규격 번호만이 아니라 "
                "모드·스팬·시편 치수를 함께 적어야 재현이 됩니다.",
            ),
            _field(
                "free_length",
                "자유 길이",
                help="클램프 사이의 길이. 계산에 들어가는 것은 전체 길이가 "
                "아니라 이 값입니다. "
                "장비 카탈로그의 스팬은 시편 길이가 아니라 클램프 사이 거리입니다 - "
                "물림 여유를 더한 블랭크 길이는 별도 칸으로 두세요.",
            ),
            _field("width", "폭", help="압축·평행판·전단 모드에는 폭 대신 직경이 옵니다."),
            _field("thickness", "두께"),
        ],
    ),
]


#: 기본 물성 항목. **최소로 둔다** — 나머지는 부서가 필요할 때 넣는다(D7).
#:
#: 여기 있는 것들의 공통점: **시험이 안 주는데 해석에는 꼭 필요하다.** 탄성계수는
#: 인장시험이 주기도 하지만 밀시트·핸드북 값을 쓰는 일이 더 흔하고(시험을 안 한
#: 재료가 대부분이다), 열물성 셋은 인장시험이 아예 안 준다.
#:
#: 밀시트(EN 10204 3.1)가 주는 것은 항복강도·인장강도·연신율·경도다 — 그것들은
#: 이미 처리 결과에 있으므로 여기 안 넣는다.
#:
#: **층이 갈린다**(ADR 0016). 앞의 다섯은 Grade 가 같으면 같은 값이라 재료에
#: 붙고, 뒤의 셋은 로트마다 달라서 시료에 붙는다 — 밀시트가 주는 것이 정확히
#: 뒤엣것이다(EN 10204 3.1).
#:
#: **경도는 안 넣는다.** 밀시트가 주기는 하는데 `HV 200` 과 `HB 200` 과
#: `HRC 200` 은 서로 다른 값이고 환산식이 없다(규격이 참고표를 주지만 재료마다
#: 다르다). 지금 기계는 값 하나에 단위 하나라 셋을 한 칸에 받게 되고, 그러면
#: **숫자는 그럴듯한데 뜻이 다른** 값이 저장된다 — 이 저장소가 가장 경계하는
#: 종류다. 시험 척도를 값의 속성으로 드는 것이 먼저다.
#: `(값, 차원, 기호, 붙는 곳, 우리가 재는 값, 시험 척도)`.
BUILTIN_PROPERTY_ITEMS: list[tuple[str, str, str, str, str | None, str | None]] = [
    ("탄성계수", "stress", "E", "재료", None, None),
    ("전단탄성계수", "stress", "G", "재료", None, None),
    ("열팽창계수", "inverse_temperature", "alpha", "재료", None, None),
    ("비열", "specific_heat", "Cp", "재료", None, None),
    ("열전도도", "thermal_conductivity", "k", "재료", None, None),
    # 밀시트가 주는 것들. 앞의 둘은 **우리가 잰 값에 대응이 있다** — 그래서
    # 「밀시트가 말한 값과 우리가 잰 값이 맞나」를 물을 수 있다.
    ("항복강도", "stress", "Rp", "시료", "proof_stress", None),
    ("인장강도", "stress", "Rm", "시료", "tensile_strength", None),
    # **연신율은 비워 둔다.** 밀시트의 A 는 파단 후 연신율인데 우리가 내는
    # `elongation_observed` 는 시험 창 안의 관측 최대 변형률이다 — 가깝지만
    # 같지 않다. 이어 붙이면 화면이 「맞다/틀리다」를 말하게 되고, 그 판정은
    # 두 값이 같은 것일 때만 뜻이 있다.
    ("연신율", "strain", "A", "시료", None, None),
    # **경도는 척도로 든다.** `HV 200`·`HB 200`·`HRC 200` 은 서로 다른 값이고
    # 환산식이 없다 — 규격(ASTM E140)이 참고표를 주지만 재료마다 다르고 그것도
    # 「대략」이라고 명시한다. 한 칸에 받으면 **숫자는 그럴듯한데 뜻이 다른**
    # 값이 저장되므로, 척도를 값의 일부로 든다.
    #
    # 차원 자리는 안 쓴다(척도가 있으면 단위 검사를 건너뛴다). 자리를 비울 수
    # 없어 `dimensionless` 를 적어 둔다.
    ("경도", "dimensionless", "H", "시료", None, "HV, HB, HRC, HRB, HS"),
]


def ensure_builtin_property_items(db: Session) -> list[str]:
    """기본 물성 항목을 보장한다. **이미 있는 것은 손대지 않는다.**

    부서가 이름을 고치거나 지웠을 수 있고, 배포가 그것을 되돌리면 안 된다.
    """
    from app.modules.vocabulary.models import VocabularyTerm
    from app.shared.text import clean, compare_key

    axis = db.scalar(select(Vocabulary).where(Vocabulary.slug == "property_item"))
    if axis is None:
        return []

    created: list[str] = []
    for value, dimension, symbol, level, measured, scales in BUILTIN_PROPERTY_ITEMS:
        cleaned = clean(value)
        if cleaned is None:
            continue
        key = compare_key(cleaned)
        found = db.scalar(
            select(VocabularyTerm).where(
                VocabularyTerm.vocabulary_id == axis.id, VocabularyTerm.normalized == key
            )
        )
        if found is not None:
            continue
        db.add(
            VocabularyTerm(
                vocabulary_id=axis.id,
                value=cleaned,
                normalized=key,
                attributes={
                    "dimension": dimension,
                    "symbol": symbol,
                    "level": level,
                    **({"measured_key": measured} if measured else {}),
                    **({"scales": scales} if scales else {}),
                },
            )
        )
        created.append(cleaned)
    if created:
        db.flush()
    return created


def measured_keys() -> list[str]:
    """처리 결과가 내는 스칼라 키들. **레지스트리가 정본이다.**

    물성 항목의 `measured_key` 를 이 목록에서 고르게 한다 — 손으로 적게 두면
    오타가 조용히 "잰 값 없음" 이 되고, 그때 사람은 비교가 안 되는 이유를
    알 방법이 없다.

    씨앗을 심을 때 부른다. 새 처리 단계가 붙은 뒤 목록을 다시 채우려면 축의
    칸을 비우고 다시 심어야 하는데, 그것은 관리자가 화면에서 고르는 편이 낫다
    (이 함수는 **관리자가 고친 칸을 되돌리지 않는다**).
    """
    from matcore import processing, registry

    processing.load_builtin()
    return sorted(
        {value.key for plugin in registry.list_plugins() for value in plugin.makes_values}
    )


def ensure_builtin_axis_fields(db: Session) -> list[str]:
    """축의 칸을 보장한다. 채운 축의 slug 를 돌려준다.

    **이미 칸이 있으면 손대지 않는다.** 관리자가 고쳤을 수 있고, 배포가 그것을
    되돌리면 안 된다(축·시험 종류와 같은 판단).
    """
    filled: list[str] = []
    for slug, fields in BUILTIN_AXIS_FIELDS.items():
        fields = [
            {**field, "choices": measured_keys()}
            if field.get("key") == "measured_key"
            else field
            for field in fields
        ]
        axis = db.scalar(select(Vocabulary).where(Vocabulary.slug == slug))
        if axis is None or axis.base_fields:
            continue
        axis.base_fields = fields
        filled.append(slug)
    if filled:
        db.flush()
    return filled


def ensure_builtin_specimen_categories(db: Session) -> list[str]:
    """기본 분류와 그 기본 칸을 보장한다. 새로 만든 값을 돌려준다.

    **이미 있는 것은 손대지 않는다.** 운영 중에 관리자가 칸을 고쳤을 수 있고,
    배포가 그것을 되돌리면 안 된다(시험 종류·축과 같은 판단).
    """
    from app.modules.vocabulary.models import SpecimenField, VocabularyTerm
    from app.shared.text import clean, compare_key

    axis = db.scalar(select(Vocabulary).where(Vocabulary.slug == "specimen_category"))
    if axis is None:
        return []

    created: list[str] = []
    for value, fields in BUILTIN_SPECIMEN_CATEGORIES:
        term = db.scalar(
            select(VocabularyTerm).where(
                VocabularyTerm.vocabulary_id == axis.id,
                VocabularyTerm.normalized == compare_key(value),
            )
        )
        if term is None:
            term = VocabularyTerm(
                vocabulary_id=axis.id,
                value=clean(value),
                normalized=compare_key(value),
            )
            db.add(term)
            db.flush()
            created.append(value)
        existing = set(
            db.scalars(
                select(SpecimenField.key).where(SpecimenField.category_term_id == term.id)
            )
        )
        for order, field in enumerate(fields):
            if field["key"] in existing:
                continue
            db.add(
                SpecimenField(
                    category_term_id=term.id,
                    sort_order=order * 10,
                    **field,
                )
            )
    return created


def ensure_builtin_vocabularies(db: Session) -> list[str]:
    """기본 축을 보장한다. 새로 만든 것의 slug 를 돌려준다.

    **이미 있는 축은 손대지 않는다.** 운영 중에 관리자가 라벨이나 정책을 바꿨을
    수 있고, 그것을 배포가 되돌리면 안 된다(시험 종류와 같은 판단).
    """
    existing = set(db.scalars(select(Vocabulary.slug)))
    created: list[str] = []
    for slug, label, policy, order, parent, attribute_source in BUILTIN_VOCABULARIES:
        if slug in existing:
            continue
        db.add(
            Vocabulary(
                slug=slug,
                label=label,
                entry_policy=policy,
                sort_order=order,
                parent_slug=parent,
                attribute_source=attribute_source,
            )
        )
        created.append(slug)
    if created:
        db.flush()
    return created
