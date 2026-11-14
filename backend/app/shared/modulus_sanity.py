"""처리 결과의 **탄성률이 말이 되는 값인가** — 막지 않고 경고한다(2026-11-14, VOC 43).

## 왜

단위 실수는 탄성률을 1000배 단위로 틀리게 한다 — 하중 kN 을 N 으로, 처짐 mm 를 m 로 읽으면
1/1000, 두께를 µm 로 넣으면 10⁹ 배, 단면적이 틀리면 10⁶ 배(실측). 처리 단계는 「0 이하」 만
거절해 그런 값이 카드 · 덱까지 갔다. 치수 자릿수 점검(`specimen_size.magnitude_gaps`)은 채널
숫자의 크기를 못 본다.

## 무엇과 견주나

    불가능        1 Pa 미만 · 2 TPa 초과 — 어느 재료에도 없는 값(다이아몬드가 1.2 TPa 쯤이다)
    재료군 범위    금속 · 세라믹 · 고무처럼 폭이 좁은 군의 1000배 실수를 잡는다
    선언값 대비    재료에 적어 둔 탄성률과 `DECLARED_RATIO` 배 넘게 다르면 — **실제로 잡는 힘은
                  여기서 나온다**(고분자는 5 kPa ~ 32 GPa 라 범위로는 「작게 틀린」 값을 못
                  잡는다)

## 왜 경고인가

이 저장소의 재료는 폭이 너무 넓다 — 문헌 카탈로그의 고분자만 5.6 kPa(PDMS) ~ 32 GPa(EMC)이고
하이드로젤은 1 kPa 아래다. 전역 하한을 1 MPa 로만 둬도 실제 값의 7.7 % 가 걸렸다. 막으면 진짜
값을 못 넣는다. 경고는 채택할 때 확인을 받고 카드 근거에 남는다(VOC 53~58 의 장치).

**범위 숫자는 잠정값이다** — 카탈로그 값의 최소 · 최대에 여유를 둔 것이라 사내 재료의 오경보를
말해 주지 못한다. 재료군 항목의 「탄성률 하한 · 상한」 칸(기준정보 편집)이 있으면 그것이
이긴다.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.modules.materials.models import Material, Sample, Specimen
from app.modules.tests.models import TestRun
from app.modules.vocabulary.models import VocabularyTerm
from app.shared import curvedata
from app.shared.text import compare_key
from matcore import processing, registry

#: 탄성률로 보는 물성 키 — **단계가 선언한 키**(`Produced.property_key`)로 고른다. 값 이름으로
#: 고르면 DMA 선형 구간 E′(`youngs_modulus` 라는 이름이지만 물성 키가 없다)와 와이블 계수가
#: 섞인다.
MODULUS_PROPERTY_KEYS = frozenset(
    {
        "mechanical.youngs_modulus",
        "mechanical.flexural_modulus",
        "mechanical.compressive_modulus",
    }
)

#: 어느 재료에도 없는 값(Pa). 하한은 아주 무른 젤(10~100 Pa)보다 아래다.
IMPOSSIBLE = (1.0, 2.0e12)

#: 재료에 적어 둔 탄성률과 이만큼(배) 다르면 말한다. 적층재의 굽힘 등가 E 는 인장 E 와 수십 %
#: 다를 수 있어 넉넉히 둔다 — 단위 실수는 10배 이상이다.
DECLARED_RATIO = 3.0

#: 재료군 → (하한, 상한) Pa. **잠정값**(문헌 카탈로그 2,306건의 군별 최소 · 최대에 여유).
FAMILY_RANGES: dict[str, tuple[float, float]] = {
    "metal": (5.0e9, 6.0e11),
    "ceramic": (1.0e9, 1.2e12),
    "polymer": (1.0e1, 6.0e10),  # 하이드로젤 ~ EMC
    "composite": (1.0e4, 6.0e11),  # 갭 패드 ~ 탄소섬유 적층
    "rubber": (1.0e3, 3.0e8),
    "foam": (1.0e2, 5.0e9),
}

#: 재료군 이름의 별칭 — 기준정보 값은 부서가 정해 이름이 갈린다.
FAMILY_ALIASES: dict[str, str] = {
    **{name: "metal" for name in ("metal", "metals", "금속", "steel", "alloy", "합금")},
    **{name: "ceramic" for name in ("ceramic", "ceramics", "세라믹", "glass", "유리")},
    **{
        name: "polymer"
        for name in ("polymer", "polymers", "plastic", "plastics", "고분자", "플라스틱")
    },
    **{name: "composite" for name in ("composite", "composites", "복합재", "복합재료")},
    **{name: "rubber" for name in ("rubber", "elastomer", "고무", "엘라스토머")},
    **{name: "foam" for name in ("foam", "foams", "폼", "발포체")},
}

#: 재료군 항목의 칸(기준정보) — 있으면 위 표를 이긴다.
MIN_FIELD = "modulus_min"
MAX_FIELD = "modulus_max"


def _gpa(value: float) -> str:
    """사람이 읽는 크기 — 자릿수가 요점이라 단위를 값에 맞춘다."""
    for scale, unit in ((1e9, "GPa"), (1e6, "MPa"), (1e3, "kPa")):
        if abs(value) >= scale:
            return f"{value / scale:.3g} {unit}"
    return f"{value:.3g} Pa"


def family_range(
    family: str | None, attributes: Mapping[str, Any] | None = None
) -> tuple[float, float] | None:
    """그 재료군의 탄성률 범위. 항목에 칸이 있으면 그것, 없으면 이름으로 표에서."""
    low = (attributes or {}).get(MIN_FIELD)
    high = (attributes or {}).get(MAX_FIELD)
    known = FAMILY_RANGES.get(FAMILY_ALIASES.get(compare_key(family), ""))
    if not isinstance(low, int | float) or not low > 0:
        low = known[0] if known else None
    if not isinstance(high, int | float) or not high > 0:
        high = known[1] if known else None
    if low is None and high is None:
        return None
    return (float(low or IMPOSSIBLE[0]), float(high or IMPOSSIBLE[1]))


def nearest_declared(
    points: Sequence[Mapping[str, Any]], temperature_k: float
) -> float | None:
    """선언 점 가운데 **시험 온도에 가장 가까운** 값. 첫 점(가장 낮은 온도)과 견주면 고온
    시험이 재료가 아니라 온도 탓으로 걸린다(`statistics` 의 spec-gap 과 같은 생각)."""
    usable = [
        one
        for one in points
        if isinstance(one.get("value_si"), int | float) and one["value_si"] > 0
    ]
    if not usable:
        return None
    best = min(
        usable,
        key=lambda one: abs(float(one.get("temperature_k") or 293.15) - temperature_k),
    )
    return float(best["value_si"])


def judge(
    value: float,
    label: str,
    *,
    family: str | None = None,
    attributes: Mapping[str, Any] | None = None,
    declared: float | None = None,
) -> list[str]:
    """그 값에 붙일 경고. 가장 센 것 하나와, 선언값과의 차이(있으면)."""
    if not value > 0:
        return []  # 0 이하는 단계가 이미 거절한다
    found: list[str] = []
    if not IMPOSSIBLE[0] <= value <= IMPOSSIBLE[1]:
        found.append(
            f"{label} {_gpa(value)} 는 어느 재료에도 없는 값입니다 — 하중 · 변위 채널의 "
            "단위와 시편 치수를 확인하세요."
        )
    else:
        bounds = family_range(family, attributes)
        if bounds is not None and not bounds[0] <= value <= bounds[1]:
            found.append(
                f"{label} {_gpa(value)} 가 재료군 「{family}」 의 범위({_gpa(bounds[0])} ~ "
                f"{_gpa(bounds[1])}) 밖입니다 — 단위(N · kN, mm · m)와 시편 치수를 확인하세요."
            )
    if declared is not None and declared > 0:
        ratio = max(value, declared) / min(value, declared)
        if ratio >= DECLARED_RATIO:
            found.append(
                f"{label} {_gpa(value)} 가 재료에 적어 둔 탄성률 {_gpa(declared)} 와 "
                f"{ratio:.3g}배 다릅니다 — 단위 · 시편 치수 · 적어 둔 값을 확인하세요."
            )
    return found


def _modulus_scalars(result: processing.PipelineResult) -> list[tuple[str, processing.Scalar]]:
    """`(단계 이름, 탄성률 값)` — 단계가 탄성률 물성 키로 선언한 값만."""
    found: list[tuple[str, processing.Scalar]] = []
    for stage in result.stages:
        keys = modulus_keys(stage.plugin)
        found.extend((stage.label, one) for one in stage.scalars if one.key in keys)
    return found


@dataclass(frozen=True)
class Context:
    """한 시험의 탄성률을 견줄 것 — 재료군 · 그 항목의 칸 · 재료에 적어 둔 탄성계수."""

    family: str | None
    attributes: Mapping[str, Any] | None
    declared: float | None


def context_of(db: Session, run: TestRun) -> Context | None:
    """그 시험의 재료에서 견줄 것을 읽는다. 재료를 못 따라가면 `None`."""
    specimen = db.get(Specimen, run.specimen_id)
    sample = db.get(Sample, specimen.sample_id) if specimen else None
    material = db.get(Material, sample.material_id) if sample else None
    if material is None:
        return None
    term = db.get(VocabularyTerm, material.family_term_id) if material.family_term_id else None
    temperature = (run.conditions or {}).get("temperature")
    temperature_k = float(temperature) if isinstance(temperature, int | float) else 293.15
    # 견줄 선언값은 **탄성계수 하나**다 — 굽힘 · 압축 탄성률을 따로 적는 재료는 드물고, 3배
    # 선이면 등가 E 와 인장 E 의 차이(수십 %)는 지나간다.
    keys = curvedata.declared_keys(db)
    declared: float | None = None
    for row in material.declared_properties or []:
        found = keys.get(str(row.get("item")))
        if found is not None and found.key == "youngs_modulus":
            declared = nearest_declared(row.get("points") or [], temperature_k)
            break
    return Context(material.family, term.attributes if term else None, declared)


def modulus_keys(plugin_id: str) -> set[str]:
    """그 단계가 탄성률 물성 키로 선언한 값 이름. 모르는 단계면 비었다."""
    try:
        plugin = registry.get(plugin_id)
    except KeyError:
        return set()
    return {
        made.key for made in plugin.makes_values if made.property_key in MODULUS_PROPERTY_KEYS
    }


def warnings_for(
    db: Session, run: TestRun, result: processing.PipelineResult
) -> list[dict[str, str]]:
    """이 결과의 탄성률 경고 — 처리 결과의 경고 목록에 그대로 싣는 꼴."""
    scalars = _modulus_scalars(result)
    if not scalars:
        return []
    context = context_of(db, run)
    if context is None:
        return []
    return [
        {"source": "step", "label": label, "message": message}
        for label, scalar in scalars
        for message in judge(
            float(scalar.value),
            scalar.label,
            family=context.family,
            attributes=context.attributes,
            declared=context.declared,
        )
    ]
