"""측정법 읽기 — **쓰는 길은 API 에 없다** (카탈로그와 같은 규율).

데이터는 이관 스크립트(`scripts/import_materialtwin.py`)로만 들어온다. 화면의
질문은 둘이다: 「이 물성은 무엇으로 재는가」(by-property) 와 「우리는 무엇을
잴 수 있고 무엇이 빈 칸인가」(coverage).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.accounts.models import User
from app.modules.catalog.models import CatalogDefinition, CatalogValue
from app.modules.metrology.models import Instrument, InstrumentCapability
from app.modules.metrology.schemas import (
    MetrologyCapabilityOut,
    MetrologyCoverageOut,
    MetrologyCoverageRowOut,
    MetrologyInstrumentOut,
    MetrologyPropertyOut,
    MetrologySummaryOut,
    MetrologyTechniqueGroupOut,
)
from app.shared.auth import current_user
from app.shared.errors import NotFound

router = APIRouter(prefix="/metrology", tags=["metrology"])


@router.get("/summary", response_model=MetrologySummaryOut)
def summary(
    _user: User = Depends(current_user), db: Session = Depends(get_db)
) -> MetrologySummaryOut:
    """규모 한눈 — 장비 수와 보유 수를 **반드시 갈라** 센다."""
    categories = {
        category: count
        for category, count in db.execute(
            select(Instrument.category, func.count()).group_by(Instrument.category)
        )
    }
    return MetrologySummaryOut(
        instruments=db.scalar(select(func.count()).select_from(Instrument)) or 0,
        instruments_owned=db.scalar(
            select(func.count()).select_from(Instrument).where(Instrument.owned)
        )
        or 0,
        capabilities=db.scalar(select(func.count()).select_from(InstrumentCapability)) or 0,
        properties_covered=db.scalar(
            select(func.count(func.distinct(InstrumentCapability.property_key)))
        )
        or 0,
        properties_total=db.scalar(select(func.count()).select_from(CatalogDefinition)) or 0,
        categories=categories,
    )


@router.get("/coverage", response_model=MetrologyCoverageOut)
def coverage(
    _user: User = Depends(current_user), db: Session = Depends(get_db)
) -> MetrologyCoverageOut:
    """카탈로그 정의 전수 대비 측정 능력 — 빈 칸(gaps)도 그대로 보인다."""
    counts: dict[str, tuple[int, int, int]] = {
        key: (techniques, instruments, owned)
        for key, techniques, instruments, owned in db.execute(
            select(
                InstrumentCapability.property_key,
                func.count(func.distinct(InstrumentCapability.technique)),
                func.count(func.distinct(InstrumentCapability.instrument_id)),
                func.count(func.distinct(InstrumentCapability.instrument_id)).filter(
                    Instrument.owned
                ),
            )
            .join(Instrument, Instrument.id == InstrumentCapability.instrument_id)
            .group_by(InstrumentCapability.property_key)
        )
    }
    value_counts: dict[str, int] = {
        key: count
        for key, count in db.execute(
            select(CatalogValue.property_key, func.count()).group_by(CatalogValue.property_key)
        )
    }

    covered: list[MetrologyCoverageRowOut] = []
    gaps: list[MetrologyCoverageRowOut] = []
    definitions = db.scalars(
        select(CatalogDefinition).order_by(CatalogDefinition.domain, CatalogDefinition.name)
    )
    for definition in definitions:
        techniques, instruments, owned = counts.get(definition.key, (0, 0, 0))
        row = MetrologyCoverageRowOut(
            property_key=definition.key,
            name=definition.name,
            domain=definition.domain,
            symbol=definition.symbol,
            si_unit=definition.si_unit,
            technique_count=techniques,
            instrument_count=instruments,
            owned_instrument_count=owned,
            value_count=value_counts.get(definition.key, 0),
        )
        (covered if instruments else gaps).append(row)
    return MetrologyCoverageOut(covered=covered, gaps=gaps)


@router.get("/by-property/{key}", response_model=MetrologyPropertyOut)
def by_property(
    key: str, _user: User = Depends(current_user), db: Session = Depends(get_db)
) -> MetrologyPropertyOut:
    """물성 하나의 측정 지도 — 기법별로 묶고, 보유 장비를 앞세운다."""
    definition = db.scalar(select(CatalogDefinition).where(CatalogDefinition.key == key))
    if definition is None:
        raise NotFound("MNX-METROLOGY-0001", f"모르는 물성입니다: {key}")

    rows = db.execute(
        select(InstrumentCapability, Instrument)
        .join(Instrument, Instrument.id == InstrumentCapability.instrument_id)
        .where(InstrumentCapability.property_key == key)
        .order_by(
            Instrument.owned.desc(),
            Instrument.vendor,
            Instrument.model,
            InstrumentCapability.mt_id,
        )
    ).all()

    groups: dict[str | None, list[MetrologyCapabilityOut]] = {}
    for capability, instrument in rows:
        groups.setdefault(capability.technique, []).append(
            MetrologyCapabilityOut(
                id=capability.id,
                instrument=MetrologyInstrumentOut(
                    id=instrument.id,
                    vendor=instrument.vendor,
                    model=instrument.model,
                    category=instrument.category,
                    owned=instrument.owned,
                    owned_note=instrument.owned_note,
                    owner_name=instrument.owner_name,
                ),
                standard=capability.standard,
                range_min=capability.range_min,
                range_max=capability.range_max,
                range_unit=capability.range_unit,
                resolution=capability.resolution,
                accuracy=capability.accuracy,
                temperature_min_k=capability.temperature_min_k,
                temperature_max_k=capability.temperature_max_k,
                specimen=capability.specimen,
                mapping_confidence=capability.mapping_confidence,
                source_detail=capability.source_detail,
                notes=capability.notes,
            )
        )
    # 기법 이름순, 기법 미정(None) 그룹은 맨 뒤.
    ordered = sorted(groups.items(), key=lambda item: (item[0] is None, item[0] or ""))
    return MetrologyPropertyOut(
        property_key=definition.key,
        name=definition.name,
        domain=definition.domain,
        symbol=definition.symbol,
        si_unit=definition.si_unit,
        test_standard=definition.test_standard,
        techniques=[
            MetrologyTechniqueGroupOut(technique=technique, capabilities=capabilities)
            for technique, capabilities in ordered
        ],
    )
