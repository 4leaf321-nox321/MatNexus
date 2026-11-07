"""문헌의 응력-변형률 한 벌 → 덱 — **지은 곡선보다 잰 곡선** (2026-11-08, ADR 0067 남은 것).

문헌 카탈로그에 곡선이 한 벌로 들어오면서(ADR 0067) 응력-변형률 곡선이 쌓였다(개발 DB 193벌 ·
41재료, 2026-11-08 — 고무 181 · 탄성체 12). 덱은 그 곡선을 안 읽고 스칼라로 지었다:

- **고무**: 초탄성 벌이 없으면 E 에서 Neo-Hookean(C10 = E/6). 곡선이 있는 고무 41개 가운데
  13개가 벌이 없었고, 그중 넷은 E 도 없어 덱에서 아예 빠졌다.
- **그 밖**: 「곡선 합성」 이 E · 항복 · 인장 · 연신율로 곡선을 지었다.

이제 곡선이 있으면 그것을 쓴다:

    고무    벌이 없을 때 그 곡선에 식을 맞춘다(Neo-Hookean · Mooney-Rivlin · Yeoh)
            — 벌 > 맞춤 > E/6
    그 밖   공칭 곡선을 진응력 · 진소성변형률 표로 옮긴다(`matcore.plastic_table`)
            — 잰 곡선 > 합성

## 곡선이 여럿이면

문헌 덱은 고를 화면이 없어서 **정한 차례로 하나를 고르고 나머지를 각주로 말한다**
(초탄성 벌과 같은 짜임, ADR 0070):

    ① 등급이 좋은 것
    ② 시험 모드 — 인장 > 압축(덱은 어떤 하중이 걸릴지 모르고 만드는 기본값이다)
    ③ 갈림 조건이 기본값인 것 — 노화 0 시간 · 보관 「none」 · 충전 0 이 노화 840 시간보다
      앞선다
    ④ 상온에 가까운 것(대표값 고르기와 같은 잣대)
    ⑤ 점이 많은 것 · 이름표

## 식을 고르는 차례

덱 기본값 범위(인장 100 % · 압축 50 % · 등이축 · 평면 전단 50 %)에서 **안정한 것**이 먼저,
그다음 상대 RMSE 가 작은 것이다. 견준 식의 RMSE 는 각주에 남긴다 — 「왜 Yeoh 인가」 를
덱만 받은 사람이 되짚을 수 있게. 맞춘 식은 출판된 벌이 아니라 **우리가 맞춘 것**이라 블록
이름표에 「문헌 곡선 맞춤」 을 단다.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.catalog.models import (
    QUALITY_TIERS,
    CatalogMaterial,
    CatalogSeries,
    CatalogSource,
    CatalogValue,
)
from app.shared import hyperelastic_sets, literature_material, representative
from matcore import fitting, plastic_table
from matcore.cards.hyperelastic import FromSet, stability
from matcore.fitting import hyperelastic as hyperelastic_fits

#: 응력-변형률 한 벌의 물성 열 → 시험 모드. 축은 공칭 변형률(%)이고 응력은 공칭(Pa)이다.
CURVE_KEYS = {
    "mechanical.tensile_stress_at_strain": "tension",
    "local.mechanical.compressive_stress_at_strain": "compression",
}
STRAIN_AXIS = "strain_pct"

#: 덱이 받고 안정 범위를 셀 수 있는 식 — 다항식 꼴만(`matcore.cards.hyperelastic.stability`).
#: Ogden 은 출처마다 μ 규약이 달라 문헌 벌도 안 옮기는 식이라 여기서도 맞추지 않는다.
FIT_FAMILIES = ("yeoh", "mooney_rivlin", "neo_hookean")

#: 모드의 차례 — 인장이 먼저다(ADR 0070 의 ③과 같은 판단).
MODE_ORDER = {"tension": 0, "compression": 1}

#: 갈림 조건에서 「기본값」 으로 읽는 글자 — 노화 안 함 · 보관 안 함 · 충전 안 함.
_BASELINE_WORDS = frozenset({"", "none", "no", "null", "untreated", "unaged", "as received"})
#: 갈림이 아니라 설명인 칸 — 몇 개 시편의 평균인지 · 어디서 왔는지. 온도는 ④가 따로 잰다.
_DESCRIPTIVE_KEYS = frozenset(
    {"statistic", "data_origin", "source_label", "temperature_k", "temperature_c"}
)


@dataclass(frozen=True)
class Curve:
    series_id: uuid.UUID
    label: str
    mode: str
    """`tension` · `compression`."""
    tier: int
    conditions: dict[str, Any]
    cite: str
    strain: np.ndarray
    """공칭 변형률 — **비율**(저장은 %)."""
    stress: np.ndarray
    """공칭 응력(Pa). 압축도 양수로 적혀 있다."""

    @property
    def tier_text(self) -> str:
        return f"tier {self.tier}: {QUALITY_TIERS.get(self.tier, str(self.tier))}"

    @property
    def span(self) -> str:
        """각주의 꼬리 — 「단축 인장 공칭 50점 · 0.4~368 %」."""
        mode = (
            hyperelastic_fits.TENSION
            if self.mode == "tension"
            else hyperelastic_fits.COMPRESSION
        )
        return (
            f"{mode} 공칭 {len(self.strain)}점 · "
            f"{self.strain[0] * 100:.3g}~{self.strain[-1] * 100:.3g} %"
        )


def _baseline(value: Any) -> bool:
    if value is None or (isinstance(value, bool) and not value):
        return True
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value) == 0.0
    return str(value).strip().lower() in _BASELINE_WORDS


def _variant(conditions: Mapping[str, Any]) -> int:
    """기본값이 아닌 갈림 조건의 수 — 적을수록 그 재료의 「바탕」 곡선이다."""
    return sum(
        1
        for key, value in conditions.items()
        if key not in _DESCRIPTIVE_KEYS and not _baseline(value)
    )


def _rank(one: Curve) -> tuple[Any, ...]:
    return (
        one.tier,
        MODE_ORDER.get(one.mode, 9),
        _variant(one.conditions),
        representative.temperature_distance(one.conditions),
        -len(one.strain),
        one.label,
    )


def curves(
    db: Session, material_id: uuid.UUID, modes: tuple[str, ...] = ("tension", "compression")
) -> list[Curve]:
    """재료의 응력-변형률 벌 — 고르는 차례(`_rank`)대로. 점이 둘 안 되는 벌은 뺀다."""
    keys = [key for key, mode in CURVE_KEYS.items() if mode in modes]
    series = db.scalars(
        select(CatalogSeries).where(
            CatalogSeries.material_id == material_id,
            CatalogSeries.kind == "curve",
            CatalogSeries.x_key == STRAIN_AXIS,
        )
    ).all()
    wanted = {
        one.id: key for one in series for key in keys if list(one.columns or []) == [key]
    }
    if not wanted:
        return []
    points: dict[uuid.UUID, list[tuple[float, float]]] = {one: [] for one in wanted}
    first: dict[uuid.UUID, CatalogValue] = {}
    for value in db.scalars(
        select(CatalogValue).where(
            CatalogValue.series_id.in_(list(wanted)),
            CatalogValue.value_num.is_not(None),
            CatalogValue.source_missing_at.is_(None),
        )
    ):
        assert value.series_id is not None
        if value.property_key != wanted[value.series_id]:
            continue
        x = (value.conditions or {}).get(STRAIN_AXIS)
        if not isinstance(x, int | float) or isinstance(x, bool):
            continue
        points[value.series_id].append((float(x) / 100.0, float(value.value_num or 0.0)))
        first.setdefault(value.series_id, value)
    sources = {
        one.id: one
        for one in db.scalars(
            select(CatalogSource).where(
                CatalogSource.id.in_([one.source_id for one in series if one.source_id])
            )
        )
    }
    found: list[Curve] = []
    for one in series:
        if one.id not in wanted or len(points[one.id]) < 2:
            continue
        pairs = sorted(points[one.id])
        conditions = representative.semantic_conditions(one.conditions)
        found.append(
            Curve(
                series_id=one.id,
                label=one.label,
                mode=CURVE_KEYS[wanted[one.id]],
                tier=one.quality_tier,
                conditions=conditions,
                cite=literature_material.cite_of(
                    first[one.id], sources.get(one.source_id) if one.source_id else None
                )
                or "출처 미상",
                strain=np.asarray([x for x, _ in pairs], dtype=np.float64),
                stress=np.asarray([y for _, y in pairs], dtype=np.float64),
            )
        )
    return sorted(found, key=_rank)


def _rest(others: list[Curve]) -> list[str]:
    if not others:
        return []
    shown = ", ".join(f"「{one.label}」" for one in others[:3])
    more = f" 외 {len(others) - 3}벌" if len(others) > 3 else ""
    return [f"다른 응력-변형률 곡선 {len(others)}벌({shown}{more})은 안 썼습니다."]


# ── 고무: 곡선에 초탄성 식을 맞춘다 ─────────────────────────────────────────────


@dataclass(frozen=True)
class _Fit:
    made: FromSet
    result: fitting.FitResult
    stable: bool


def _fit(curve: Curve, key: str) -> _Fit | None:
    base = fitting.FAMILIES[key]
    family = (
        base
        if curve.mode == "tension"
        # 같은 식을 압축 축에 뒤집어 건다 — 계수 이름 · 덱으로 옮기는 법이 인장과 같다.
        else hyperelastic_fits.compression(
            base, x_column="strain_compression", y_column="stress_compression"
        )
    )
    x, y, _ = family.prepare(curve.strain, curve.stress)
    try:
        result = fitting.fit_with(family, x, y)
    except fitting.FittingError:
        return None
    values = {one.name: one.value for one in result.parameters}
    # 초기 전단탄성률이 0 이하인 계수는 첫 증분에서 멈춘다 — 문헌 벌과 같은 거절(`_stable`).
    if 2.0 * (values.get("c10", 0.0) + values.get("c01", 0.0)) <= 0.0:
        return None
    found = stability(values)
    return _Fit(FromSet(key, values), result, found is None or found.ok)


def fitted_hyperelastic(
    db: Session, material: CatalogMaterial
) -> tuple[dict[str, Any] | None, list[str]]:
    """초탄성 벌이 없는 고무 — 그 재료의 응력-변형률 곡선에 식을 맞춘 블록과 각주."""
    fitting.load_builtin()
    found = curves(db, material.id)
    if not found:
        return None, []
    chosen = found[0]
    fits = [one for key in FIT_FAMILIES if (one := _fit(chosen, key)) is not None]
    if not fits:
        return None, [
            f"문헌 곡선 「{chosen.label}」 에 초탄성 식을 맞추지 못했습니다 — 점이 모자라거나 "
            "식이 성립하지 않는 구간입니다."
        ]
    fits.sort(
        key=lambda one: (
            0 if one.stable else 1,
            one.result.relative_rmse,
            hyperelastic_sets.RICHNESS.get(one.made.family, 9),
        )
    )
    best = fits[0]
    name = hyperelastic_sets.FAMILY_LABELS.get(best.made.family, best.made.family)
    block = hyperelastic_sets.block_of(best.made, origin="문헌 곡선 맞춤", mode=chosen.mode)
    block["values"].update(
        relative_rmse=best.result.relative_rmse,
        r_squared=best.result.r_squared,
        max_residual=best.result.max_residual,
        strain_min=best.result.strain_min,
        strain_max=best.result.strain_max,
    )
    block["origin"] = "fitted"
    said = [
        f"초탄성 = {name} — 문헌 곡선 「{chosen.label}」({chosen.span})에 맞춘 계수 · "
        f"상대 RMSE {best.result.relative_rmse * 100:.3g} % — {chosen.cite} "
        f"[{chosen.tier_text}]. "
        "출판된 벌이 아니라 이 곡선에 맞춘 값입니다.",
    ]
    others = [
        f"{hyperelastic_sets.FAMILY_LABELS.get(one.made.family, one.made.family)} "
        f"{one.result.relative_rmse * 100:.3g} %" + ("" if one.stable else " · 불안정")
        for one in fits[1:]
    ]
    if others:
        said.append("견준 식(상대 RMSE): " + " · ".join(others))
    said.append(
        hyperelastic_fits.only_note(
            hyperelastic_fits.TENSION
            if chosen.mode == "tension"
            else hyperelastic_fits.COMPRESSION
        )
    )
    # 적합이 남긴 경고(RMSE 가 큼 · 경계에 붙음 · 적합 구간 안의 연화). 앞의 두 줄은 구간
    # 설명이라 뺀다.
    said.extend(best.result.notes[2:])
    warned = hyperelastic_sets.unstable_note(best.made)
    if warned:
        said.append(warned)
    said.extend(_rest(found[1:]))
    return block, said


# ── 그 밖: 공칭 곡선을 소성 표로 ────────────────────────────────────────────────


def measured_plastic(
    db: Session, material: CatalogMaterial, youngs_modulus: Any
) -> tuple[list[dict[str, float]] | None, list[str]]:
    """재료의 인장 응력-변형률 곡선 → *MAT_024 소성 표와 각주. 곡선이 없으면 `(None, [])`.

    E 는 **카드의 탄성 블록이 쓰는 그 값**을 받는다 — 곡선의 기울기로 따로 재지 않는다.
    """
    found = curves(db, material.id, modes=("tension",))
    if not found:
        return None, []
    chosen = found[0]
    if not isinstance(youngs_modulus, int | float) or youngs_modulus <= 0:
        return None, [
            f"문헌 곡선 「{chosen.label}」 이 있지만 탄성계수가 없어 소성 표로 옮기지 "
            "못했습니다 — "
            "진소성변형률은 E 로 탄성 몫을 빼야 나옵니다."
        ]
    made = plastic_table.from_nominal(chosen.strain, chosen.stress, float(youngs_modulus))
    if isinstance(made, str):
        return None, [f"문헌 곡선 「{chosen.label}」 을 소성 표로 옮기지 않았습니다 — {made}"]
    said = [
        f"소성 표 = 문헌 실측 곡선 「{chosen.label}」({chosen.span}) — {chosen.cite} "
        f"[{chosen.tier_text}]. 공칭 → 진응력 · 진소성변형률 {len(made.rows)}줄, "
        f"E = {float(youngs_modulus) / 1e9:.4g} GPa · 0.2 % 오프셋 항복 "
        f"{made.yield_stress / 1e6:.4g} MPa 부터.",
    ]
    if made.cut_strain is not None:
        said.append(
            f"최대 공칭 응력 점(변형률 {made.cut_strain * 100:.3g} %)에서 잘랐습니다 — "
            "그 뒤는 "
            "네킹이라 진응력 변환식(균일 변형)이 성립하지 않습니다."
        )
    if made.first_is_yield:
        said.append("곡선이 탄성 구간 없이 시작해 첫 점을 항복으로 봤습니다.")
    said.extend(_rest(found[1:]))
    return [dict(one) for one in made.rows], said
