"""허용치 조회 — 문헌 값을 **재질 · 고장모드 · 지표 · 시험법**으로 묶어 대표 · 하한 · 상한으로.

실측(2026-11-17, HWAX 연결): 해석 플랫폼이 파손 판정에 쓸 허용치를 받을 길이 없어, 사람이 문헌
카탈로그 값을 손으로 json 에 모았다. 여러 재료를 가로지르는 도구는 `find_by_property`
하나였는데 조건 · 출처 · 시험규격을 빼고 돌려주어, 재료마다 상세를 다시 열어야 했다. 하한 ·
상한은 칸이 아니라 따로 된 줄의 조건 글자에 흩어져 있었다(`value_bounds`).

## 한 줄 = 한 재료 · 한 물성 · 한 조건

같은 재료 · 물성에서 **범위 표지를 뺀 조건이 같은 값**들을 한 줄로 묶는다. 「400 to 700」 이 두
줄로 나뉜 하한과 상한이 같은 줄로 돌아오고, 온도 · 방향이 다른 값은 다른 줄이다(평균하지 않는다
— 다른 조건을 섞으면 아무것도 아닌 수가 된다).

    representative   범위의 끝이 아닌 값 중 순위가 가장 앞선 것(`representative.rank`)
    lower · upper    하한 · 상한 줄 중 앞선 것
    others           같은 줄에 더 있는 값의 수 — 출처가 다른 같은 조건의 값

**문헌만이다**(사용자 결정, 1차). 사내 재료를 주면 이어진 문헌 재료로 푼다. 시험으로 잰
값의 하위 5 % 같은 사내 허용치는 다음이다 — 표본이 적을 때 P5 를 쓰지 않기로 한
결정(ADR 0041)과 함께 정해야 한다.

## 고장모드 · 지표 표

물성 분류에 고장모드 축이 없어(분야 · 물성군 · 물성 셋) 고장모드는 물성 키에 숨어 있다. 여기서
키마다 (고장모드, 지표, 하중)을 적는다 — 새 키가 허용치로 쓰이려면 이 표에 한 줄을 더한다. 식의
계수(σf′ · Johnson-Cook A 같은 것)는 허용치가 아니라 모델이라 넣지 않는다.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.catalog.models import (
    QUALITY_TIERS,
    CatalogDefinition,
    CatalogMaterial,
    CatalogSource,
    CatalogValue,
)
from app.shared import declared_catalog, representative, value_bounds


@dataclass(frozen=True)
class Mode:
    failure_mode: str
    metric: str
    loading: str | None = None
    """물성 키가 정하는 하중 — 굽힘강도는 굽힘, 중첩전단강도는 전단. 비면 조건(`loading` ·
    `mode`)에서 읽는다."""


#: 고장모드 — 사람이 읽는 이름.
FAILURE_MODES: dict[str, str] = {
    "yield": "항복",
    "ultimate": "극한(파단 강도)",
    "fracture_strain": "파단 변형",
    "fatigue": "피로",
    "toughness": "파괴인성 · 균열",
    "adhesion": "접합 · 박리",
    "impact": "충격",
}

#: 지표 — 사람이 읽는 이름.
METRICS: dict[str, str] = {
    "stress": "응력",
    "strain": "변형률",
    "stress_intensity": "응력확대계수",
    "line_force": "단위 폭당 힘",
    "energy": "에너지",
    "energy_per_area": "단위 면적당 에너지",
}

#: 물성 키 → (고장모드, 지표, 하중). **허용치로 읽을 수 있는 것만** — 모델 계수는 뺀다.
MODES: dict[str, Mode] = {
    "mechanical.yield_strength": Mode("yield", "stress", "tension"),
    "mechanical.yield_strength_at_rate": Mode("yield", "stress", "tension"),
    "mechanical.tensile_strength": Mode("ultimate", "stress", "tension"),
    "mechanical.tensile_strength_at_rate": Mode("ultimate", "stress", "tension"),
    "mechanical.compressive_strength": Mode("ultimate", "stress", "compression"),
    "mechanical.flexural_strength": Mode("ultimate", "stress", "bending"),
    "mechanical.shear_strength": Mode("ultimate", "stress", "shear"),
    "mechanical.elongation_at_break": Mode("fracture_strain", "strain", "tension"),
    "mechanical.reduction_of_area": Mode("fracture_strain", "strain", "tension"),
    "mechanical.true_fracture_ductility": Mode("fracture_strain", "strain", "tension"),
    "mechanical.fatigue_strength": Mode("fatigue", "stress"),
    "mechanical.fracture_toughness": Mode("toughness", "stress_intensity"),
    "local.mechanical.fatigue_crack_growth_threshold": Mode("toughness", "stress_intensity"),
    "interface.peel_strength": Mode("adhesion", "line_force", "peel"),
    "interface.lap_shear_strength": Mode("adhesion", "stress", "shear"),
    "interface.die_shear_strength": Mode("adhesion", "stress", "shear"),
    "interface.cohesive_strength": Mode("adhesion", "stress"),
    "interface.cohesive_energy_mode1": Mode("adhesion", "energy_per_area", "mode I"),
    "interface.cohesive_energy_mode2": Mode("adhesion", "energy_per_area", "mode II"),
    "mechanical.impact_energy_charpy": Mode("impact", "energy"),
    "mechanical.impact_strength_charpy": Mode("impact", "energy_per_area"),
    "mechanical.impact_strength_izod": Mode("impact", "line_force"),
}

#: 범위 표지 — 묶을 때 조건에서 뺀다(같은 범위의 하한 · 상한이 한 줄로 돌아오게).
_BOUND_KEYS = frozenset({"bound", "value_type", "statistic"})
#: 응력 성분을 말하는 조건 칸.
_COMPONENT_KEYS = ("direction", "loading", "mode", "test_mode", "component", "stress_state")
#: 시험법을 말하는 조건 칸 — 앞이 이긴다.
_METHOD_KEYS = ("test_standard", "standard", "test_method", "test")

#: 한 번에 볼 수 있는 문헌 재료 수 · 줄 수.
MAX_MATERIALS = 50
MAX_ROWS = 500


def test_method_of(conditions: dict[str, Any]) -> str | None:
    for key in _METHOD_KEYS:
        found = conditions.get(key)
        if isinstance(found, str) and found.strip():
            return found.strip()
    return None


def _signature(conditions: dict[str, Any]) -> str:
    kept = {key: conditions[key] for key in sorted(conditions) if key not in _BOUND_KEYS}
    return repr(kept)


def _value(value: CatalogValue, source: CatalogSource | None) -> dict[str, Any]:
    caveats: list[str] = []
    if value.quality_tier == 4:
        caveats.append("tier 4 — 계산 · 추정 · 가정, 실측이 아니다")
    if (value.conditions or {}).get("assumption") is True:
        caveats.append("가정값으로 표시돼 있다")
    return {
        "value_id": value.id,
        "value_si": declared_catalog.value_si(value),
        "value": value.value_num,
        "unit": value.unit,
        "quality_tier": value.quality_tier,
        "tier": QUALITY_TIERS.get(value.quality_tier, str(value.quality_tier)),
        "method": value.method,
        "source": (
            {
                "title": source.title or source.publisher,
                "year": source.year,
                "doi": source.doi,
                "kind": source.kind,
            }
            if source is not None
            else None
        ),
        "source_detail": value.source_detail,
        "caveat": " · ".join(caveats) or None,
    }


def collect(
    db: Session,
    material_ids: list[uuid.UUID],
    *,
    failure_mode: str | None = None,
    metric: str | None = None,
    property_keys: list[str] | None = None,
    test_method: str | None = None,
    max_tier: int | None = None,
    limit: int = 200,
) -> tuple[list[dict[str, Any]], int]:
    """문헌 재료들 → 허용치 줄. 돌려주는 것: (줄, 자르기 전 줄 수)."""
    keys = [
        key
        for key, mode in MODES.items()
        if (failure_mode is None or mode.failure_mode == failure_mode)
        and (metric is None or mode.metric == metric)
        and (not property_keys or key in property_keys)
    ]
    if not keys or not material_ids:
        return [], 0
    query = (
        select(CatalogValue, CatalogSource)
        .outerjoin(CatalogSource, CatalogSource.id == CatalogValue.source_id)
        .where(
            CatalogValue.material_id.in_(material_ids),
            CatalogValue.property_key.in_(keys),
            CatalogValue.value_num.is_not(None),
            # 곡선 · 산점의 점은 허용치가 아니다(S-N 점 하나가 피로 허용치로 서면 안 된다).
            CatalogValue.series_id.is_(None),
            CatalogValue.scatter_point.is_(False),
            CatalogValue.source_missing_at.is_(None),
        )
    )
    if max_tier is not None:
        query = query.where(CatalogValue.quality_tier <= max_tier)
    rows = db.execute(query).all()
    materials = {
        one.id: one
        for one in db.scalars(
            select(CatalogMaterial).where(CatalogMaterial.id.in_(material_ids))
        )
    }
    names = dict(
        db.execute(
            select(CatalogDefinition.key, CatalogDefinition.name).where(
                CatalogDefinition.key.in_(keys)
            )
        )
        .tuples()
        .all()
    )
    si_units = dict(
        db.execute(
            select(CatalogDefinition.key, CatalogDefinition.si_unit).where(
                CatalogDefinition.key.in_(keys)
            )
        )
        .tuples()
        .all()
    )
    wanted = test_method.casefold().strip() if test_method else None
    groups: dict[
        tuple[uuid.UUID, str, str], list[tuple[CatalogValue, CatalogSource | None]]
    ] = {}
    for value, source in rows:
        if representative.is_term(value):
            continue
        conditions = representative.semantic_conditions(value.conditions)
        if wanted and wanted not in (test_method_of(conditions) or "").casefold():
            continue
        groups.setdefault(
            (value.material_id, value.property_key, _signature(conditions)), []
        ).append((value, source))

    out: list[dict[str, Any]] = []
    for (material_id, key, _), members in groups.items():
        ranked = sorted(members, key=lambda pair: representative.rank(pair[0]))
        middle = [pair for pair in ranked if value_bounds.side(pair[0].conditions) is None]
        lower = [pair for pair in ranked if value_bounds.side(pair[0].conditions) == "lower"]
        upper = [pair for pair in ranked if value_bounds.side(pair[0].conditions) == "upper"]
        first = ranked[0][0]
        conditions = {
            key_: item
            for key_, item in representative.semantic_conditions(first.conditions).items()
            if key_ not in _BOUND_KEYS
        }
        mode = MODES[key]
        component = {
            name: conditions[name]
            for name in _COMPONENT_KEYS
            if isinstance(conditions.get(name), str | int | float)
        }
        caveats: list[str] = []
        if not middle:
            caveats.append("범위의 끝만 있다 — 가운데(대표) 값이 없다")
        material = materials.get(material_id)
        shown = middle[:1] + lower[:1] + upper[:1]
        out.append(
            {
                "catalog_material_id": material_id,
                "material": material.name if material else None,
                "category": material.category if material else None,
                "property_key": key,
                "property": names.get(key) or key,
                "failure_mode": mode.failure_mode,
                "metric": mode.metric,
                "si_unit": si_units.get(key),
                "loading": mode.loading or component.get("loading") or component.get("mode"),
                "stress_component": component,
                "temperature_k": representative.temperature_of(first.conditions),
                "test_method": test_method_of(conditions),
                "conditions": conditions,
                "representative": _value(*middle[0]) if middle else None,
                "lower": _value(*lower[0]) if lower else None,
                "upper": _value(*upper[0]) if upper else None,
                "others": len(members) - len(shown),
                "caveat": " · ".join(caveats) or None,
            }
        )
    # 재료 → 고장모드 → 물성 → 상온에 가까운 것 차례.
    out.sort(
        key=lambda row: (
            str(row["material"] or ""),
            list(FAILURE_MODES).index(row["failure_mode"]),
            row["property_key"],
            representative.temperature_distance(row["conditions"]),
        )
    )
    return out[:limit], len(out)
