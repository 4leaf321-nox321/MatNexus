"""2026-10-04 에 고친 결함이 **이미 남긴 흔적**을 센다 — 읽기만 한다.

고친 것은 앞으로를 막을 뿐 지난 데이터를 되돌리지 않는다. 배포 뒤 운영 서버에서 한 번 돌려,
사람이 손볼 것이 있는지 본다. DB 는 읽기 전용 트랜잭션으로 열고 아무것도 쓰지 않는다.

    ① 가져온 마스터커브   각주파수(rad/s)만 있는 표에서 가져온 것 — 주파수가 2π 배 크다
    ② 문헌 값의 불확도     직접 넣은 값의 불확도가 단위 환산 없이 담겼을 수 있다
    ③ 덮어쓴 원본         같은 파일 이름으로 원본을 바꾸면 옛 원본이 새 파일로 덮였다
    ④ 선언 물성           빈 칸이 0 으로 저장된 점 · 다른 재료의 줄이 통째로 든 재료
    ⑤ 구간 자르기 · 재샘플  단위 있는 열로 적은 시작 · 끝(계산은 그대로, 표시만 바뀌었다)

못 세는 것: 일반 사용자가 붙여넣기로 남의 값에 단 별칭 — 별칭은 누가 달았는지 안 남는다.

사용:
    cd C:\\Server\\MatNexus\\backend
    .\\.venv\\Scripts\\python.exe scripts\\check_fixes_20261004.py
    .\\.venv\\Scripts\\python.exe scripts\\check_fixes_20261004.py --limit 200  # 길게
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

import numpy as np  # noqa: E402
from sqlalchemy import cast, select, text  # noqa: E402
from sqlalchemy.dialects.postgresql import JSONB  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

# **모델을 전부 등록시킨다.** 스크립트가 손대는 모델만 import 하면 외래키가 가리키는 테이블이
# 메타데이터에 없어 매핑을 못 푼다 — 앱에서는 안 드러나고 배포용 스크립트에서만 터진다.
import app.all_models  # noqa: E402,F401
from _console import survive_cp949  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.modules.catalog.models import CatalogMaterial, CatalogValue  # noqa: E402
from app.modules.materials.models import Material, Sample  # noqa: E402
from app.modules.processing.models import ProcessingRecipe, ProcessingResult  # noqa: E402
from app.modules.tests.models import TestChannel, TestRun  # noqa: E402
from app.modules.viscoelastic import services as visco  # noqa: E402
from app.modules.viscoelastic.models import MasterCurve, PronyFit  # noqa: E402
from app.shared import curvedata, filestore  # noqa: E402
from matcore import extensions, processing, registry, units  # noqa: E402

survive_cp949()

TWO_PI = 6.283185307179586

#: 시작 · 끝을 「기준 열」 의 단위로 받는 단계(`unit_from="x"`).
RANGE_STEPS = ("curve.crop", "curve.resample")

#: 불확도 / |값| 이 이보다 작으면 단위 환산이 빠진 것으로 의심한다 — 9.4 GPa ± 0.2 가
#: `9.4e9 ± 0.2` 로 담기면 2e-11 이다. 실제 측정 불확도가 값의 0.01% 아래인 일은 드물다.
SUSPECT_RATIO = 1e-4

#: 화면이 보여 주는 단위(`frontend/src/shared/units.ts` 의 기본) — 저장값을 사람 말로
#: 옮길 때만 쓴다.
SHOWN = {"K": "°C", "m": "mm", "Pa": "MPa", "N": "kN"}


class Report:
    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.findings = 0

    def section(
        self, title: str, rows: list[str], *, advice: str, count: int | None = None
    ) -> None:
        total = len(rows) if count is None else count
        self.findings += total
        mark = "확인할 것 있음" if total else "없음"
        print(f"\n■ {title} — {total}건 ({mark})")
        for line in rows[: self.limit]:
            print(f"   {line}")
        if len(rows) > self.limit:
            print(f"   … 그 밖 {len(rows) - self.limit}건 (--limit 로 더 볼 수 있다)")
        if total:
            print(f"   → {advice}")


def _shown(value: float, unit: str) -> str:
    target = SHOWN.get(unit)
    if target is None:
        return f"{value:g} {unit}"
    return f"{value:g} {unit} (= {units.from_si(value, target):g} {target})"


# ① ------------------------------------------------------------------------------------
def angular_master_curves(db: Session) -> list[str]:
    rows: list[str] = []
    for curve in db.scalars(select(MasterCurve).where(MasterCurve.method == "imported")):
        run = db.get(TestRun, curve.test_run_id)
        key = curve.source_curve_keys[0] if curve.source_curve_keys else None
        if run is None or key is None:
            continue
        try:
            frame, _ = curvedata.load_frame(db, run, key)
        except Exception as exc:  # 하나를 못 읽어도 나머지는 센다
            rows.append(f"{run.code} 곡선 '{key}' — 원본 곡선을 못 읽었다({exc}). 손으로 확인")
            continue
        if visco._first_column(frame, visco.IMPORT_FREQUENCY) is not None:
            continue
        angular = visco._first_column(frame, visco.IMPORT_ANGULAR)
        if angular is None or not np.isfinite(angular).any():
            continue
        low, high = curve.minimum_frequency_hz, curve.maximum_frequency_hz
        # **각주파수 값이 그대로 담긴 것만** — 고친 뒤에 가져온 것은 2π 로 나눠 담겨 있다.
        if not np.isclose(low, float(np.nanmin(angular)), rtol=1e-6, atol=0.0):
            continue
        fits = len(
            list(db.scalars(select(PronyFit.id).where(PronyFit.master_curve_id == curve.id)))
        )
        rows.append(
            f"시험 {run.code} · 마스터커브 {curve.id} (대표={curve.is_primary}) · "
            f"저장된 주파수 {low:.4g}~{high:.4g} Hz(실제는 {low / TWO_PI:.4g}~"
            f"{high / TWO_PI:.4g} Hz) · 그 위의 Prony {fits}개"
        )
    return rows


# ② ------------------------------------------------------------------------------------
def catalog_uncertainty(db: Session) -> list[str]:
    rows: list[str] = []
    found = db.execute(
        select(CatalogValue, CatalogMaterial.name)
        .join(CatalogMaterial, CatalogMaterial.id == CatalogValue.material_id)
        .where(CatalogValue.mt_id.is_(None), CatalogValue.uncertainty.is_not(None))
    ).all()
    for value, name in found:
        number = value.value_num
        if number is None or number == 0 or value.uncertainty is None:
            continue
        ratio = abs(value.uncertainty / number)
        if ratio >= SUSPECT_RATIO:
            continue
        rows.append(
            f"{name} · {value.property_key} = {number:g} {value.unit or ''} "
            f"± {value.uncertainty:g} (값의 {ratio:.1e} 배) · 값 id {value.id}"
        )
    return rows


# ③ ------------------------------------------------------------------------------------
def overwritten_sources(db: Session) -> list[str]:
    rows: list[str] = []
    runs = db.scalars(
        select(TestRun).where(text("jsonb_array_length(test_runs.source_history) > 0"))
    )
    for run in runs:
        for at, old in enumerate(run.source_history or []):
            path, recorded = old.get("path"), old.get("sha256")
            if not path or not recorded:
                continue
            try:
                actual = hashlib.sha256(filestore.read_bytes(str(path))).hexdigest()
            except OSError:
                rows.append(
                    f"시험 {run.code} · {at + 1}번째 옛 원본 {old.get('filename')} — "
                    "파일이 없다"
                )
                continue
            if actual != recorded:
                rows.append(
                    f"시험 {run.code} · {at + 1}번째 옛 원본 {old.get('filename')} — "
                    "뒤에 올린 파일로 덮였다(지금 내용의 해시가 이력과 다르다)"
                )
    return rows


# ④ ------------------------------------------------------------------------------------
def _zero_points(owner: str, declared: Iterable[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for row in declared or []:
        points = [one for one in row.get("points") or [] if isinstance(one, dict)]
        zeros = [one for one in points if one.get("value_si") == 0]
        if zeros:
            out.append(f"{owner} · 「{row.get('item')}」 점 {len(zeros)}/{len(points)}개가 0")
    return out


def declared_zeros(db: Session) -> list[str]:
    rows: list[str] = []
    for material in db.scalars(select(Material).where(Material.deleted_at.is_(None))):
        rows += _zero_points(
            f"재료 {material.code} {material.record_name}", material.declared_properties
        )
    for sample in db.scalars(select(Sample).where(Sample.deleted_at.is_(None))):
        rows += _zero_points(
            f"시료 {sample.code} {sample.record_name}", sample.declared_properties
        )
    return rows


def _fingerprint(declared: list[dict[str, Any]]) -> str:
    # 근거 · 승인 지문은 빼고 「무엇을 적었나」 만 견준다.
    kept = [
        {key: value for key, value in row.items() if key not in ("approval", "catalog")}
        for row in declared
    ]
    return json.dumps(sorted(kept, key=lambda row: str(row.get("item"))), sort_keys=True)


def declared_copies(db: Session) -> tuple[list[str], int]:
    groups: dict[str, list[Material]] = defaultdict(list)
    for material in db.scalars(select(Material).where(Material.deleted_at.is_(None))):
        if material.declared_properties:
            groups[_fingerprint(material.declared_properties)].append(material)
    rows: list[str] = []
    count = 0
    for members in groups.values():
        if len(members) < 2:
            continue
        count += len(members)
        names = ", ".join(f"{one.code} {one.record_name}" for one in members[:6])
        more = f" 외 {len(members) - 6}" if len(members) > 6 else ""
        items = ", ".join(str(row.get("item")) for row in members[0].declared_properties[:4])
        rows.append(f"재료 {len(members)}개가 선언 물성이 통째로 같다({items}): {names}{more}")
    return rows, count


# ⑤ ------------------------------------------------------------------------------------
def _produced_units() -> dict[str, str]:
    processing.load_builtin()
    extensions.load(get_settings().extensions_dir)
    out: dict[str, str] = {}
    for plugin in registry.list_plugins():
        for made in plugin.makes_columns:
            if "{" not in made.key and made.si_unit:
                out[made.key] = made.si_unit
    return out


def _range_steps(steps: list[dict[str, Any]], channel_units: dict[str, str]) -> list[str]:
    out: list[str] = []
    for step in steps or []:
        if step.get("plugin") not in RANGE_STEPS:
            continue
        options = step.get("options") or {}
        column = str(options.get("x") or "")
        unit = channel_units.get(column)
        if not unit or unit == "1":
            continue
        ends = [
            f"{name} {_shown(float(options[name]), unit)}"
            for name in ("start", "end")
            if isinstance(options.get(name), int | float)
            and not isinstance(options.get(name), bool)
        ]
        if ends:
            out.append(f"{step.get('plugin')} 기준 열 {column}: " + " · ".join(ends))
    return out


def unit_column_ranges(db: Session) -> tuple[list[str], int]:
    produced = _produced_units()
    by_type: dict[Any, dict[str, str]] = defaultdict(lambda: dict(produced))
    for channel in db.scalars(select(TestChannel)):
        by_type[channel.test_type_id][channel.key] = channel.si_unit

    rows: list[str] = []
    for recipe in db.scalars(
        select(ProcessingRecipe).where(ProcessingRecipe.deleted_at.is_(None))
    ):
        for line in _range_steps(recipe.steps, by_type[recipe.test_type_id]):
            rows.append(f"레시피 「{recipe.label}」({recipe.key}) · {line}")

    # 그 단계로 돌린 결과 가운데 **채택된 것**만 센다 — 카드 · 덱으로 가는 것이 그것이다.
    adopted = 0
    for crop in RANGE_STEPS:
        for result, run in db.execute(
            select(ProcessingResult, TestRun)
            .join(TestRun, TestRun.adopted_result_id == ProcessingResult.id)
            .where(ProcessingResult.steps_snapshot.op("@>")(cast([{"plugin": crop}], JSONB)))
        ).all():
            if _range_steps(result.steps_snapshot, by_type[run.test_type_id]):
                adopted += 1
    if adopted:
        rows.append(
            f"(그런 단계로 돌린 결과가 채택된 시험 {adopted}건 — 카드 · 덱으로 간 값이다)"
        )
    return rows, len(rows) - (1 if adopted else 0)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--limit", type=int, default=50, help="항목마다 보여 줄 줄 수")
    limit = parser.parse_args().limit

    db = SessionLocal()
    try:
        # **아무것도 쓰지 않는다** — 실수로 쓰는 코드가 끼어도 DB 가 거절한다.
        db.execute(text("SET TRANSACTION READ ONLY"))
        report = Report(limit)
        print("2026-10-04 수정 전에 남았을 수 있는 흔적 — 읽기만 합니다.")

        report.section(
            "① 각주파수만 있는 표에서 가져온 마스터커브",
            angular_master_curves(db),
            advice="그 마스터커브를 지우고 같은 표에서 다시 가져온 뒤(이제 Hz 로 담긴다), "
            "그 위의 Prony 를 다시 맞춘다. 대표였으면 새 것을 대표로 지정한다.",
        )
        report.section(
            "② 단위 환산이 빠졌을 수 있는 문헌 값 불확도(직접 넣은 값)",
            catalog_uncertainty(db),
            advice="값 상세에서 그 값을 지우고 같은 값 · 같은 단위로 다시 넣는다 — 이제 "
            "불확도도 환산된다. 정말 그만큼 작은 불확도면 그대로 둔다.",
        )
        report.section(
            "③ 같은 이름으로 바꿔 덮인 옛 원본",
            overwritten_sources(db),
            advice="옛 원본은 되돌릴 수 없다(백업 미러도 같은 경로라 같은 내용). 그 시험의 "
            "처리 결과가 어느 원본의 것인지 이력으로 확인한다.",
        )
        report.section(
            "④-1 선언 물성에 0 인 점(빈 칸이 0 으로 저장됐을 수 있다)",
            declared_zeros(db),
            advice="정말 0 이면 그대로, 빈 칸이었으면 그 점을 지우거나 값을 적어 다시 "
            "저장한다.",
        )
        copies, copied = declared_copies(db)
        report.section(
            "④-2 선언 물성이 통째로 같은 재료(다른 재료의 줄이 들어갔을 수 있다)",
            copies,
            count=copied,
            advice="같은 시트에서 온 재료면 정상이다. 아니면 감사 기록에서 그 재료의 선언 "
            "물성 수정을 찾아 원래 값으로 되돌린다.",
        )
        ranges, ranged = unit_column_ranges(db)
        report.section(
            "⑤ 단위 있는 열로 시작 · 끝을 적은 구간 자르기 · 재샘플",
            ranges,
            count=ranged,
            advice="계산은 전과 같다 — 저장된 값(SI)으로 돌아 왔다. 이제 화면에 그 값이 "
            "그대로 보인다. 25 °C 를 뜻하고 25 를 적었다면 실제로는 25 K(-248 °C)로 "
            "잘린 것이니, 레시피 값을 고쳐 저장하고 다시 돌린다.",
        )
        print(
            f"\n합계 {report.findings}건. 0 이면 손볼 것이 없다. "
            "(별칭은 누가 달았는지 안 남아 세지 못한다)"
        )
    finally:
        db.rollback()
        db.close()


if __name__ == "__main__":
    main()
