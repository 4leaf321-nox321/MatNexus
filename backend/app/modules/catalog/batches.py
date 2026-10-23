"""반입 묶음 — **외부 공개 데이터를 묶음 파일 하나로 들인다**(2026-10-23, ADR 0068).

수집기(MaterialCollector)가 라이선스를 확인한 공개 데이터(문헌 피로 · 고무 곡선 …)를
묶음 파일로 낸다. 값 하나씩 MCP 로 수백 번 넣으면 시간 초과 뒤 다시 부를 때 두 번
들어가고, 중간에 끊기면 반쯤 들어간 채 남고, 무엇을 넣었는지 묶어서 볼 수도 되돌릴 수도
없다. 그래서 서버가 파일을 **한 번에** 받는다:

    미리보기     들였을 때의 결과(만들 것 · 이미 있는 것 · 문제)만 돌려준다
    적용         문제가 하나라도 있으면 아무것도 적지 않는다 — 전부 되거나 전부 안 된다
    다시 들이기  같은 외부 키 · 같은 내용이면 그대로 둔다(멱등), 다르면 문제로 낸다
    지우기       자료 관리자. 사내가 받아 간 값 · 사내와 이은 재료가 있으면 막는다

항목은 값 하나 · 한 벌을 넣을 때와 **같은 검사**를 지난다(`contribute`) — 두 벌이면
어긋난다. 이관(`mt_id`, ADR 0027)과는 독립이다. 이관은 `mt_id` 로만 찾으므로 이 줄들을
모른다.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel
from sqlalchemy import Text, cast, delete, func, select, update
from sqlalchemy.orm import Session

from app.modules.accounts.models import User
from app.modules.catalog import contribute, parameters
from app.modules.catalog.models import (
    CatalogBatch,
    CatalogLink,
    CatalogMaterial,
    CatalogSeries,
    CatalogSource,
    CatalogValue,
)
from app.modules.catalog.schemas import (
    CatalogBatchAttachedOut,
    CatalogBatchBundleIn,
    CatalogBatchCountOut,
    CatalogBatchDeleteOut,
    CatalogBatchImportOut,
    CatalogBatchMaterialIn,
    CatalogBatchOut,
    CatalogBatchProblemOut,
    CatalogMaterialCreate,
    CatalogSeriesCreate,
    CatalogSourceIn,
    CatalogValueCreate,
)
from app.modules.materials.models import Material, Sample
from app.shared import audit, declared_approval, permissions
from app.shared.errors import AppError, Conflict, NotFound

#: 보고서에 실을 문제의 상한 — 넘으면 앞의 것만 싣고 수를 말한다.
MAX_PROBLEMS = 200

#: 값 · 벌이 출처 · 재료를 가리킬 때 쓰는 자리 — 출처는 값 하나를 넣을 때 필수라 자리만 채운다
#: (묶음은 출처를 먼저 정해 넘긴다, `contribute.create_value(source=…)`).
_PLACEHOLDER_SOURCE = CatalogSourceIn(kind="other", title="(반입 묶음)")


def _digest(item: BaseModel) -> str:
    """항목의 내용 지문 — 키를 뺀 입력을 정렬한 JSON 의 sha256. 같은 파일이면 같은 값이다."""
    body = item.model_dump(mode="json", exclude={"key"})
    text = json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _external(batch_key: str, item_key: str) -> str:
    return f"{batch_key}:{item_key}"


@dataclass
class _Run:
    batch: CatalogBatch
    counts: dict[str, CatalogBatchCountOut] = field(
        default_factory=lambda: {
            kind: CatalogBatchCountOut()
            for kind in ("sources", "materials", "values", "series")
        }
    )
    points: int = 0
    attached: list[CatalogBatchAttachedOut] = field(default_factory=list)
    problems: list[CatalogBatchProblemOut] = field(default_factory=list)
    hidden: int = 0
    parameter_sets: bool = False

    def problem(self, kind: str, key: str, code: str, message: str) -> None:
        if len(self.problems) >= MAX_PROBLEMS:
            self.hidden += 1
            return
        self.problems.append(
            CatalogBatchProblemOut(kind=kind, key=key, code=code, message=message)
        )


def _tag(row: Any, batch: CatalogBatch, external: str | None, digest: str | None) -> None:
    row.batch_id = batch.id
    row.external_key = external
    row.external_hash = digest


def _existing(
    db: Session, model: Any, external: str, digest: str, run: _Run, kind: str, key: str
) -> tuple[bool, Any]:
    """같은 외부 키가 있나 — `(있다, 그 줄)`. 내용이 다르면 문제로 낸다."""
    found = db.scalar(select(model).where(model.external_key == external))
    if found is None:
        return False, None
    if found.external_hash != digest:
        run.problem(
            kind,
            key,
            "MNX-CATALOG-0076",
            f"외부 키 '{external}' 는 이미 다른 내용으로 들어와 있습니다 — 고치려면 묶음을 "
            "지우고 "
            "다시 들이세요(조용히 덮어쓰지 않습니다).",
        )
        return True, None
    return True, found


def _batch(db: Session, bundle: CatalogBatchBundleIn, user: User) -> CatalogBatch:
    meta = bundle.batch
    found = db.scalar(select(CatalogBatch).where(CatalogBatch.key == meta.key))
    if found is None:
        found = CatalogBatch(
            key=meta.key,
            title=meta.title.strip(),
            description=(meta.description or "").strip() or None,
            manifest_sha256=meta.manifest_sha256,
            created_by_id=user.id,
        )
        db.add(found)
        db.flush()
        return found
    # 이름 · 설명 · 지문은 묶음의 머리말이라 다시 들일 때 새 파일의 것을 따른다.
    found.title = meta.title.strip()
    found.description = (meta.description or "").strip() or None
    found.manifest_sha256 = meta.manifest_sha256
    found.retired_at = None
    return found


def _duplicate_keys(bundle: CatalogBatchBundleIn, run: _Run) -> None:
    for kind, items in (
        ("source", bundle.sources),
        ("material", bundle.materials),
        ("value", bundle.values),
        ("series", bundle.series),
    ):
        counts = Counter(one.key for one in items)
        for key, count in counts.items():
            if count > 1:
                run.problem(
                    kind,
                    key,
                    "MNX-CATALOG-0077",
                    f"묶음 안에서 키 '{key}' 가 {count}번 나옵니다.",
                )


def import_bundle(
    db: Session, bundle: CatalogBatchBundleIn, user: User, *, dry_run: bool
) -> CatalogBatchImportOut:
    """묶음 파일 하나를 들인다. 미리보기면 결과만 돌려주고 되돌린다."""
    permissions.require_steward(
        user, code="MNX-CATALOG-0075", what="문헌 반입 묶음을 들이는 일"
    )
    run = _Run(batch=_batch(db, bundle, user))
    _duplicate_keys(bundle, run)
    sources = _import_sources(db, bundle, user, run)
    materials = _import_materials(db, bundle, user, run)
    _import_values(db, bundle, user, run, materials, sources)
    _import_series(db, bundle, user, run, materials, sources)

    licenses = Counter(
        (one.license or "(없음)") for one in {row.id: row for row in sources.values()}.values()
    )
    applied = not dry_run and not run.problems and run.hidden == 0
    out = CatalogBatchImportOut(
        batch_key=run.batch.key,
        dry_run=dry_run,
        applied=applied,
        sources=run.counts["sources"],
        materials=run.counts["materials"],
        values=run.counts["values"],
        series=run.counts["series"],
        points=run.points,
        licenses=dict(sorted(licenses.items())),
        attached=run.attached,
        problems=run.problems,
    )
    if not applied:
        db.rollback()
        if not dry_run:
            raise AppError(
                "MNX-CATALOG-0077",
                f"묶음 '{bundle.batch.key}' 에 문제가 {len(run.problems) + run.hidden}건 있어 "
                "아무것도 "
                "들이지 않았습니다 — 미리보기로 문제를 고친 뒤 다시 들이세요.",
                status=422,
                details=out.model_dump(mode="json"),
            )
        return out
    audit.record(
        db,
        action=audit.CATALOG_BATCH_IMPORTED,
        actor=user,
        target_table="catalog_batches",
        target_id=run.batch.id,
        target_label=run.batch.key,
        changes={
            kind: {"created": count.created, "existing": count.existing}
            for kind, count in run.counts.items()
        },
    )
    db.commit()
    if run.parameter_sets:
        # 「이 키가 계수 묶음형인가」 는 프로세스 캐시다 — 새 키가 처음 묶음이 됐을 수 있다.
        parameters.forget()
    return out


def _import_sources(
    db: Session, bundle: CatalogBatchBundleIn, user: User, run: _Run
) -> dict[str, CatalogSource]:
    made: dict[str, CatalogSource] = {}
    for item in bundle.sources:
        external = _external(run.batch.key, item.key)
        digest = _digest(item)
        try:
            with db.begin_nested():
                there, found = _existing(
                    db, CatalogSource, external, digest, run, "source", item.key
                )
                if there:
                    if found is not None:
                        made[item.key] = found
                        run.counts["sources"].existing += 1
                    continue
                given = CatalogSourceIn(**item.model_dump(exclude={"key"}))
                source, created = contribute.find_or_make_source(db, given, user)
                if created:
                    _tag(source, run.batch, external, digest)
                    run.counts["sources"].created += 1
                else:
                    # 이미 있던 출처(같은 DOI · 제목)는 여러 값이 나눠 쓴다 — 묶음의 것이
                    # 아니다.
                    run.counts["sources"].existing += 1
                made[item.key] = source
        except AppError as exc:
            run.problem("source", item.key, exc.code, exc.message)
    return made


def _attach(db: Session, item: CatalogBatchMaterialIn, run: _Run) -> CatalogMaterial | None:
    """이미 있는 문헌 재료를 찾는다 — `existing_mt_id`(서버마다 같다) 또는 `existing_id`."""
    if item.existing_id is not None and item.existing_mt_id is not None:
        run.problem(
            "material",
            item.key,
            "MNX-CATALOG-0077",
            "existing_id 와 existing_mt_id 는 하나만 적습니다.",
        )
        return None
    if item.existing_mt_id is not None:
        found = db.scalar(
            select(CatalogMaterial).where(CatalogMaterial.mt_id == item.existing_mt_id)
        )
        missing = f"existing_mt_id {item.existing_mt_id} 는 카탈로그에 없는 재료입니다."
    else:
        found = db.get(CatalogMaterial, item.existing_id)
        missing = f"existing_id {item.existing_id} 는 카탈로그에 없는 재료입니다."
    if found is None:
        run.problem("material", item.key, "MNX-CATALOG-0001", missing)
        return None
    run.attached.append(
        CatalogBatchAttachedOut(key=item.key, id=found.id, mt_id=found.mt_id, name=found.name)
    )
    return found


def _import_materials(
    db: Session, bundle: CatalogBatchBundleIn, user: User, run: _Run
) -> dict[str, CatalogMaterial]:
    made: dict[str, CatalogMaterial] = {}
    for item in bundle.materials:
        if item.existing_id is not None or item.existing_mt_id is not None:
            existing = _attach(db, item, run)
            if existing is not None:
                made[item.key] = existing
                run.counts["materials"].existing += 1
            continue
        external = _external(run.batch.key, item.key)
        digest = _digest(item)
        try:
            with db.begin_nested():
                there, found = _existing(
                    db, CatalogMaterial, external, digest, run, "material", item.key
                )
                if there:
                    if found is not None:
                        made[item.key] = found
                        run.counts["materials"].existing += 1
                    continue
                payload = CatalogMaterialCreate(
                    **item.model_dump(
                        exclude={"key", "existing_id", "existing_mt_id"}, exclude_none=True
                    )
                )
                material = contribute.create_material(db, payload, user)
                _tag(material, run.batch, external, digest)
                made[item.key] = material
                run.counts["materials"].created += 1
        except AppError as exc:
            run.problem("material", item.key, exc.code, exc.message)
        except ValueError as exc:  # 이름 · 분류가 빠진 새 재료(pydantic)
            run.problem("material", item.key, "MNX-CATALOG-0041", str(exc).splitlines()[0])
    return made


def _refs(
    run: _Run,
    kind: str,
    key: str,
    material_key: str,
    source_key: str,
    materials: dict[str, CatalogMaterial],
    sources: dict[str, CatalogSource],
) -> tuple[CatalogMaterial, CatalogSource] | None:
    material = materials.get(material_key)
    source = sources.get(source_key)
    if material is None:
        run.problem(
            kind,
            key,
            "MNX-CATALOG-0077",
            f"재료 키 '{material_key}' 가 묶음에 없거나 실패했습니다.",
        )
    if source is None:
        run.problem(
            kind,
            key,
            "MNX-CATALOG-0077",
            f"출처 키 '{source_key}' 가 묶음에 없거나 실패했습니다.",
        )
    if material is None or source is None:
        return None
    return material, source


def _import_values(
    db: Session,
    bundle: CatalogBatchBundleIn,
    user: User,
    run: _Run,
    materials: dict[str, CatalogMaterial],
    sources: dict[str, CatalogSource],
) -> None:
    for item in bundle.values:
        refs = _refs(run, "value", item.key, item.material, item.source, materials, sources)
        if refs is None:
            continue
        material, source = refs
        external = _external(run.batch.key, item.key)
        digest = _digest(item)
        try:
            with db.begin_nested():
                there, found = _existing(
                    db, CatalogValue, external, digest, run, "value", item.key
                )
                if there:
                    if found is not None:
                        run.counts["values"].existing += 1
                    continue
                payload = CatalogValueCreate(
                    **item.model_dump(exclude={"key", "material", "source"}),
                    source=_PLACEHOLDER_SOURCE,
                )
                row, _ = contribute.create_value(db, material.id, payload, user, source=source)
                _tag(row, run.batch, external, digest)
                run.counts["values"].created += 1
        except AppError as exc:
            run.problem("value", item.key, exc.code, exc.message)


def _import_series(
    db: Session,
    bundle: CatalogBatchBundleIn,
    user: User,
    run: _Run,
    materials: dict[str, CatalogMaterial],
    sources: dict[str, CatalogSource],
) -> None:
    for item in bundle.series:
        refs = _refs(run, "series", item.key, item.material, item.source, materials, sources)
        if refs is None:
            continue
        material, source = refs
        external = _external(run.batch.key, item.key)
        digest = _digest(item)
        try:
            with db.begin_nested():
                there, found = _existing(
                    db, CatalogSeries, external, digest, run, "series", item.key
                )
                if there:
                    if found is not None:
                        run.counts["series"].existing += 1
                    continue
                payload = CatalogSeriesCreate(
                    **item.model_dump(exclude={"key", "material", "source"}),
                    source=_PLACEHOLDER_SOURCE,
                )
                made = contribute.create_series(db, material.id, payload, user, source=source)
                _tag(made.series, run.batch, external, digest)
                for point in made.points:
                    point.batch_id = run.batch.id
                db.flush()
                run.counts["series"].created += 1
                run.points += len(made.points)
                run.parameter_sets = run.parameter_sets or item.kind == "parameter_set"
        except AppError as exc:
            run.problem("series", item.key, exc.code, exc.message)


# --- 보기 · 지우기 ------------------------------------------------------------------


def batch_or_404(db: Session, key: str) -> CatalogBatch:
    found = db.scalar(select(CatalogBatch).where(CatalogBatch.key == key))
    if found is None:
        raise NotFound("MNX-CATALOG-0078", f"반입 묶음 '{key}' 이 없습니다.")
    return found


def _count(db: Session, model: Any, batch: CatalogBatch) -> int:
    return int(
        db.scalar(select(func.count()).select_from(model).where(model.batch_id == batch.id))
        or 0
    )


def _batch_value_ids(db: Session, batch: CatalogBatch) -> set[str]:
    return {
        str(one)
        for one in db.scalars(select(CatalogValue.id).where(CatalogValue.batch_id == batch.id))
    }


def adopted_by(db: Session, value_ids: set[str]) -> list[str]:
    """이 값들을 선언 물성으로 받아 간 사내 재료 · 시료 이름(ADR 0055 의 근거 `value_ids`)."""
    if not value_ids:
        return []
    holders: list[str] = []
    for model in (Material, Sample):
        rows = db.execute(
            select(model.record_name, model.declared_properties).where(
                cast(model.declared_properties, Text).contains('"value_ids"')
            )
        ).all()
        for name, declared in rows:
            for entry in declared or []:
                evidence = (entry or {}).get(declared_approval.CATALOG_KEY) or {}
                if value_ids & {str(one) for one in evidence.get("value_ids") or []}:
                    holders.append(str(name))
                    break
    return holders


def summary(db: Session, batch: CatalogBatch) -> CatalogBatchOut:
    values = _batch_value_ids(db, batch)
    source_ids = set(
        db.scalars(
            select(CatalogValue.source_id)
            .where(CatalogValue.batch_id == batch.id, CatalogValue.source_id.is_not(None))
            .distinct()
        )
    )
    licenses = Counter(
        (one or "(없음)")
        for one in db.scalars(
            select(CatalogSource.license).where(CatalogSource.id.in_(source_ids))
        )
    )
    creator = db.get(User, batch.created_by_id) if batch.created_by_id else None
    return CatalogBatchOut(
        key=batch.key,
        title=batch.title,
        description=batch.description,
        manifest_sha256=batch.manifest_sha256,
        created_by=creator.display_name if creator else None,
        created_at=batch.created_at,
        retired_at=batch.retired_at,
        materials=_count(db, CatalogMaterial, batch),
        sources=_count(db, CatalogSource, batch),
        values=len(values),
        series=_count(db, CatalogSeries, batch),
        adopted=len(adopted_by(db, values)),
        licenses=dict(sorted(licenses.items())),
    )


def delete_batch(db: Session, key: str, user: User, *, dry_run: bool) -> CatalogBatchDeleteOut:
    """묶음째 지운다 — 벌 → 값 → 남은 값이 없는 출처 · 재료. 묶음 줄은 남기고 `retired_at`.

    **사내가 쓰고 있으면 막는다**: 받아 간 값(선언 물성의 근거)이 있거나, 묶음의 재료가
    사내 재료와 이어져 있으면 — 지우면 그 근거와 BOM 덱의 문헌 값이 조용히 사라진다.
    """
    permissions.require_steward(
        user, code="MNX-CATALOG-0075", what="문헌 반입 묶음을 지우는 일"
    )
    batch = batch_or_404(db, key)
    values = _batch_value_ids(db, batch)
    holders = adopted_by(db, values)
    if holders:
        raise Conflict(
            "MNX-CATALOG-0079",
            f"사내 재료 · 시료 {len(holders)}곳이 이 묶음의 값을 받아 갔습니다 — 그 선언 "
            "물성을 먼저 "
            f"고치세요: {', '.join(holders[:10])}",
            details={"holders": holders[:50]},
        )
    material_ids = set(
        db.scalars(select(CatalogMaterial.id).where(CatalogMaterial.batch_id == batch.id))
    )
    linked = list(
        db.scalars(
            select(Material.record_name)
            .join(CatalogLink, CatalogLink.material_id == Material.id)
            .where(CatalogLink.catalog_material_id.in_(material_ids))
            .limit(50)
        )
    )
    if linked:
        raise Conflict(
            "MNX-CATALOG-0079",
            f"사내 재료 {len(linked)}곳이 이 묶음의 문헌 재료와 이어져 있습니다 — 연결을 먼저 "
            "끊으세요: "
            f"{', '.join(linked[:10])}",
            details={"linked": linked},
        )
    series_count = _count(db, CatalogSeries, batch)
    db.execute(delete(CatalogValue).where(CatalogValue.batch_id == batch.id))
    db.execute(delete(CatalogSeries).where(CatalogSeries.batch_id == batch.id))
    db.flush()
    sources = 0
    for source in db.scalars(select(CatalogSource).where(CatalogSource.batch_id == batch.id)):
        used = db.scalar(
            select(func.count())
            .select_from(CatalogValue)
            .where(CatalogValue.source_id == source.id)
        )
        if not used:
            db.delete(source)
            sources += 1
    materials = 0
    for material in db.scalars(
        select(CatalogMaterial).where(CatalogMaterial.batch_id == batch.id)
    ):
        used = db.scalar(
            select(func.count())
            .select_from(CatalogValue)
            .where(CatalogValue.material_id == material.id)
        )
        if not used:
            db.delete(material)
            materials += 1
        else:
            # 묶음 밖의 값이 붙은 재료는 남긴다 — 묶음 표지만 걷는다.
            material.batch_id = None
            material.external_key = None
            material.external_hash = None
    db.execute(
        update(CatalogSource)
        .where(CatalogSource.batch_id == batch.id)
        .values(batch_id=None, external_key=None, external_hash=None)
    )
    out = CatalogBatchDeleteOut(
        batch_key=batch.key,
        dry_run=dry_run,
        series=series_count,
        values=len(values),
        sources=sources,
        materials=materials,
    )
    if dry_run:
        db.rollback()
        return out
    batch.retired_at = datetime.now(UTC)
    audit.record(
        db,
        action=audit.CATALOG_BATCH_DELETED,
        actor=user,
        target_table="catalog_batches",
        target_id=batch.id,
        target_label=batch.key,
        changes=out.model_dump(exclude={"batch_key", "dry_run"}),
    )
    db.commit()
    parameters.forget()
    return out


def list_batches(db: Session) -> list[CatalogBatchOut]:
    rows = db.scalars(select(CatalogBatch).order_by(CatalogBatch.created_at.desc()).limit(200))
    return [summary(db, one) for one in rows]
