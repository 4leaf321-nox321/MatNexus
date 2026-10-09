"""문헌 흡습 값 → **흡습 블록** — 한 환경(온도 · 습도)의 셋을 고른다(2026-10-08).

문헌 카탈로그에는 포화 수분 농도 52값 · 흡습 팽창 계수 27값 · 확산계수 136값이 있다
(EMC · 언더필 · NCA · BT 기판). 사내 물성 항목과 안 이어져 있어서 선언 물성 길
(`literature_material`)로는 덱까지 못 간다. 이어도 그 길로는 안 된다 — 고를 것이 둘 있다:

**확산 종.** `physical.diffusion_coefficient` 에는 물 말고 용융 Sn 속 Cu · O₂ · Li⁺ 도 산다.
대표값을 그대로 쓰면 솔더의 흡습 확산계수 자리에 Cu 의 값이 선다. 그래서 확산 종
(`species` · `diffusing_species` · `medium`)이 물인 것만 쓰고, 종을 안 적은 값은 습도
조건이 있을 때만 물로 본다.

**환경.** 포화 농도는 온도 · 습도로 정해진다 — 같은 EMC 가 85 °C/85 %RH 에서 220, 60 %RH 에서
213 mol/m³ 이다. 셋을 따로 대표값으로 고르면 다른 환경의 값이 한 덱에 섞인다. 그래서
포화 농도가 선 환경 하나를 먼저 고르고(그 환경의 확산계수가 있는 것 · 85/85 · 등급 순),
확산계수를 같은 환경에서, 흡습 팽창 계수를 같은 온도에서 고른다. 같은 출처를 앞세운다 —
포화 농도와 확산계수는 대개 한 흡습 곡선에서 함께 나온 값이다.

**단위.** 포화 농도는 mol/m³ 로 적혀 있다. 블록은 kg/m³ 를 든다(`matcore.cards.moisture`) —
물의 몰질량을 곱한다.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.catalog.models import QUALITY_TIERS, CatalogSource, CatalogValue
from app.shared import literature_material, standard_conditions

BLOCK = "moisture"
DIFFUSION_KEY = "physical.diffusion_coefficient"
SATURATION_KEY = "physical.moisture_saturation"
EXPANSION_KEY = "physical.hygroscopic_expansion"
KEYS = (DIFFUSION_KEY, SATURATION_KEY, EXPANSION_KEY)

#: 물의 몰질량(kg/mol) — 포화 농도 mol/m³ → kg/m³.
WATER_MOLAR_MASS = 0.018015

#: 확산 종을 적는 조건 칸과, 물로 읽는 낱말.
SPECIES_FIELDS = ("species", "diffusing_species", "medium", "penetrant", "diffusant")
WATER_WORDS = ("h2o", "water", "moisture", "수분")

#: 앞세우는 환경 — JEDEC MSL 1 의 85 °C/85 %RH. 패키지 흡습 문헌의 기준 조건이다.
PREFERRED = (358.15, 0.85)
#: 같은 환경으로 보는 폭 — 섭씨 · 켈빈 환산의 끝자리와 85 · 0.85 의 끝자리.
TEMPERATURE_TOLERANCE = 0.5
HUMIDITY_TOLERANCE = 0.005


@dataclass(frozen=True)
class Found:
    value: CatalogValue
    temperature: float | None
    humidity: float | None

    @property
    def number(self) -> float:
        return float(self.value.value_num or 0.0)

    @property
    def tier(self) -> int:
        return int(self.value.quality_tier)


def is_water(conditions: dict[str, Any] | None, *, default: bool) -> bool:
    """확산 종이 물인가. 종을 안 적었으면 `default`."""
    named = [str(value) for key in SPECIES_FIELDS if (value := (conditions or {}).get(key))]
    if not named:
        return default
    return any(word in one.lower() for one in named for word in WATER_WORDS)


def _close(a: float | None, b: float | None, tolerance: float) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return abs(a - b) <= tolerance


def _found(value: CatalogValue) -> Found:
    return Found(
        value=value,
        temperature=standard_conditions.read_catalog(value.conditions, "temperature"),
        humidity=standard_conditions.read_catalog(value.conditions, "humidity"),
    )


def _at(one: Found, environment: tuple[float | None, float | None]) -> bool:
    """이 값이 그 환경의 것인가 — 온도가 같고, 습도는 둘 다 적혔으면 같아야 한다."""
    temperature, humidity = environment
    if not _close(one.temperature, temperature, TEMPERATURE_TOLERANCE):
        return False
    if one.humidity is None or humidity is None:
        return True
    return abs(one.humidity - humidity) <= HUMIDITY_TOLERANCE


def _pick(pool: list[Found], source: uuid.UUID | None) -> Found:
    """같은 출처 먼저, 그다음 등급. 끝은 id — 같은 입력에 늘 같은 답."""
    return min(
        pool,
        key=lambda one: (
            source is None or one.value.source_id != source,
            one.tier,
            str(one.value.id),
        ),
    )


def _paired(saturation: list[Found], diffusion: list[Found]) -> uuid.UUID | None:
    """확산계수도 낸 출처 — 등급 좋은 포화 농도의 출처부터. 한 흡습 곡선의 두 값이다."""
    for one in sorted(saturation, key=lambda x: (x.tier, str(x.value.id))):
        if any(d.value.source_id == one.value.source_id for d in diffusion):
            return one.value.source_id
    return None


def describe(environment: tuple[float | None, float | None]) -> str:
    """`85 °C · RH 85 %` — 덱 각주에 쓰는 환경 이름."""
    temperature, humidity = environment
    parts = []
    if temperature is not None:
        parts.append(f"{temperature - 273.15:.4g} °C")
    if humidity is not None:
        parts.append(f"RH {humidity * 100:.4g} %")
    return " · ".join(parts) or "조건 미상"


def _choose_environment(
    saturation: list[Found], diffusion: list[Found], expansion: list[Found]
) -> tuple[float | None, float | None] | None:
    """환경 하나 — 확산계수도 함께 있는 포화 농도의 환경, 없으면 확산계수의 환경(포화 농도는
    버린다), 그것도 없으면 포화 농도의 환경. 덱은 확산계수가 있어야 서서 그 순서다 — 포화
    농도만 맞추고 확산계수가 없는 환경을 고르면 덱이 통째로 안 선다. 같은 급에서는 85/85 ·
    흡습 팽창 계수가 같은 온도에 있는 것 · 등급 순."""
    paired = [
        one
        for one in saturation
        if any(_at(d, (one.temperature, one.humidity)) for d in diffusion)
    ]
    anchors = paired or diffusion or saturation
    if not anchors:
        return None

    def rank(one: Found) -> tuple[bool, bool, int, str]:
        return (
            not (
                _close(one.temperature, PREFERRED[0], TEMPERATURE_TOLERANCE)
                and _close(one.humidity, PREFERRED[1], HUMIDITY_TOLERANCE)
            ),
            not any(
                _close(b.temperature, one.temperature, TEMPERATURE_TOLERANCE)
                for b in expansion
            ),
            one.tier,
            str(one.value.id),
        )

    best = min(anchors, key=rank)
    return best.temperature, best.humidity


def _line(label: str, shown: str, one: Found, source: CatalogSource | None) -> str:
    tier = one.tier
    return (
        f"{label} = {shown} — {literature_material.cite_of(one.value, source) or '출처 미상'} "
        f"[tier {tier}: {QUALITY_TIERS.get(tier, str(tier))}]"
    )


def from_catalog(
    db: Session, material_id: uuid.UUID
) -> tuple[dict[str, Any] | None, list[str]]:
    """문헌 재료의 흡습 값 → 흡습 블록 — `(블록 또는 None, 각주)`."""
    values = db.scalars(
        select(CatalogValue).where(
            CatalogValue.material_id == material_id,
            CatalogValue.property_key.in_(KEYS),
            CatalogValue.value_num.is_not(None),
            CatalogValue.source_missing_at.is_(None),
        )
    ).all()
    found = [_found(value) for value in values]
    diffusion = [
        one
        for one in found
        if one.value.property_key == DIFFUSION_KEY
        and is_water(one.value.conditions, default=one.humidity is not None)
    ]
    other_species = sum(1 for one in found if one.value.property_key == DIFFUSION_KEY) - len(
        diffusion
    )
    saturation = [
        one
        for one in found
        if one.value.property_key == SATURATION_KEY
        and is_water(one.value.conditions, default=True)
    ]
    expansion = [
        one
        for one in found
        if one.value.property_key == EXPANSION_KEY
        and is_water(one.value.conditions, default=True)
    ]
    environment = _choose_environment(saturation, diffusion, expansion)
    if environment is None:
        if expansion:
            return None, [
                "흡습 팽창 계수만 있고 포화 농도 · 확산계수가 없어 흡습 블록을 안 지었습니다."
            ]
        return None, []

    sources: dict[uuid.UUID, CatalogSource | None] = {}

    def source_of(one: Found) -> CatalogSource | None:
        key = one.value.source_id
        if key is None:
            return None
        if key not in sources:
            sources[key] = db.get(CatalogSource, key)
        return sources[key]

    values_out: dict[str, Any] = {}
    said = [
        f"흡습 환경 = {describe(environment)} — 포화 농도 · 확산계수는 이 환경의 값입니다."
    ]
    here = [one for one in saturation if _at(one, environment)]
    near = [one for one in diffusion if _at(one, environment)]
    chosen_saturation = _pick(here, _paired(here, near)) if here else None
    anchor = chosen_saturation.value.source_id if chosen_saturation else None
    if chosen_saturation is not None:
        mass = chosen_saturation.number * WATER_MOLAR_MASS
        values_out["moisture_saturation"] = mass
        said.append(
            _line(
                "포화 수분 농도 Csat",
                f"{mass:.6g} kg/m3 ({chosen_saturation.number:.6g} mol/m3 에 물의 몰질량 "
                f"{WATER_MOLAR_MASS} kg/mol 을 곱함)",
                chosen_saturation,
                source_of(chosen_saturation),
            )
        )
    if near:
        chosen = _pick(near, anchor)
        anchor = anchor or chosen.value.source_id
        values_out["moisture_diffusivity"] = chosen.number
        model = (chosen.value.conditions or {}).get("model")
        said.append(
            _line("수분 확산계수 D", f"{chosen.number:.6g} m2/s", chosen, source_of(chosen))
            + (f" · 모델: {model}" if isinstance(model, str) and len(model) <= 60 else "")
        )
    if saturation and chosen_saturation is None:
        said.append(
            "포화 농도는 확산계수와 같은 환경에서 잰 값이 없어 안 썼습니다 — 다른 환경의 값을 "
            "쓰면 CSAT 이 이 환경과 안 맞습니다."
        )
    if expansion:
        same = [
            one
            for one in expansion
            if _close(one.temperature, environment[0], TEMPERATURE_TOLERANCE)
        ]
        chosen = _pick(same or expansion, anchor)
        values_out["hygroscopic_expansion"] = chosen.number
        line = _line(
            "흡습 팽창 계수 β", f"{chosen.number:.6g} m3/kg", chosen, source_of(chosen)
        )
        if not same:
            line += f" · 다른 온도({describe((chosen.temperature, None))})에서 잰 값"
        said.append(line)
    if not values_out:
        return None, said
    if environment[0] is not None:
        values_out["temperature"] = environment[0]
    if environment[1] is not None:
        values_out["humidity"] = environment[1]

    spare = len(here) + len(near) - (chosen_saturation is not None) - bool(near)
    if spare:
        said.append(f"같은 환경의 다른 포화 농도 · 확산계수 {spare}개는 안 썼습니다.")
    at_here = {id(one) for one in (*here, *near)}
    elsewhere = sorted(
        {
            describe((one.temperature, one.humidity))
            for one in (*saturation, *diffusion)
            if id(one) not in at_here
        }
    )
    if elsewhere:
        said.append(f"다른 환경의 흡습 값은 안 썼습니다: {', '.join(elsewhere)}.")
    if other_species:
        said.append(f"확산 종이 물이 아닌 확산계수 {other_species}개는 안 썼습니다.")
    return {"values": values_out}, said
