"""값으로 재료 찾기 — **「항복응력이 200MPa 근처인 재료」.**

1단계(`property_names`)가 이름을 풀고, 여기가 값을 건다. 둘은 형제다 — 그래프는
연결을 따라가는 데 강하지 **숫자 범위로 거르는 데는 표가 훨씬 낫다.**

## 단위를 안 주면 거절한다

    Pa   990건   8.0 ~ 2,753,909,000
    1    158건   0.007 ~ 0.96

값이 SI 로 저장돼 있으므로 200MPa 는 `200,000,000` 이다. 사람은 「200」이라고
치는데 그대로 넣으면 **8 Pa 짜리가 나온다.** 그래서 단위를 필수로 받고, 없으면
답하지 않는다 — 짐작해서 답하면 조용히 틀린다.

이 저장소는 단위로 여러 번 데었다. 알루미늄 밀도를 `density_kg_m3` 라 이름 붙였다가
`2.68e-09 kg/m3` 로 내보낸 일이 MCP 안내서에 적혀 있다.

## 문헌과 사내를 함께 본다

문헌만 찾으면 반쪽이다 — 사내 재료의 선언 물성도 같은 물성이고, 값이 이미 SI 로
저장돼 있어(`points[].value_si`) 같은 범위가 그대로 걸린다.

**권한은 여기서 안 건다.** 사내 재료 조회는 부르는 쪽이 `visible_materials` 를
거친다 — 이 모듈은 값만 안다(그래프 모듈과 같은 분리).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Float, Select, cast, func, or_, select, true
from sqlalchemy import null as sa_null
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from app.modules.catalog import parameters
from app.modules.catalog.models import CatalogDefinition, CatalogMaterial, CatalogValue
from app.modules.materials.models import Material, Sample, Specimen
from app.modules.processing.models import ProcessingResult
from app.modules.tests.models import TestConditionField, TestRun
from app.shared import standard_conditions, tiers
from app.shared.errors import AppError
from matcore import registry, units

#: 「근처」 를 물었을 때의 기본 폭. ±10% — 물성 문헌값이 그 정도로 흩어진다.
NEAR_RATIO = 0.10

#: 한 번에 돌려주는 최대. 서버가 상한을 강제한다(AGENTS.md).
MAX_ROWS = 200


@dataclass(frozen=True)
class ConditionFilter:
    """「어떤 조건에서」 — 표준 조건 하나의 SI 범위(2026-09-16).

    조건은 값의 **한정자**라 값처럼 범위로 건다. 어느 키가 그 조건인지는 세계마다
    다르게 풀린다: 시험은 조건 칸의 `canonical_key`, 문헌은 `conditions` 의 별칭
    (`temperature_k` · `temperature_c`), 선언은 점의 `temperature_k`.
    """

    key: str
    low: float
    high: float

    @property
    def standard(self) -> standard_conditions.StandardCondition:
        return standard_conditions.STANDARD[self.key]


def condition_bounds(
    *,
    key: str,
    unit: str,
    near: float | None = None,
    minimum: float | None = None,
    maximum: float | None = None,
    tolerance: float | None = None,
) -> ConditionFilter:
    """조건의 물음을 SI 범위로. **단위는 필수**다 — 값과 같은 이유.

    「근처」 의 폭은 표준 조건이 정한다(온도 ±5 K). `tolerance` 를 주면(물은 단위로)
    그것이 이긴다. 폭이 0 인 조건(속도·주파수)은 값처럼 ±10% 다.
    """
    standard = standard_conditions.STANDARD.get(key)
    if standard is None:
        known = ", ".join(standard_conditions.STANDARD)
        raise AppError(
            "MNX-CATALOG-0051",
            f"모르는 조건입니다: {key}. 있는 것: {known}",
            status=422,
        )
    if units.canonical(unit) is None:
        raise AppError("MNX-CATALOG-0032", f"모르는 단위입니다: '{unit}'.", status=422)
    if near is None and minimum is None and maximum is None:
        raise AppError(
            "MNX-CATALOG-0051",
            f"조건 {standard.label} 의 값을 주세요 — condition_near 또는 condition_min/max.",
            status=422,
        )
    if near is not None:
        center = units.to_si(near, unit)
        if tolerance is not None:
            # 폭은 차이라, 영점이 있는 단위(°C)는 두 점의 차로 환산한다.
            width = abs(units.to_si(near + tolerance, unit) - center)
        elif standard.near_tolerance_si > 0:
            width = standard.near_tolerance_si
        else:
            width = abs(center) * NEAR_RATIO
        return ConditionFilter(key=key, low=center - width, high=center + width)
    low = units.to_si(minimum, unit) if minimum is not None else float("-inf")
    high = units.to_si(maximum, unit) if maximum is not None else float("inf")
    return ConditionFilter(key=key, low=low, high=high)


@dataclass(frozen=True)
class Hit:
    """값 하나와 그것을 든 재료."""

    world: str
    """`catalog`(문헌) · `internal`(사내 선언) · `measured`(시험으로 잰 값)."""
    material_id: uuid.UUID
    material_name: str
    value_si: float
    """**SI 다.** 보여 줄 때는 물어본 단위로 되돌린다."""
    value_shown: float
    unit_shown: str
    quality_tier: int | None = None
    source_detail: str | None = None
    category: str | None = None
    count: int = 1
    """이 줄에 묶인 값의 수. 잰 값은 **재료·방법별로 묶어** 낸다 — 시편 3장이면 1줄."""
    spread_si: float | None = None
    """묶인 값들의 표준편차(SI). 하나면 `None`."""
    method: str | None = None
    """어떻게 쟀나 — 「항복강도 · 오프셋 0.002」. **같은 키로 묶였어도 방법이 다르면
    값이 다르다**(Tg 는 DSC·DMA 가 다르고, 항복은 오프셋마다 다르다). 그 사실이
    보이지 않으면 사람은 「왜 같은 재료가 값이 셋이지」 가 된다."""


def bounds(
    *,
    unit: str,
    si_unit: str,
    minimum: float | None,
    maximum: float | None,
    near: float | None,
    convert: bool = True,
) -> tuple[float, float]:
    """사람이 준 범위를 SI 로. **단위가 안 맞으면 거절한다.**

    `near` 를 주면 ±10% 로 편다 — 「200MPa 근처」 가 실제로 사람이 묻는 방식이다.
    """
    if near is None and minimum is None and maximum is None:
        raise AppError(
            "MNX-CATALOG-0030",
            "범위를 주세요 — `near`(근처) 또는 `min`/`max` 중 하나가 있어야 합니다.",
            status=422,
        )
    if not convert:
        # **파라미터형 물성은 환산하지 않는다**(ADR 0029 D2). 저장된 값이 SI 가
        # 아니라 그 항의 원래 단위라, 환산하면 값이 상한다 — 그리고 그 사실은
        # 숫자만 봐서는 안 드러난다.
        if near is not None:
            return near * (1 - NEAR_RATIO), near * (1 + NEAR_RATIO)
        low = minimum if minimum is not None else float("-inf")
        high = maximum if maximum is not None else float("inf")
        if low > high:
            raise AppError("MNX-CATALOG-0033", "최솟값이 최댓값보다 큽니다.", status=422)
        return low, high

    canonical = units.canonical(unit)
    if canonical is None:
        raise AppError(
            "MNX-CATALOG-0031",
            f"'{unit}' 는 아는 단위가 아닙니다.",
            status=422,
        )
    # **차원이 다르면 답하지 않는다.** 「항복강도를 °C 로」 물으면 숫자는 나오지만
    # 그 답은 뜻이 없다 — 조용히 틀리는 쪽이다.
    #
    # 정의의 단위를 표가 모르면(HV·ShoreA) 차원 검사는 **건너뛴다** — 전에는 빈
    # 차원과 견줘서 「차원이 다릅니다」 로 막혔다. 같은 단위인데 표기만 다른 것
    # (`W/(m*K)`)이 그 길로 3,591건 막혀 있었다(2026-09-11).
    known = units.unit_of(canonical)
    dimension = _dimension_of(si_unit) if si_unit else None
    if dimension and not units.same_dimension(known.dimension, dimension):
        raise AppError(
            "MNX-CATALOG-0032",
            f"이 물성의 단위는 '{si_unit}' 인데 '{unit}' 로 물었습니다 — 차원이 다릅니다.",
            status=422,
        )

    if near is not None:
        middle = units.to_si(near, canonical)
        return middle * (1 - NEAR_RATIO), middle * (1 + NEAR_RATIO)
    low = units.to_si(minimum, canonical) if minimum is not None else float("-inf")
    high = units.to_si(maximum, canonical) if maximum is not None else float("inf")
    if low > high:
        raise AppError("MNX-CATALOG-0033", "최솟값이 최댓값보다 큽니다.", status=422)
    return low, high


def _dimension_of(si_unit: str) -> str | None:
    """정의의 기호에서 차원을 되찾는다. 모르면 `None` — 그때는 검사를 건너뛴다.

    표기가 조금 달라도(`W/(m*K)`) `canonical` 이 알면 그 차원이다. 정말 모르는
    단위(HV·ShoreA 등 원본 taxonomy 것)는 억지로 꿰지 않는다(ADR 0027).
    """
    found = units.canonical(si_unit)
    return units.unit_of(found).dimension if found else None


def same_symbol(asked: str, si_unit: str | None) -> bool:
    """물어본 단위가 **정의의 단위 그 자체**인가 — 표에 없어도 그대로 견줄 수 있다.

    `HV` 는 환산할 수 없지만 「HV 200 근처」 는 뜻이 있다 — 저장된 값이 그 눈금
    그대로라 숫자를 그대로 걸면 된다. 곱·거듭제곱·대소문자·공백만 다른 것은 같다.
    """
    if not si_unit:
        return False
    return units.loose_key(asked) == units.loose_key(si_unit)


def rank(center: float | None) -> Any:
    """결과를 **무엇에 가까운 순**으로 세울지 — `near` 를 줬으면 그 값에서 가까운 순.

    실측(기준선 5차, 2026-09-20): 「탄성계수 200 GPa 근처」 를 `near=200, limit=20` 으로
    물으면 180~220 창의 **아래쪽 20개**(180.x 부터)가 왔다. 값 오름차순이라서다. AI 는
    200 근처를 못 보고 창을 195~205, 199~201 로 좁혀 세 번 더 불렀다 — 네 문항이
    그렇게 예산을 넘겼다. 「근처」 라고 물었으면 가까운 것부터가 답이다.

    **동점에는 작은 값이 앞이다.** 기준 200 에 190 과 210 은 똑같이 10 만큼 머니,
    거리만 열쇠로 쓰면 둘의 앞뒤를 SQL 이 준 순서가 정한다 — 그쪽도 거리만 보므로
    결국 DB 마음이고, 같은 요청이 매번 다른 답을 준다(시험이 이따금 빨갰다,
    실측 2026-09-23).
    """
    if center is None:
        return lambda one: one.value_si
    return lambda one: (abs(one.value_si - center), one.value_si)


def catalog_hits(
    db: Session,
    *,
    property_key: str,
    low: float,
    high: float,
    unit: str,
    limit: int,
    term: str | None = None,
    convert: bool = True,
    condition: ConditionFilter | None = None,
    min_tier: int | None = None,
    center: float | None = None,
) -> list[Hit]:
    """문헌 값에서 찾는다.

    `term` 은 **파라미터형 물성에서 어느 변수인가**다(ADR 0029). 안 주고 찾으면
    Anand 의 `A`(1/s)와 `h0`(MPa)를 섞어서 답하게 된다.

    조건은 `conditions` JSON 의 별칭으로 푼다 — 온도는 `temperature_k` 또는
    `temperature_c`(+273.15). 그 키가 없는 값은 **그 조건에서 잰 것이 아니라** 안 걸린다.
    """
    query: Select[Any] = (
        select(CatalogValue, CatalogMaterial)
        .join(CatalogMaterial, CatalogMaterial.id == CatalogValue.material_id)
        .where(
            CatalogValue.property_key == property_key,
            CatalogValue.value_num.is_not(None),
            CatalogValue.value_num >= low,
            CatalogValue.value_num <= high,
        )
        .order_by(
            # **동점에 앞뒤를 준다.** 기준 200 에 190 과 210 은 똑같이 10 만큼 멀다 —
            # 거리만으로 줄 세우면 둘의 순서가 DB 마음이라 같은 요청이 매번 다른 답을
            # 준다(시험이 이따금 빨갰다, 실측 2026-09-23).
            *(
                (func.abs(CatalogValue.value_num - center), CatalogValue.value_num)
                if center is not None
                else (CatalogValue.value_num,)
            )
        )
        .limit(limit)
    )
    if term:
        query = query.where(CatalogValue.conditions[parameters.TERM].astext == term)
    else:
        # **변수 달린 값은 스칼라가 아니다.** 영률 키에 Prony 급수의 E0 가 몇 건 섞여 있다 —
        # 그 값은 「영률」 이 아니라 「그 식의 E0」 다. 같은 범위에 넣으면 조용히 섞인다.
        query = query.where(
            or_(
                CatalogValue.conditions.is_(None),
                ~CatalogValue.conditions.has_key(parameters.TERM),
            )
        )
    if min_tier is not None:
        query = query.where(CatalogValue.quality_tier <= min_tier)
    if condition is not None:
        query = query.where(
            _catalog_condition_si(condition.key).between(condition.low, condition.high)
        )
    made: list[Hit] = []
    for value, material in db.execute(query).all():
        made.append(
            Hit(
                world="catalog",
                material_id=material.id,
                material_name=material.name,
                value_si=float(value.value_num),
                value_shown=float(value.value_num)
                if not convert
                else units.from_si(value.value_num, unit),
                unit_shown=unit,
                quality_tier=value.quality_tier,
                source_detail=value.source_detail,
                category=material.category,
            )
        )
    return made


def _catalog_condition_si(key: str) -> Any:
    """문헌 `conditions` 에서 표준 조건 값을 SI 로 읽는 SQL 식. 없으면 NULL(= 안 걸림)."""
    standard = standard_conditions.STANDARD[key]
    pieces: list[Any] = []
    for alias in (key, *standard.aliases):
        if not alias.isascii():
            continue
        raw: Any = cast(CatalogValue.conditions[alias].astext, Float)
        if key == "temperature" and alias == "temperature_c":
            raw = raw + 273.15
        pieces.append(raw)
    return func.coalesce(*pieces)


def measured_hits(
    db: Session,
    *,
    scalar_keys: tuple[str, ...],
    low: float,
    high: float,
    unit: str,
    limit: int,
    visible: Select[Any] | None = None,
    convert: bool = True,
    condition: ConditionFilter | None = None,
    min_tier: int | None = None,
    center: float | None = None,
) -> list[Hit]:
    """**시험으로 잰 값**에서 찾는다 — 채택된 처리 결과의 스칼라.

    셋 중 제일 믿을 만한 값인데 전에는 이것만 빠져 있었다(2026-09-12). 어느 스칼라가
    이 물성인지는 계산이 선언한다(`Produced.property_key`) — 여기는 그 이름들만
    받는다. **채택된 결과만** 본다: 돌려만 보고 안 정한 시도까지 세면 한 시험이
    값을 여럿 든다.
    """
    if not scalar_keys:
        return []
    element = func.jsonb_array_elements(ProcessingResult.scalars).table_valued("value")
    scalar_key = cast(element.c.value, JSONB)["key"].astext
    scalar_value = cast(cast(element.c.value, JSONB)["value"].astext, Float)
    query = (
        select(
            Material.id,
            Material.record_name,
            TestRun.record_name,
            scalar_key,
            scalar_value,
            ProcessingResult.stages,
        )
        .select_from(ProcessingResult)
        .join(TestRun, TestRun.adopted_result_id == ProcessingResult.id)
        .join(Specimen, Specimen.id == TestRun.specimen_id)
        .join(Sample, Sample.id == Specimen.sample_id)
        .join(Material, Material.id == Sample.material_id)
        .join(element, true())
        .where(
            TestRun.deleted_at.is_(None),
            Material.deleted_at.is_(None),
            scalar_key.in_(scalar_keys),
            scalar_value >= low,
            scalar_value <= high,
        )
        .order_by(
            # 위와 같은 이유로 동점에 앞뒤를 준다.
            *(
                (func.abs(scalar_value - center), scalar_value)
                if center is not None
                else (scalar_value,)
            )
        )
        .limit(MAX_ROWS)
    )
    if visible is not None:
        query = query.where(Material.id.in_(visible))
    if condition is not None:
        # 시험의 조건은 **그 시험 종류의 조건 칸 이름**으로 저장돼 있다. 어느 칸이 이 표준
        # 조건인지는 정의(`canonical_key`)가 말한다 — 부서마다 `temp`·`temperature` 로
        # 갈려도 여기서 한 키로 모인다. 칸을 안 이은 시험 종류는 안 걸린다.
        field = TestConditionField
        query = query.join(
            field,
            (field.test_type_id == TestRun.test_type_id)
            & (field.canonical_key == condition.key),
        ).where(
            cast(TestRun.conditions[field.key].astext, Float).between(
                condition.low, condition.high
            )
        )

    # **재료·방법별로 묶는다.** 시편 3장이면 값이 셋인데 그것을 3줄로 내면 사람은
    # 「같은 재료가 왜 셋이지」 가 되고, 방법을 안 가르고 묶으면 0.2% 와 0.5%
    # 오프셋이 한 평균에 섞인다.
    bucket: dict[tuple[uuid.UUID, str, str], list[tuple[float, str]]] = {}
    names: dict[uuid.UUID, str] = {}
    for material_id, name, run_name, key, value, stages in db.execute(query).all():
        names[material_id] = name
        method = _method_of(key, stages)
        bucket.setdefault((material_id, key, method), []).append((float(value), run_name))

    made: list[Hit] = []
    for (material_id, key, method), values in bucket.items():
        numbers = [one for one, _ in values]
        mean = sum(numbers) / len(numbers)
        spread = (
            (sum((one - mean) ** 2 for one in numbers) / (len(numbers) - 1)) ** 0.5
            if len(numbers) > 1
            else None
        )
        runs = ", ".join(run for _, run in values[:3]) + (" …" if len(values) > 3 else "")
        tier = tiers.measured_tier(len(values))
        if min_tier is not None and tier > min_tier:
            continue
        made.append(
            Hit(
                world="measured",
                material_id=material_id,
                material_name=names[material_id],
                value_si=mean,
                value_shown=units.from_si(mean, unit) if convert else mean,
                unit_shown=unit,
                quality_tier=tier,
                source_detail=f"{key} · {runs}",
                count=len(values),
                spread_si=spread,
                method=method,
            )
        )
    made.sort(key=rank(center))
    return made[:limit]


def _method_of(scalar_key: str, stages: list[dict[str, Any]] | None) -> str:
    """이 값을 낸 단계와 그 인자 — 「항복강도 · offset_strain=0.002」.

    인자는 그 단계가 **선언한 것 중 숫자·선택 칸만**(열 이름·참조는 뺀다). 기본값과
    같아도 적는다 — 「오프셋 0.2%」 는 기본값이어도 값의 뜻이다.
    """
    plugin = next(
        (
            one
            for one in registry.list_plugins()
            if one.kind in ("processing", "grouping")
            and any(made.key == scalar_key for made in one.makes_values)
        ),
        None,
    )
    if plugin is None:
        return scalar_key
    options: dict[str, Any] = {}
    for stage in stages or []:
        if stage.get("plugin") == plugin.id:
            options = stage.get("options") or {}
    # **앞 단계가 낸 값을 받는 칸은 방법이 아니다.** 항복강도 단계의 `youngs_modulus`
    # 는 탄성계수 단계가 잰 값이 흘러든 것이라 시편마다 다르다 — 그것을 방법에 넣으면
    # 시편마다 다른 방법이 되어 묶이지 않는다. 저장된 옵션은 이미 숫자로 풀려 있어
    # 참조였는지 알 수 없으니, 어느 계산이든 내는 이름이면 뺀다.
    carried = {
        made.key
        for one in registry.list_plugins()
        if one.kind in ("processing", "grouping")
        for made in one.makes_values
    }
    parts: list[str] = []
    for spec in plugin.params:
        if spec.role is not None or spec.type not in ("float", "int", "choice"):
            continue
        if spec.name in carried or spec.links_to in carried:
            continue
        value = options.get(spec.name)
        if value is None or (isinstance(value, str) and value.startswith("@")):
            continue
        parts.append(
            f"{spec.name}={value:g}" if isinstance(value, float) else f"{spec.name}={value}"
        )
    return plugin.label + (" · " + ", ".join(parts) if parts else "")


def internal_hits(
    db: Session,
    *,
    item: str,
    low: float,
    high: float,
    unit: str,
    limit: int,
    visible: Select[Any] | None = None,
    scale: str | None = None,
    convert: bool = True,
    condition: ConditionFilter | None = None,
    min_tier: int | None = None,
    center: float | None = None,
) -> list[Hit]:
    """사내 재료의 선언 물성에서 찾는다.

    선언 물성은 JSONB 라 SQL 로 파고든다 — `declared_properties` 의 각 항목이
    `{"item": "항복강도", "points": [{"value_si": …}]}` 모양이다.

    **권한은 부르는 쪽이 준다**(`visible`). 이 모듈은 값만 안다.
    """
    wanted = cast([{"item": item}], JSONB)
    # **재료와 시료 둘 다 본다.** 문헌·규격값은 재료에, 밀시트값(경도·강도)은 시료에
    # 붙는다(ADR 0016) — 재료만 보면 시료 층 항목은 영영 안 잡힌다.
    query = select(
        Material.id, Material.record_name, Material.declared_properties, sa_null()
    ).where(
        Material.deleted_at.is_(None),
        # **JSONB 를 통째로 훑기 전에 그 항목을 든 재료로 좁힌다.** `@>` 는
        # GIN 색인을 탄다 — 없으면 재료 전부의 JSON 을 파이썬으로 연다.
        Material.declared_properties.op("@>")(wanted),
    )
    sample_query = (
        select(Material.id, Material.record_name, Sample.declared_properties, Sample.lot_no)
        .join(Material, Material.id == Sample.material_id)
        .where(
            Sample.deleted_at.is_(None),
            Material.deleted_at.is_(None),
            Sample.declared_properties.op("@>")(wanted),
        )
    )
    if visible is not None:
        query = query.where(Material.id.in_(visible))
        sample_query = sample_query.where(Material.id.in_(visible))
    rows = [
        *db.execute(query.limit(MAX_ROWS)).all(),
        *db.execute(sample_query.limit(MAX_ROWS)).all(),
    ]

    made: list[Hit] = []
    for material_id, name, declared, lot_no in rows:
        for entry in declared or []:
            if entry.get("item") != item:
                continue
            # **눈금이 다르면 다른 값이다.** HRC 60 은 비커스 검색에 안 낀다.
            if scale is not None and entry.get("scale") != scale:
                continue
            tier = tiers.declared_tier(entry.get("source"))
            if min_tier is not None and tier > min_tier:
                continue
            for point in entry.get("points") or []:
                value = point.get("value_si")
                if not isinstance(value, int | float):
                    continue
                if condition is not None:
                    # 선언 점이 아는 조건은 온도(`temperature_k`)뿐이다. 다른 조건을 물으면
                    # 선언값은 **그 조건에서 잰 것이 아니라** 안 걸린다 — 없는 것을 있는 척하지
                    # 않는다.
                    at = point.get("temperature_k") if condition.key == "temperature" else None
                    if not isinstance(at, int | float) or not (
                        condition.low <= float(at) <= condition.high
                    ):
                        continue
                if low <= value <= high:
                    made.append(
                        Hit(
                            world="internal",
                            material_id=material_id,
                            material_name=name,
                            value_si=float(value),
                            quality_tier=tier,
                            # 표가 모르는 눈금(HV)은 환산 없이 — 저장된 값이 그 눈금이다.
                            value_shown=units.from_si(value, unit)
                            if convert
                            else float(value),
                            unit_shown=unit,
                            source_detail=(
                                f"로트 {lot_no} · {entry.get('reference') or ''}".rstrip(" ·")
                                if lot_no
                                else entry.get("reference")
                            ),
                        )
                    )
                    break
    made.sort(key=rank(center))
    return made[:limit]


def si_unit_of(db: Session, property_key: str) -> str:
    definition = db.scalar(
        select(CatalogDefinition).where(CatalogDefinition.key == property_key)
    )
    return (definition.si_unit or "") if definition else ""
