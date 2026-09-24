"""물성 데이터 내보내기 — **다른 플랫폼이 그대로 읽을 수 있는 모양으로.**

## 왜 DB 덤프를 안 주나

셋 다 실무에서 문제가 된다.

    곡선이 DB 에 없다      `curves` 표에는 경로·해시·행 수만 있다. 점은 파일스토어의
                           Parquet 다 — 덤프만 주면 「시험이 있었다는 기록」만 간다
    섞이면 안 되는 것이 있다  백업은 계정·토큰 해시·감사 기록·`.env`(JWT 비밀키)까지 받는다
    읽을 수가 없다          `pg_dump` 커스텀 포맷은 복원해야 보인다 — 구조를 묻는
                           사람에게 서버를 하나 세우라는 말이 된다

그래서 **도메인 단위의 평면 CSV + 곡선 파일**로 낸다. 받는 쪽이 엑셀로도, pandas
로도, 자기 DB 적재로도 쓸 수 있다.

## 단위는 전부 SI 이고, 열 이름에 적는다

화면은 mm·MPa·tonne/mm³ 로 보여 주는 자리가 있다(`app/shared/display.py`). 그 값을
그대로 뽑으면 받는 쪽이 1000배 틀린 채로 쓰고, 그 사실은 해석 결과를 보기 전까지
안 드러난다. 그래서 여기서는 **저장된 SI 값**만 내고 이름에 단위를 박는다
(`spec_thickness_m`, `density_kg_m3`).

## 사람은 안 낸다

계정·토큰·감사·접근 로그는 여기 없다. 물성 데이터를 넘기는 데 필요하지 않고,
한 번 나가면 되돌릴 수 없다. 등록자도 이름 대신 부서만 남긴다.

## 내는 것

    materials.csv            재료
    samples.csv              시료(로트)
    specimens.csv            시편
    test_runs.csv            시험 — 조건은 `conditions_json` 한 칸에 SI 로
    test_summaries.csv       요약값(장비가 준 것 · 표로 적은 것)
    processing_results.csv   처리 결과 — 채택 여부까지
    processing_scalars.csv   그 결과가 낸 값들(긴 형식)
    cards.csv                물성 카드
    card_values.csv          카드 값 — `블록.값 = 숫자`(긴 형식)
    declared_properties.csv  사람이 적어 둔 값 — 출처·근거와 함께
    parameter_sets.csv       사내 재료가 인용하는 모델 파라미터 벌 (ADR 0029)
    catalog_*.csv            문헌 카탈로그 — 물성 사전·재료·값·출처·연결
    curves/<시험>__<키>.csv   곡선 점
    curves/index.csv         곡선 파일 ↔ 시험
    README.md                열 뜻·단위·빠진 것
    manifest.json            언제·무엇을·몇 줄·무엇이 빠졌나

## 문헌은 **어디서 왔는지 적어서** 낸다

카탈로그는 대부분 MaterialTwin 에서 이관해 온 것이고 원본은 논문·핸드북이다. 다른
조직으로 넘기는 것은 3자 데이터의 재배포가 될 수 있다 — 막지는 않되 **줄마다
`origin`(materialtwin · local)과 출처의 `license` 를 함께 낸다.** 판단할 근거를 빼고
데이터만 주면 받는 쪽도 판단할 수가 없다.

## 부르는 자리가 둘이다 — **같은 함수를 부른다**

    화면    서버 화면의 「데이터 내보내기」 → 작업 큐 → `app/modules/server/jobs.py`
    명령줄  `scripts/export_dataset.py`

두 벌로 두면 버튼으로 뽑은 것과 스크립트로 뽑은 것이 달라지고, 그 차이는 아무도
설명할 수 없다.
"""

from __future__ import annotations

import csv
import json
import re
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import version
from app.modules.catalog.models import (
    CatalogDefinition,
    CatalogLink,
    CatalogMaterial,
    CatalogSource,
    CatalogValue,
)
from app.modules.catalog.ontology_models import PropertyLink
from app.modules.fitting.models import PropertyCard
from app.modules.materials.models import Material, MaterialParameterSet, Sample, Specimen
from app.modules.processing.models import ProcessingResult
from app.modules.tests.models import Curve, TestRun, TestSummary, TestType
from app.modules.workspaces.models import Workspace
from app.shared import filestore
from matcore import curves as curvekit

#: 파일 이름에 못 쓰는 글자. 시험 이름이 그대로 파일 이름이 된다.
UNSAFE = re.compile(r"[^0-9A-Za-z가-힣._-]+")


def _safe(name: str) -> str:
    return UNSAFE.sub("_", name).strip("_") or "unnamed"


class Sheet:
    """CSV 한 장. **줄 수를 세어 manifest 에 남긴다.**"""

    def __init__(
        self, root: Path, name: str, columns: Sequence[str], *, label: str | None = None
    ) -> None:
        self.name = name
        #: manifest 에 적히는 이름. 하위 폴더의 표는 폴더까지 적는다.
        self.label = label or name
        self.columns = list(columns)
        self.rows = 0
        self._handle = (root / name).open("w", encoding="utf-8-sig", newline="")
        self._writer = csv.writer(self._handle)
        self._writer.writerow(self.columns)

    def write(self, values: Sequence[Any]) -> None:
        self._writer.writerow(["" if one is None else one for one in values])
        self.rows += 1

    def close(self) -> None:
        self._handle.close()


def _iso(value: Any) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else None


def _dump(value: Any) -> str | None:
    """JSON 칸 하나. **비어 있으면 빈 칸으로** — `{}` 와 빈 칸이 섞이면 세기 어렵다."""
    if not value:
        return None
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _workspaces(db: Session, slug: str | None) -> dict[Any, str]:
    rows = db.scalars(select(Workspace)).all()
    if slug:
        rows = [one for one in rows if one.slug == slug]
        if not rows:
            # **SystemExit 를 안 쓴다.** 워커도 이 함수를 부르므로, 프로세스를 끄는
            # 예외를 던지면 작업 하나가 워커를 데리고 내려간다.
            raise ValueError(f"그런 부서가 없습니다: {slug}")
    return {one.id: one.slug for one in rows}


def export(
    out: Path,
    *,
    db: Session,
    workspace: str | None,
    with_curves: bool,
    with_catalog: bool = True,
) -> dict[str, Any]:
    """CSV 묶음을 만든다. **세션은 부르는 쪽이 준다.**

    전에는 여기서 `SessionLocal()` 로 자기 세션을 열었다. 워커가 건넨 세션을 무시하고
    기본 DB 로 갔다는 뜻이다 — 운영에서는 같은 DB 라 표가 안 났지만, 시험은 제 DB 가
    아니라 개발 DB 를 뽑고 있었고 CI(그 DB 가 없는 기계)에서야 드러났다(2026-09-23).
    """
    out.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "app_version": version.current(),
        "scope": {
            "workspace": workspace or "전 부서",
            "curves": with_curves,
            "catalog": with_catalog,
        },
        "counts": {},
        "missing_curve_files": [],
    }

    spaces = _workspaces(db, workspace)
    keep = set(spaces)

    # **부서 없이 올린 재료**(`owner_workspace_id` 가 NULL)는 부서로 거를 때도 함께
    # 낸다 — 그 재료를 쓰는 시험이 나가는데 재료만 빠지면 줄이 끊긴다.
    materials = [
        one
        for one in db.scalars(select(Material).where(Material.deleted_at.is_(None)))
        if one.owner_workspace_id is None or one.owner_workspace_id in keep
    ]
    material_ids = {one.id for one in materials}

    samples = [
        one
        for one in db.scalars(select(Sample).where(Sample.deleted_at.is_(None)))
        if one.material_id in material_ids
    ]
    sample_ids = {one.id for one in samples}

    specimens = [
        one
        for one in db.scalars(select(Specimen).where(Specimen.deleted_at.is_(None)))
        if one.sample_id in sample_ids
    ]
    specimen_ids = {one.id for one in specimens}

    runs = [
        one
        for one in db.scalars(select(TestRun).where(TestRun.deleted_at.is_(None)))
        if one.specimen_id in specimen_ids
    ]
    run_ids = {one.id for one in runs}
    types = {one.id: one.key for one in db.scalars(select(TestType))}

    sheets = _write_core(out, spaces, materials, samples, specimens, runs, types)
    sheets += _write_values(out, db, runs, run_ids, material_ids, sample_ids)
    if with_catalog:
        sheets += _write_catalog(out, db, material_ids, report)
    if with_curves:
        sheets.append(_write_curves(out, db, runs, run_ids, report))

    for sheet in sheets:
        sheet.close()
        report["counts"][sheet.label] = sheet.rows

    _write_readme(out, report)
    (out / "manifest.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report


def _write_core(
    out: Path,
    spaces: dict[Any, str],
    materials: list[Material],
    samples: list[Sample],
    specimens: list[Specimen],
    runs: list[TestRun],
    types: dict[Any, str],
) -> list[Sheet]:
    material_sheet = Sheet(
        out,
        "materials.csv",
        [
            "material_id",
            "code",
            "record_name",
            "workspace",
            "family",
            "category",
            "grade",
            "details",
            "spec_thickness_m",
            "density_kg_m3",
            "poisson_ratio",
            "alias",
            "legacy_id",
            "note",
            "created_at",
        ],
    )
    for material in materials:
        material_sheet.write(
            [
                material.id,
                material.code,
                material.record_name,
                spaces.get(material.owner_workspace_id),
                material.family,
                material.category,
                material.grade,
                material.details,
                material.spec_thickness_m,
                material.density_si,
                material.poisson_ratio,
                material.alias,
                # `is_global` 칸은 걷었다(ADR 0035) — 받는 쪽이 「공식인가」 로 읽었다.
                # 부서가 비었는지는 `workspace` 칸이 그대로 말한다.
                material.legacy_id,
                material.note,
                _iso(material.created_at),
            ]
        )

    sample_sheet = Sheet(
        out,
        "samples.csv",
        [
            "sample_id",
            "material_id",
            "seq_no",
            "record_name",
            "lot_no",
            "manufacturer",
            "distributor",
            "primary_vendor",
            "sales_type",
            "production_date",
            "density_kg_m3",
            "alias",
            "note",
            "created_at",
        ],
    )
    for sample in samples:
        sample_sheet.write(
            [
                sample.id,
                sample.material_id,
                sample.seq_no,
                sample.record_name,
                sample.lot_no,
                sample.manufacturer,
                sample.distributor,
                sample.primary_vendor,
                sample.sales_type,
                _iso(sample.production_date),
                sample.density_si,
                sample.alias,
                sample.note,
                _iso(sample.created_at),
            ]
        )

    specimen_sheet = Sheet(
        out,
        "specimens.csv",
        [
            "specimen_id",
            "sample_id",
            "seq_no",
            "record_name",
            "orientation",
            "standard",
            "thickness_m",
            "width_m",
            "gauge_length_m",
            "dimensions_json_si",
            "note",
            "created_at",
        ],
    )
    for specimen in specimens:
        specimen_sheet.write(
            [
                specimen.id,
                specimen.sample_id,
                specimen.seq_no,
                specimen.record_name,
                specimen.orientation,
                specimen.standard,
                specimen.thickness_m,
                specimen.width_m,
                specimen.gauge_length_m,
                # 규격이 정한 그 밖의 치수(직경·평행부 길이…). 규격마다 칸이 다르다.
                _dump(specimen.dimensions),
                specimen.note,
                _iso(specimen.created_at),
            ]
        )

    run_sheet = Sheet(
        out,
        "test_runs.csv",
        [
            "test_run_id",
            "specimen_id",
            "record_name",
            "test_type",
            "status",
            "tested_at",
            "instrument",
            "division",
            "conditions_json_si",
            "adopted_result_id",
            "created_at",
        ],
    )
    for run in runs:
        run_sheet.write(
            [
                run.id,
                run.specimen_id,
                run.record_name,
                types.get(run.test_type_id),
                run.status,
                _iso(run.tested_at),
                run.instrument,
                run.division,
                _dump(run.conditions),
                run.adopted_result_id,
                _iso(run.created_at),
            ]
        )

    return [material_sheet, sample_sheet, specimen_sheet, run_sheet]


def _write_values(
    out: Path,
    db: Session,
    runs: list[TestRun],
    run_ids: set[Any],
    material_ids: set[Any],
    sample_ids: set[Any],
) -> list[Sheet]:
    summary_sheet = Sheet(
        out,
        "test_summaries.csv",
        ["test_run_id", "key", "label", "source", "value_si", "value_text", "si_unit"],
    )
    for summary in db.scalars(select(TestSummary)):
        if summary.test_run_id not in run_ids:
            continue
        summary_sheet.write(
            [
                summary.test_run_id,
                summary.key,
                summary.label,
                summary.source,
                summary.value_num,
                summary.value_text,
                summary.si_unit,
            ]
        )

    adopted = {one.adopted_result_id for one in runs if one.adopted_result_id}
    result_sheet = Sheet(
        out,
        "processing_results.csv",
        [
            "result_id",
            "test_run_id",
            "source_curve_key",
            "recipe_label",
            "is_adopted",
            "steps_json",
            "created_at",
        ],
    )
    scalar_sheet = Sheet(
        out,
        "processing_scalars.csv",
        ["result_id", "test_run_id", "is_adopted", "key", "label", "value_si", "si_unit"],
    )
    for result in db.scalars(select(ProcessingResult)):
        if result.test_run_id not in run_ids:
            continue
        is_adopted = result.id in adopted
        result_sheet.write(
            [
                result.id,
                result.test_run_id,
                result.source_curve_key,
                result.recipe_label,
                is_adopted,
                _dump(result.steps_snapshot),
                _iso(result.created_at),
            ]
        )
        for scalar in result.scalars or []:
            if not isinstance(scalar, dict):
                continue
            scalar_sheet.write(
                [
                    result.id,
                    result.test_run_id,
                    is_adopted,
                    scalar.get("key"),
                    scalar.get("label"),
                    scalar.get("value"),
                    scalar.get("si_unit"),
                ]
            )

    card_sheet = Sheet(
        out,
        "cards.csv",
        [
            "card_id",
            "material_id",
            "label",
            "status",
            "orientation",
            "test_run_ids_json",
            "sample_count",
            "created_at",
        ],
    )
    card_value_sheet = Sheet(
        out,
        "card_values.csv",
        ["card_id", "material_id", "block", "key", "value_si", "row_index"],
    )
    for card in db.scalars(select(PropertyCard)):
        if card.material_id not in material_ids:
            continue
        source = card.source or {}
        card_sheet.write(
            [
                card.id,
                card.material_id,
                card.label,
                card.status,
                card.orientation,
                _dump(source.get("test_run_ids")),
                source.get("sample_count"),
                _iso(card.created_at),
            ]
        )
        for block, payload in (card.blocks or {}).items():
            if not isinstance(payload, dict):
                continue
            for key, value in (payload.get("values") or {}).items():
                card_value_sheet.write([card.id, card.material_id, block, key, value, None])
            for index, row in enumerate(payload.get("rows") or []):
                if not isinstance(row, dict):
                    continue
                for key, value in row.items():
                    card_value_sheet.write(
                        [card.id, card.material_id, block, key, value, index]
                    )

    declared_sheet = Sheet(
        out,
        "declared_properties.csv",
        [
            "level",
            "owner_id",
            "item",
            "temperature_k",
            "value_si",
            "si_unit",
            "scale",
            "source",
            "reference",
            "note",
        ],
    )
    owners: Iterable[tuple[str, Any, list[Any]]] = [
        ("material", one.id, one.declared_properties or [])
        for one in db.scalars(select(Material).where(Material.deleted_at.is_(None)))
        if one.id in material_ids
    ] + [
        ("sample", one.id, one.declared_properties or [])
        for one in db.scalars(select(Sample).where(Sample.deleted_at.is_(None)))
        if one.id in sample_ids
    ]
    for level, owner_id, rows in owners:
        for row in rows:
            if not isinstance(row, dict):
                continue
            for point in row.get("points") or []:
                declared_sheet.write(
                    [
                        level,
                        owner_id,
                        row.get("item"),
                        point.get("temperature_k"),
                        point.get("value"),
                        row.get("si_unit"),
                        row.get("scale"),
                        row.get("source"),
                        row.get("reference"),
                        row.get("note"),
                    ]
                )

    parameter_sheet = Sheet(
        out,
        "parameter_sets.csv",
        [
            "material_id",
            "model",
            "property_key",
            "label",
            "origin",
            "quality_tier",
            "source_ref",
            "source_detail",
            "terms_json_si",
            "notes",
            "created_at",
        ],
    )
    for pset in db.scalars(select(MaterialParameterSet)):
        if pset.material_id not in material_ids:
            continue
        parameter_sheet.write(
            [
                pset.material_id,
                pset.model,
                pset.property_key,
                pset.label,
                pset.origin,
                pset.quality_tier,
                pset.source_ref,
                _dump(pset.source_detail),
                _dump(pset.terms),
                pset.notes,
                _iso(pset.created_at),
            ]
        )

    return [
        summary_sheet,
        result_sheet,
        scalar_sheet,
        card_sheet,
        card_value_sheet,
        declared_sheet,
        parameter_sheet,
    ]


def _origin(mt_id: Any) -> str:
    """이 줄이 어디서 왔나. **이관해 온 것과 여기서 만든 것을 가른다** — 재배포
    판단이 그 구별 위에 선다(이관은 원본이 정본이고, `local.` 은 우리 것이다)."""
    return "materialtwin" if mt_id else "local"


def _write_catalog(
    out: Path, db: Session, material_ids: set[Any], report: dict[str, Any]
) -> list[Sheet]:
    """문헌 카탈로그. **전부 낸다** — 사내 재료에 이어진 것만 내면 「이 값이 왜
    이 등급인가」 를 되짚을 출처가 함께 안 간다."""
    property_sheet = Sheet(
        out,
        "catalog_properties.csv",
        [
            "property_key",
            "name",
            "symbol",
            "si_unit",
            "domain",
            "value_type",
            "test_standard",
            "condition_axes_json",
            "deprecated_at",
            "superseded_by",
            "origin",
        ],
    )
    for definition in db.scalars(select(CatalogDefinition)):
        property_sheet.write(
            [
                definition.key,
                definition.name,
                definition.symbol,
                definition.si_unit,
                definition.domain,
                definition.value_type,
                definition.test_standard,
                _dump(definition.condition_axes),
                _iso(definition.deprecated_at),
                definition.superseded_by,
                _origin(definition.mt_id),
            ]
        )

    material_sheet = Sheet(
        out,
        "catalog_materials.csv",
        [
            "catalog_material_id",
            "name",
            "material_code",
            "material_class",
            "category",
            "grade",
            "manufacturer",
            "role",
            "subsystem",
            "description",
            "attributes_json",
            "origin",
        ],
    )
    for material in db.scalars(select(CatalogMaterial)):
        material_sheet.write(
            [
                material.id,
                material.name,
                material.material_code,
                material.material_class,
                material.category,
                material.grade,
                material.manufacturer,
                material.role,
                material.subsystem,
                material.description,
                _dump(material.attributes),
                _origin(material.mt_id),
            ]
        )

    value_sheet = Sheet(
        out,
        "catalog_values.csv",
        [
            "value_id",
            "catalog_material_id",
            "property_key",
            "value_num",
            "value_text",
            "unit",
            "uncertainty",
            "conditions_json",
            "method",
            "quality_tier",
            "source_id",
            "source_detail",
            "notes",
            "origin",
        ],
    )
    for value in db.scalars(select(CatalogValue)):
        value_sheet.write(
            [
                value.id,
                value.material_id,
                value.property_key,
                value.value_num,
                value.value_text,
                # **사내 표와 달리 여기 단위는 줄마다 온다.** 물성 정의의 단위와
                # 같지만(적재 관문이 검사한다) 값 옆에 둔다 — 떨어져 있으면
                # 언젠가 어긋난다.
                value.unit,
                value.uncertainty,
                _dump(value.conditions),
                value.method,
                value.quality_tier,
                value.source_id,
                value.source_detail,
                value.notes,
                _origin(value.mt_id),
            ]
        )

    #: 라이선스가 적힌 출처가 몇이나 되나. **승인하는 사람이 볼 수다** — 거의
    #: 전부 빈칸이면 「확인하고 넘기라」 는 말이 실제 무게를 갖는다.
    licenses: dict[str, int] = {}
    source_sheet = Sheet(
        out,
        "catalog_sources.csv",
        [
            "source_id",
            "kind",
            "title",
            "authors",
            "year",
            "publisher",
            "doi",
            "isbn",
            "url",
            "license",
            "origin",
        ],
    )
    for source in db.scalars(select(CatalogSource)):
        licenses[source.license or "(적혀 있지 않음)"] = (
            licenses.get(source.license or "(적혀 있지 않음)", 0) + 1
        )
        source_sheet.write(
            [
                source.id,
                source.kind,
                source.title,
                source.authors,
                source.year,
                source.publisher,
                source.doi,
                source.isbn,
                source.url,
                # **재배포 판단의 근거다.** 비어 있으면 「모른다」 이지 「자유」 가 아니다.
                source.license,
                _origin(source.mt_id),
            ]
        )

    link_sheet = Sheet(
        out,
        "catalog_links.csv",
        ["material_id", "catalog_material_id", "created_at"],
    )
    for link in db.scalars(select(CatalogLink)):
        if link.material_id not in material_ids:
            continue
        link_sheet.write([link.material_id, link.catalog_material_id, _iso(link.created_at)])

    property_link_sheet = Sheet(
        out,
        "catalog_property_links.csv",
        ["property_key", "term_id", "kind", "scale", "note"],
    )
    for mapping in db.scalars(select(PropertyLink)):
        property_link_sheet.write(
            [mapping.property_key, mapping.term_id, mapping.kind, mapping.scale, mapping.note]
        )

    report["catalog_licenses"] = dict(sorted(licenses.items(), key=lambda pair: -pair[1]))
    return [
        property_sheet,
        material_sheet,
        value_sheet,
        source_sheet,
        link_sheet,
        property_link_sheet,
    ]


def _write_curves(
    out: Path, db: Session, runs: list[TestRun], run_ids: set[Any], report: dict[str, Any]
) -> Sheet:
    """곡선 점을 시험마다 CSV 로. **못 읽은 것은 조용히 넘기지 않고 센다.**"""
    folder = out / "curves"
    folder.mkdir(exist_ok=True)
    names = {one.id: one.record_name for one in runs}

    # 이름에 폴더를 담아 둔다 — manifest 의 줄 수 목록에서 어느 표인지 보이게.
    index = Sheet(
        out / "curves",
        "index.csv",
        ["file", "test_run_id", "test_run", "curve_key", "kind", "row_count", "channels_json"],
        label="curves/index.csv",
    )
    taken: set[str] = set()
    for curve in db.scalars(select(Curve)):
        if curve.test_run_id not in run_ids:
            continue
        run_name = names.get(curve.test_run_id, str(curve.test_run_id))
        stem = f"{_safe(run_name)}__{_safe(curve.key)}"
        name = stem
        serial = 2
        while name in taken:
            name = f"{stem}_{serial}"
            serial += 1
        taken.add(name)
        try:
            columns = curvekit.read_columns(filestore.read_bytes(curve.storage_path))
        except Exception as failed:  # 파일이 없거나 깨졌다 — 세어서 manifest 에 남긴다
            report["missing_curve_files"].append(
                {
                    "test_run": names.get(curve.test_run_id),
                    "path": curve.storage_path,
                    "why": f"{type(failed).__name__}: {failed}",
                }
            )
            continue
        keys = list(columns)
        with (folder / f"{name}.csv").open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(keys)
            for values in zip(*(columns[key] for key in keys), strict=False):
                writer.writerow(["" if value is None else value for value in values])
        index.write(
            [
                f"{name}.csv",
                curve.test_run_id,
                names.get(curve.test_run_id),
                curve.key,
                curve.kind,
                curve.row_count,
                _dump(curve.channels),
            ]
        )
    return index


README = """# MatNexus 물성 데이터 내보내기

생성: {generated_at} · 버전 {app_version} · 범위 {scope}

## 읽는 법

표는 **id 로 이어집니다.**

    materials.material_id → samples.material_id → specimens.sample_id
                          → test_runs.specimen_id
    test_runs.test_run_id → test_summaries · processing_results · curves/index.csv
    cards.card_id         → card_values.card_id

## 단위

**숫자는 전부 SI 입니다.** 열 이름에 단위를 적어 뒀습니다(`spec_thickness_m`,
`density_kg_m3`). 화면이 보여 주는 단위(mm·MPa·tonne/mm³)와 다릅니다 — 화면 값을
기대하고 읽으면 1000배 틀립니다.

`value_si` 로 끝나는 칸은 그 값의 정본 단위가 같은 줄의 `si_unit` 에 있습니다.

## 칸이 여럿 든 곳

    test_runs.conditions_json_si     시험 조건. 키는 시험 종류가 정합니다(온도는 K)
    processing_results.steps_json    그때 돌린 처리 단계와 옵션
    card_values                      긴 형식입니다 — 한 줄이 `블록.값 = 숫자` 하나.
                                     `row_index` 가 있으면 그 블록 표의 몇 번째 줄인지

## 곡선

`curves/` 에 시험마다 CSV 한 장입니다. 열 이름이 채널 키이고 값은 SI 입니다.
어느 파일이 어느 시험인지는 `curves/index.csv` 에 있습니다.

원본 저장은 Parquet 이고 여기서 CSV 로 편 것이라, **실수 표현이 조금 달라질 수
있습니다**(마지막 자리). 정밀 대조가 필요하면 Parquet 원본을 따로 요청하세요.

## 문헌 카탈로그 — **재배포 전에 확인하세요**

`catalog_*.csv` 는 논문·핸드북에서 온 값입니다. 줄마다 `origin` 이 붙어 있습니다.

    materialtwin   MaterialTwin 에서 이관해 온 것. **원본이 정본입니다**
    local          MatNexus 에서 직접 넣은 것 (키가 `local.` 로 시작합니다)

출처의 라이선스는 `catalog_sources.license` 에 있습니다. **비어 있으면 「모른다」이지
「자유롭게 써도 된다」가 아닙니다.** 이 데이터를 다시 배포하기 전에 원본 소유자와
확인하세요 — 우리가 넘길 수 있는 것은 우리가 잰 값이고, 문헌 값은 그 출처의 것입니다.

이번 내보내기의 출처 라이선스:

{licenses}

값의 등급(`quality_tier`)은 1(제품 문서 실측) ~ 4(계산·추정)이고, 사내 값과 같은
척도입니다. `method` 가 `digitized` 면 그래프에서 읽은 값이라 자릿수를 믿지 마세요.

## 빠진 것 — 일부러

- **계정·토큰·감사 기록·접근 로그.** 물성 데이터를 넘기는 데 필요하지 않습니다.
- **등록한 사람.** 부서(`materials.workspace`)만 남겼습니다.
- **지운 것.** 소프트 삭제된 재료·시료·시편·시험·카드는 안 나옵니다.
- **기준정보 사전·시험 종류 정의·처리 레시피.** 값이 아니라 «우리가 일하는 방식»
  입니다. 그쪽이 필요하면 따로 말씀하세요 — 다른 표입니다.

## 못 읽은 곡선

{missing}
"""


def _write_readme(out: Path, report: dict[str, Any]) -> None:
    missing = report["missing_curve_files"]
    licenses = report.get("catalog_licenses") or {}
    text = README.format(
        generated_at=report["generated_at"],
        app_version=report["app_version"],
        scope=report["scope"]["workspace"],
        licenses=(
            "    (문헌을 안 냈습니다)"
            if not licenses
            else "\n".join(f"    {name:24s} {count:>6,}건" for name, count in licenses.items())
        ),
        missing=(
            "없습니다."
            if not missing
            else "\n".join(f"- {one['test_run']} — {one['why']}" for one in missing)
        ),
    )
    (out / "README.md").write_text(text, encoding="utf-8")
