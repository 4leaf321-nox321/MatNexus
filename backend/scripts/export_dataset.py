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
    curves/<시험>__<키>.csv   곡선 점
    curves/index.csv         곡선 파일 ↔ 시험
    README.md                열 뜻·단위·빠진 것
    manifest.json            언제·무엇을·몇 줄·무엇이 빠졌나

사용:
    python scripts/export_dataset.py --out D:\\export
    python scripts/export_dataset.py --out D:\\export --no-curves
    python scripts/export_dataset.py --out D:\\export --workspace metal
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

# **모델을 전부 등록시킨다.** 손대는 모델만 import 하면 그 외래키가 가리키는 표가
# 메타데이터에 없어 매핑이 안 풀린다 — 앱에서는 안 드러나고 스크립트에서만 터진다.
from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

import app.all_models  # noqa: E402,F401
from _console import survive_cp949  # noqa: E402
from app import version  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.modules.fitting.models import PropertyCard  # noqa: E402
from app.modules.materials.models import Material, Sample, Specimen  # noqa: E402
from app.modules.processing.models import ProcessingResult  # noqa: E402
from app.modules.tests.models import Curve, TestRun, TestSummary, TestType  # noqa: E402
from app.modules.workspaces.models import Workspace  # noqa: E402
from app.shared import filestore  # noqa: E402
from matcore import curves as curvekit  # noqa: E402

survive_cp949()

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
            raise SystemExit(f"그런 부서가 없습니다: {slug}")
    return {one.id: one.slug for one in rows}


def export(out: Path, *, workspace: str | None, with_curves: bool) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "app_version": version.current(),
        "scope": {"workspace": workspace or "전 부서", "curves": with_curves},
        "counts": {},
        "missing_curve_files": [],
    }

    with SessionLocal() as db:
        spaces = _workspaces(db, workspace)
        keep = set(spaces)

        # **전역 재료는 부서가 없다**(`owner_workspace_id` 가 NULL). 부서로 거를 때도
        # 함께 낸다 — 그 재료를 쓰는 시험이 나가는데 재료만 빠지면 줄이 끊긴다.
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
            "is_global",
            "legacy_id",
            "note",
            "created_at",
        ],
    )
    for one in materials:
        material_sheet.write(
            [
                one.id,
                one.code,
                one.record_name,
                spaces.get(one.owner_workspace_id),
                one.family,
                one.category,
                one.grade,
                one.details,
                one.spec_thickness_m,
                one.density_si,
                one.poisson_ratio,
                one.alias,
                # 전역 재료는 소유 부서가 없다 — 그것이 곧 「전역」 이다.
                one.owner_workspace_id is None,
                one.legacy_id,
                one.note,
                _iso(one.created_at),
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
    for one in samples:
        sample_sheet.write(
            [
                one.id,
                one.material_id,
                one.seq_no,
                one.record_name,
                one.lot_no,
                one.manufacturer,
                one.distributor,
                one.primary_vendor,
                one.sales_type,
                _iso(one.production_date),
                one.density_si,
                one.alias,
                one.note,
                _iso(one.created_at),
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
    for one in specimens:
        specimen_sheet.write(
            [
                one.id,
                one.sample_id,
                one.seq_no,
                one.record_name,
                one.orientation,
                one.standard,
                one.thickness_m,
                one.width_m,
                one.gauge_length_m,
                # 규격이 정한 그 밖의 치수(직경·평행부 길이…). 규격마다 칸이 다르다.
                _dump(one.dimensions),
                one.note,
                _iso(one.created_at),
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
    for one in runs:
        run_sheet.write(
            [
                one.id,
                one.specimen_id,
                one.record_name,
                types.get(one.test_type_id),
                one.status,
                _iso(one.tested_at),
                one.instrument,
                one.division,
                _dump(one.conditions),
                one.adopted_result_id,
                _iso(one.created_at),
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
    for one in db.scalars(select(TestSummary)):
        if one.test_run_id not in run_ids:
            continue
        summary_sheet.write(
            [
                one.test_run_id,
                one.key,
                one.label,
                one.source,
                one.value_num,
                one.value_text,
                one.si_unit,
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
    for one in db.scalars(select(ProcessingResult)):
        if one.test_run_id not in run_ids:
            continue
        is_adopted = one.id in adopted
        result_sheet.write(
            [
                one.id,
                one.test_run_id,
                one.source_curve_key,
                one.recipe_label,
                is_adopted,
                _dump(one.steps_snapshot),
                _iso(one.created_at),
            ]
        )
        for scalar in one.scalars or []:
            if not isinstance(scalar, dict):
                continue
            scalar_sheet.write(
                [
                    one.id,
                    one.test_run_id,
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
    for one in db.scalars(select(PropertyCard)):
        if one.material_id not in material_ids:
            continue
        source = one.source or {}
        card_sheet.write(
            [
                one.id,
                one.material_id,
                one.label,
                one.status,
                one.orientation,
                _dump(source.get("test_run_ids")),
                source.get("sample_count"),
                _iso(one.created_at),
            ]
        )
        for block, payload in (one.blocks or {}).items():
            if not isinstance(payload, dict):
                continue
            for key, value in (payload.get("values") or {}).items():
                card_value_sheet.write([one.id, one.material_id, block, key, value, None])
            for index, row in enumerate(payload.get("rows") or []):
                if not isinstance(row, dict):
                    continue
                for key, value in row.items():
                    card_value_sheet.write([one.id, one.material_id, block, key, value, index])

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

    return [
        summary_sheet,
        result_sheet,
        scalar_sheet,
        card_sheet,
        card_value_sheet,
        declared_sheet,
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
    for one in db.scalars(select(Curve)):
        if one.test_run_id not in run_ids:
            continue
        stem = f"{_safe(names.get(one.test_run_id, str(one.test_run_id)))}__{_safe(one.key)}"
        name = stem
        serial = 2
        while name in taken:
            name = f"{stem}_{serial}"
            serial += 1
        taken.add(name)
        try:
            columns = curvekit.read_columns(filestore.read_bytes(one.storage_path))
        except Exception as failed:  # 파일이 없거나 깨졌다 — 세어서 manifest 에 남긴다
            report["missing_curve_files"].append(
                {
                    "test_run": names.get(one.test_run_id),
                    "path": one.storage_path,
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
                one.test_run_id,
                names.get(one.test_run_id),
                one.key,
                one.kind,
                one.row_count,
                _dump(one.channels),
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

## 빠진 것 — 일부러

- **계정·토큰·감사 기록·접근 로그.** 물성 데이터를 넘기는 데 필요하지 않습니다.
- **등록한 사람.** 부서(`materials.workspace`)만 남겼습니다.
- **지운 것.** 소프트 삭제된 재료·시료·시편·시험·카드는 안 나옵니다.
- **문헌 카탈로그·기준정보 사전·시험 종류 정의.** 이 내보내기는 «잰 값»이 대상입니다.
  그쪽이 필요하면 따로 말씀하세요 — 다른 표입니다.

## 못 읽은 곡선

{missing}
"""


def _write_readme(out: Path, report: dict[str, Any]) -> None:
    missing = report["missing_curve_files"]
    text = README.format(
        generated_at=report["generated_at"],
        app_version=report["app_version"],
        scope=report["scope"]["workspace"],
        missing=(
            "없습니다."
            if not missing
            else "\n".join(f"- {one['test_run']} — {one['why']}" for one in missing)
        ),
    )
    (out / "README.md").write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, help="내보낼 폴더")
    parser.add_argument("--workspace", default=None, help="부서 slug 하나만. 없으면 전 부서")
    parser.add_argument("--no-curves", action="store_true", help="곡선 파일을 빼고 표만 낸다")
    args = parser.parse_args()

    report = export(Path(args.out), workspace=args.workspace, with_curves=not args.no_curves)
    print(f"내보냄: {args.out}")
    for name, rows in report["counts"].items():
        print(f"  {name:28s} {rows:>8,}줄")
    if report["missing_curve_files"]:
        print(f"  ** 못 읽은 곡선 {len(report['missing_curve_files'])}건 — README 참고")


if __name__ == "__main__":
    main()
