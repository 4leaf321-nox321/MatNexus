"""묶음을 만들고 통계를 낸다 — **저장소와 계산 커널 사이.**

`matcore.statistics` 는 값 목록과 격자만 안다. "어느 시험들이 한 묶음인가",
"채택된 결과에서 무엇을 꺼내는가" 는 여기서 정한다.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.materials.models import Material, Sample, Specimen
from app.modules.processing.models import ProcessingResult
from app.modules.tests.models import TestRun, TestType
from app.shared import curvedata, filestore, permissions
from app.shared.errors import NotFound
from matcore import curves, statistics

#: 평균이 뜻이 없는 값. **차원으로 거르고 남는 예외들이다.**
#:
#:   proof_offset      설정값이다. 시편마다 다르면 서로 다른 조건으로 잰 것이고,
#:                     평균이 아니라 **경고**가 나와야 한다.
#:   *_index           배열 위치다. 평균 14.0 은 아무 뜻이 없다.
#:   elastic_r_squared 적합도다. 평균보다 최솟값이 중요하다.
SETTING_KEYS = frozenset({"proof_offset"})
SKIP_KEYS = frozenset({"elastic_r_squared"})


def _is_averageable(scalar: dict[str, Any]) -> bool:
    key = str(scalar.get("key", ""))
    if key in SETTING_KEYS or key in SKIP_KEYS or key.endswith("_index"):
        return False
    # 차원이 없으면 무엇인지 모른다. 개수인지 비율인지 구분이 안 되므로 뺀다 —
    # 단위가 `1` 인 값에는 변형률도 있고 배열 위치도 있다.
    return bool(scalar.get("dimension")) or str(scalar.get("si_unit") or "1") != "1"


@dataclass(frozen=True)
class Member:
    """묶음의 한 시편."""

    run: TestRun
    result: ProcessingResult
    specimen: Specimen


@dataclass(frozen=True)
class Group:
    """통계 한 묶음 — **재료 + 시험종류 + 방향.**"""

    material: Material
    test_type: TestType
    orientation: str
    members: list[Member]
    skipped_unadopted: int
    """채택되지 않아 빠진 시험 수. **조용히 빼면 n 이 왜 15가 아닌지 모른다.**"""


def groups_for_material(
    db: Session, user: object, material_id: uuid.UUID
) -> tuple[Material, list[Group]]:
    """재료 하나의 묶음들. 방향마다 따로 나온다."""
    material = db.scalar(
        permissions.visible_materials(db, user).where(Material.id == material_id)  # type: ignore[arg-type]
    )
    if material is None:
        raise NotFound("MNX-MATERIALS-0001", "재료를 찾을 수 없습니다.")

    rows = db.execute(
        select(TestRun, Specimen)
        .join(Specimen, Specimen.id == TestRun.specimen_id)
        .join(Sample, Sample.id == Specimen.sample_id)
        .where(
            Sample.material_id == material.id,
            TestRun.deleted_at.is_(None),
            Specimen.deleted_at.is_(None),
        )
    ).all()

    buckets: dict[tuple[uuid.UUID, str], list[tuple[TestRun, Specimen]]] = {}
    for run, specimen in rows:
        buckets.setdefault((run.test_type_id, specimen.orientation), []).append(
            (run, specimen)
        )

    result_ids = [run.adopted_result_id for run, _ in rows if run.adopted_result_id]
    adopted = {
        item.id: item
        for item in db.scalars(
            select(ProcessingResult).where(ProcessingResult.id.in_(result_ids))
        )
    }
    types = {
        item.id: item
        for item in db.scalars(
            select(TestType).where(TestType.id.in_({run.test_type_id for run, _ in rows}))
        )
    }

    groups: list[Group] = []
    for (type_id, orientation), items in sorted(
        buckets.items(), key=lambda entry: (str(entry[0][0]), entry[0][1])
    ):
        members = [
            Member(run=run, result=adopted[run.adopted_result_id], specimen=specimen)
            for run, specimen in items
            if run.adopted_result_id and run.adopted_result_id in adopted
        ]
        test_type = types.get(type_id)
        if test_type is None:
            continue
        groups.append(
            Group(
                material=material,
                test_type=test_type,
                orientation=orientation,
                members=members,
                skipped_unadopted=len(items) - len(members),
            )
        )
    return material, groups


def scalar_table(group: Group, *, threshold: float) -> list[dict[str, Any]]:
    """항목별 통계와 이상치 후보.

    **어느 시편이 이상치인지 되짚을 수 있어야 한다.** 커널은 표본 목록의 자리만
    돌려주므로, 여기서 그 자리를 시험 이름으로 바꾼다.
    """
    by_key: dict[str, dict[str, Any]] = {}
    for member in group.members:
        for scalar in member.result.scalars:
            key = str(scalar.get("key", ""))
            if not _is_averageable(scalar):
                continue
            entry = by_key.setdefault(
                key,
                {
                    "key": key,
                    "label": scalar.get("label") or key,
                    "si_unit": scalar.get("si_unit") or "1",
                    "dimension": scalar.get("dimension"),
                    "_values": [],
                    "_runs": [],
                },
            )
            entry["_values"].append(float(scalar.get("value", 0.0)))
            entry["_runs"].append(member.run)

    table: list[dict[str, Any]] = []
    for entry in by_key.values():
        values = entry.pop("_values")
        runs = entry.pop("_runs")

        if len(values) == 1:
            # **시험이 1건이어도 값은 보여 준다.**
            #
            # 전에는 `scalar_stats` 가 1건을 거부하고 그 항목이 통째로 빠져,
            # 물성 탭에 **빈 카드만 남았다.** 처리하고 채택까지 한 사람이
            # "아무것도 안 뜬다" 를 보게 된다 — 값은 분명히 있는데.
            #
            # 흩어짐은 여전히 내지 않는다(SD·CV·신뢰구간·이상치는 없음). 그것이
            # ADR 0008 이 지키려는 것이고, 여기서 주는 것은 **통계가 아니라 그
            # 시편의 값**이다. `count=1` 이 그 사실을 말한다.
            table.append(
                {
                    **entry,
                    "count": 1,
                    "mean": values[0],
                    "median": values[0],
                    "minimum": values[0],
                    "maximum": values[0],
                    "sample_sd": None,
                    "mad": None,
                    "iqr": None,
                    "coefficient_of_variation": None,
                    "ci95_low": None,
                    "ci95_high": None,
                    "outliers": [],
                }
            )
            continue

        try:
            stats = statistics.scalar_stats(values)
        except statistics.StatisticsError:
            # 항목 하나가 모자란다고 표 전체를 버리지 않는다. 시편마다 나오는
            # 항목이 다를 수 있다(네킹을 못 찾은 시편 등).
            continue
        found = statistics.outliers(values, threshold=threshold)
        table.append(
            {
                **entry,
                "count": stats.count,
                "mean": stats.mean,
                "sample_sd": stats.sample_sd,
                "median": stats.median,
                "mad": stats.mad,
                "iqr": stats.iqr,
                "minimum": stats.minimum,
                "maximum": stats.maximum,
                "coefficient_of_variation": stats.coefficient_of_variation,
                "ci95_low": stats.ci95_low,
                "ci95_high": stats.ci95_high,
                "outliers": [
                    {
                        "test_run_id": str(runs[item.index].id),
                        "record_name": runs[item.index].record_name,
                        "value": item.value,
                        "score": item.score,
                        "reason": item.reason,
                    }
                    for item in found
                ],
            }
        )
    return sorted(table, key=lambda row: str(row["key"]))


def setting_warnings(group: Group) -> list[str]:
    """설정값이 시편마다 다른가.

    **다르면 서로 다른 조건으로 잰 것이다.** 0.2% 오프셋으로 잰 것과 0.5% 로 잰
    것을 평균 내면 그 평균은 아무것도 뜻하지 않는다. 평균을 내지 않고 말해 준다.
    """
    seen: dict[str, set[float]] = {}
    for member in group.members:
        for scalar in member.result.scalars:
            key = str(scalar.get("key", ""))
            if key in SETTING_KEYS:
                seen.setdefault(key, set()).add(round(float(scalar.get("value", 0.0)), 12))
    return [
        f"'{key}' 가 시편마다 다릅니다({', '.join(str(v) for v in sorted(values))}) — "
        f"서로 다른 조건으로 잰 값을 함께 보고 있습니다."
        for key, values in seen.items()
        if len(values) > 1
    ]


def curve_table(
    db: Session, group: Group, *, x: str, y: str
) -> tuple[dict[str, Any] | None, list[str]]:
    """점별 곡선 통계. 격자가 다르면 계산하지 않고 이유를 돌려준다."""
    if len(group.members) == 1:
        # **1건이면 그 곡선이 곧 대표다.**
        #
        # 평균을 낼 상대가 없다는 것은 계산이 불가능하다는 뜻이 아니다. 격자를
        # 맞출 이유도 없다 — 맞출 상대가 없으니 재샘플 없이도 그릴 수 있다.
        # 전에는 문턱값(2건) 때문에 곡선을 아예 안 냈고, 화면에는 "대표 곡선을
        # 만들 수 없습니다" 만 떴다. 있는 곡선을 못 본 것이다.
        #
        # 평균과 중앙값을 같은 값으로 둔다 — 한 점의 평균도 중앙값도 그 점이다.
        # **흩어짐은 내지 않는다**(`sd` 가 빈다). 0 을 넣으면 "여러 번 재서
        # 같았다" 로 읽힌다.
        member = group.members[0]
        raw = curves.read_columns(filestore.read_bytes(member.result.storage_path))
        if x not in raw or y not in raw:
            return None, [
                f"'{member.run.record_name}' 의 처리 결과에 '{x}' 또는 '{y}' 열이 없습니다."
            ]
        points = [
            (0.0 if px is None else float(px), 0.0 if py is None else float(py))
            for px, py in zip(raw[x], raw[y], strict=True)
        ]
        return (
            {
                "x": x,
                "y": y,
                "mean": points,
                "median": points,
                "sd": [],
                "count": [(px, 1.0) for px, _ in points],
            },
            [
                f"시편 1개('{member.run.record_name}')의 곡선입니다 — "
                f"평균이 아니라 그 시편의 값입니다."
            ],
        )

    grids: list[np.ndarray] = []
    values: list[np.ndarray] = []
    for member in group.members:
        raw = curves.read_columns(filestore.read_bytes(member.result.storage_path))
        if x not in raw or y not in raw:
            return None, [
                f"'{member.run.record_name}' 의 처리 결과에 '{x}' 또는 '{y}' 열이 없습니다. "
                f"같은 레시피로 처리했는지 확인하세요."
            ]
        grids.append(np.asarray([0.0 if v is None else v for v in raw[x]], dtype=np.float64))
        values.append(np.asarray([0.0 if v is None else v for v in raw[y]], dtype=np.float64))

    try:
        stats = statistics.curve_stats(grids, values)
    except statistics.StatisticsError as exc:
        check = statistics.grid_check(grids)
        note = str(exc)
        if check.common_start is not None and check.shortest_index is not None:
            shortest = group.members[check.shortest_index].run.record_name
            note += f" 가장 짧은 곡선은 '{shortest}' 입니다."
        return None, [note]

    return (
        {
            "x": x,
            "y": y,
            "mean": stats.mean_curve,
            "median": stats.median_curve,
            "sd": [(point.x, point.y.sample_sd) for point in stats.points],
            "count": [(point.x, float(point.y.count)) for point in stats.points],
        },
        list(stats.notes),
    )


#: 볼 만한 축 짝. 앞이 우선이다 — 인장이면 공칭 응력-변형률이 먼저다.
AXIS_PAIRS = (
    ("strain_engineering", "stress_engineering"),
    ("strain_true_plastic", "stress_true"),
)


def axis_candidates(db: Session, group: Group) -> list[tuple[str, str]]:
    """그려 볼 축들. **하나가 아니라 목록인 이유:**

    격자가 맞는 축은 레시피가 정한다. 진소성변형률 축에서 재샘플한 결과는 그
    축에서만 격자가 맞고 공칭 축에서는 안 맞는다 — 실측으로 그 상태가 나왔고,
    앞의 축 하나만 보고 포기해서 "적합은 되는데 곡선은 안 보인다" 가 됐다.

    **정렬을 대신 하는 것이 아니다**(ADR 0008). 있는 그대로 그릴 수 있는 축을
    고를 뿐이고, 어느 축으로 그렸는지는 응답에 실린다.
    """
    if not group.members:
        return []
    columns = set(group.members[0].result.columns)
    found = [(x, y) for x, y in AXIS_PAIRS if x in columns and y in columns]
    if found:
        return found
    units = curvedata.channel_units(db, group.test_type.id)
    ordered = sorted(columns)
    return [(ordered[0], ordered[1])] if len(ordered) >= 2 and units else []


def default_axes(db: Session, group: Group) -> tuple[str, str]:
    """무엇을 x·y 로 볼지. 후보 중 첫 번째다."""
    found = axis_candidates(db, group)
    return found[0] if found else ("", "")
