"""휴지통 — **지운 것을 보고, 되살리고, 영영 지운다.**

## 왜 필요한가

삭제가 소프트라 행은 남는데 **볼 자리가 없었다.** 그래서 지운 것은 "사라진 것"
도 "남은 것" 도 아닌 상태가 됐고, 실제로 사고가 났다(2026-08-28): 이관에서 금속
재료를 지운 뒤 같은 이름으로 다시 넣으려다 전부 막혔는데, 막은 그 행이 **화면
어디에도 없어서** 이유를 알 방법이 없었다.

유니크는 부분 인덱스로 고쳤다(`c3d7b21f9a04`). 그러나 그것은 **막히지 않게** 한
것이지, 지운 것을 **볼 수 있게** 한 것이 아니다. 이 파일이 그 나머지다.

## 되살리기 — 위는 살아 있어야 하고, 아래는 함께 온다

    ↑ 조상   살아 있어야 한다.   아니면 되살려도 화면에서 닿을 수 없다
    ↓ 후손   함께 되살린다.      한 번의 삭제로 함께 죽었으니 함께 살아난다

조상이 죽어 있으면 **막고 무엇을 먼저 되살릴지 말한다.** 조용히 조상까지 되살리지
않는다 — 재료 하나를 되살리려다 시험 200건이 함께 돌아오는 것은 사람이 예상하지
못하는 일이다.

**이름이 이미 남에게 가 있으면 막는다.** 지운 이름을 다시 쓸 수 있게 됐으므로
(그것이 위 수정이다) 되살릴 자리가 이미 차 있을 수 있다. 그때 조용히 덮으면 살아
있는 데이터가 다친다.

## 영영 지우기 — 되돌릴 수 없다

행을 진짜로 지우고 곡선 파일까지 치운다. **이 길에는 자동이 없다** — 오래된 것을
알아서 비우는 잡을 두지 않는다. 이 저장소에서 되돌릴 수 없는 일은 전부 사람이
한 번 더 누르게 되어 있다.
"""

from __future__ import annotations

import contextlib
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.modules.accounts.models import User
from app.modules.materials.models import Material, Sample, Specimen
from app.modules.tests.models import Curve, TestRun, TestSummary
from app.modules.vocabulary import services as vocabulary_services
from app.shared import audit, filestore
from app.shared.errors import AppError, Conflict, NotFound

#: 다루는 것. **재료 계층과 시험이다** — 이관과 실사용에서 지워지는 것이 이 넷이다.
#: 계정은 뺐다: 성격이 달라(권한·소속) 같은 표에 섞으면 읽히지 않고, 계정 관리
#: 화면이 이미 따로 있다.
KINDS = ("material", "sample", "specimen", "test_run")

#: 종류 → (모델, 사람이 읽는 이름). 순서는 위에서 아래로 — 화면이 그대로 그린다.
#:
#: **모델 타입을 `Any` 로 둔다.** 넷을 한 규칙으로 다루는 것이 이 파일의 요점인데,
#: 그러면 컬럼 접근이 전부 유니온이 되어 `# type: ignore` 가 줄마다 붙는다. 무시
#: 주석이 스무 개 붙은 코드는 타입을 지키는 것이 아니라 지키는 척하는 것이다.
_MODELS: dict[str, tuple[Any, str]] = {
    "material": (Material, "재료"),
    "sample": (Sample, "시료"),
    "specimen": (Specimen, "시편"),
    "test_run": (TestRun, "시험"),
}

#: 되살릴 때 되돌려 놓을 기준정보 연결. 지울 때 `release_bindings` 가 뺀 것을
#: 그대로 다시 더한다 — 안 되돌리면 피커의 「쓰는 곳」 이 실제보다 작아진다.
_BINDINGS = {
    "material": vocabulary_services.MATERIAL_BINDINGS,
    "sample": vocabulary_services.SAMPLE_BINDINGS,
    "specimen": vocabulary_services.SPECIMEN_BINDINGS,
    "test_run": vocabulary_services.TEST_RUN_BINDINGS,
}


@dataclass(frozen=True)
class Item:
    """휴지통의 한 줄."""

    kind: str
    kind_label: str
    id: uuid.UUID
    name: str
    deleted_at: datetime
    workspace_id: uuid.UUID | None
    #: 이 행 아래에 함께 지워진 것. 되살리면 함께 돌아온다.
    below: dict[str, int]
    #: 되살릴 수 있나. 아니면 그 이유.
    blocked: str | None


def _name(kind: str, row: Any) -> str:
    if kind == "test_run":
        return str(getattr(row, "record_name", "") or getattr(row, "source_filename", ""))
    return str(getattr(row, "record_name", "") or "")


def _rows(db: Session, kind: str, *, limit: int) -> list[Any]:
    model, _ = _MODELS[kind]
    return list(
        db.scalars(
            select(model)
            .where(model.deleted_at.is_not(None))
            .order_by(model.deleted_at.desc())
            .limit(limit)
        )
    )


# --- 아래에 무엇이 딸려 있나 -------------------------------------------------


def _below(db: Session, kind: str, row: Any) -> dict[str, int]:
    """이 행 아래에 **함께 지워진** 것의 수. 살아 있는 것은 안 센다.

    되살리면 함께 돌아오는 것이 곧 이 숫자다 — 사람이 「되살리기」 를 누를 근거다.
    """
    if kind == "test_run":
        return {}

    counted: dict[str, int] = {}
    if kind == "material":
        samples = _ids(db, Sample, Sample.material_id == row.id)
        specimens = _ids(db, Specimen, Specimen.sample_id.in_(samples)) if samples else []
    else:  # sample
        samples = []
        specimens = _ids(db, Specimen, Specimen.sample_id == row.id)

    if kind == "specimen":
        specimens = [row.id]

    if samples:
        counted["시료"] = len(samples)
    if specimens and kind != "specimen":
        counted["시편"] = len(specimens)
    if specimens:
        runs = db.scalar(
            select(func.count())
            .select_from(TestRun)
            .where(TestRun.specimen_id.in_(specimens), TestRun.deleted_at.is_not(None))
        )
        if runs:
            counted["시험"] = int(runs)
    return counted


def _ids(db: Session, model: Any, where: Any) -> list[uuid.UUID]:
    """지워진 자식의 id. **지워진 것만** 본다 — 살아 있는 자식은 되살릴 대상이 아니다."""
    return list(db.scalars(select(model.id).where(where, model.deleted_at.is_not(None))))


# --- 되살릴 수 있나 ----------------------------------------------------------


def _blocker(db: Session, kind: str, row: Any) -> str | None:
    """되살리기를 막는 이유. 없으면 `None`.

    **막는 것이 둘이다** — 조상이 죽어 있거나, 자리가 이미 차 있거나.
    """
    if kind == "material":
        taken = db.scalar(
            select(func.count())
            .select_from(Material)
            .where(
                Material.record_name == row.record_name,
                Material.owner_workspace_id == row.owner_workspace_id,
                Material.deleted_at.is_(None),
            )
        )
        if taken:
            return (
                f"같은 이름의 재료가 이미 살아 있습니다: {row.record_name}. "
                f"그쪽을 지우거나 이름을 바꾼 뒤에 되살리세요."
            )
        return None

    if kind == "sample":
        material = db.get(Material, row.material_id)
        if material is None or material.deleted_at is not None:
            return "상위 재료가 지워져 있습니다. 재료를 먼저 되살리세요."
        return _seq_taken(db, Sample, Sample.material_id == row.material_id, row, "시료")

    if kind == "specimen":
        sample = db.get(Sample, row.sample_id)
        if sample is None or sample.deleted_at is not None:
            return "상위 시료가 지워져 있습니다. 시료를 먼저 되살리세요."
        return _seq_taken(
            db,
            Specimen,
            (Specimen.sample_id == row.sample_id) & (Specimen.orientation == row.orientation),
            row,
            "시편",
        )

    specimen = db.get(Specimen, row.specimen_id)
    if specimen is None or specimen.deleted_at is not None:
        return "상위 시편이 지워져 있습니다. 시편을 먼저 되살리세요."
    return None


def _seq_taken(db: Session, model: Any, where: Any, row: Any, label: str) -> str | None:
    taken = db.scalar(
        select(func.count())
        .select_from(model)
        .where(where, model.seq_no == row.seq_no, model.deleted_at.is_(None))
    )
    if taken:
        return f"그 자리에 살아 있는 {label} 가 이미 있습니다 ({row.seq_no}번)."
    return None


# --- 목록 -------------------------------------------------------------------


def listing(db: Session, *, kind: str | None, limit: int) -> list[Item]:
    """지운 것 목록. **최근에 지운 것부터.**

    `kind` 를 주면 그 종류만. 안 주면 넷을 모아 한 표로 낸다 — 사람은 "무엇을
    지웠더라" 를 종류로 기억하지 않는다.
    """
    kinds = [kind] if kind else list(KINDS)
    items: list[Item] = []
    for one in kinds:
        if one not in _MODELS:
            raise AppError("MNX-TRASH-0001", f"모르는 종류입니다: {one}", status=422)
        for row in _rows(db, one, limit=limit):
            items.append(
                Item(
                    kind=one,
                    kind_label=_MODELS[one][1],
                    id=row.id,
                    name=_name(one, row),
                    deleted_at=row.deleted_at,
                    workspace_id=getattr(row, "workspace_id", None)
                    or getattr(row, "owner_workspace_id", None),
                    below=_below(db, one, row),
                    blocked=_blocker(db, one, row),
                )
            )
    items.sort(key=lambda item: item.deleted_at, reverse=True)
    return items[:limit]


def _get(db: Session, kind: str, item_id: uuid.UUID) -> Any:
    if kind not in _MODELS:
        raise AppError("MNX-TRASH-0001", f"모르는 종류입니다: {kind}", status=422)
    model, label = _MODELS[kind]
    row = db.get(model, item_id)
    if row is None:
        raise NotFound("MNX-TRASH-0002", f"그 {label} 를 찾을 수 없습니다.")
    if row.deleted_at is None:
        raise Conflict("MNX-TRASH-0003", f"이 {label} 는 지워져 있지 않습니다.")
    return row


# --- 되살리기 ----------------------------------------------------------------


def _tree(db: Session, kind: str, row: Any) -> dict[str, list[Any]]:
    """이 행과 **함께 지워진 아래 전부.** 되살리기와 영구 삭제가 같은 것을 본다.

    두 길이 다른 목록을 보면, 화면이 보여 준 숫자와 실제로 손대는 것이 어긋난다.
    """
    materials: list[Any] = [row] if kind == "material" else []
    samples: list[Any] = [row] if kind == "sample" else []
    specimens: list[Any] = [row] if kind == "specimen" else []
    runs: list[Any] = [row] if kind == "test_run" else []

    if kind == "material":
        samples = _dead(db, Sample, Sample.material_id == row.id)
    if kind in ("material", "sample"):
        parents = [s.id for s in samples] or ([row.id] if kind == "sample" else [])
        specimens = _dead(db, Specimen, Specimen.sample_id.in_(parents)) if parents else []
    if kind in ("material", "sample", "specimen"):
        parents = [s.id for s in specimens] or ([row.id] if kind == "specimen" else [])
        runs = _dead(db, TestRun, TestRun.specimen_id.in_(parents)) if parents else []

    return {
        "material": materials,
        "sample": samples,
        "specimen": specimens,
        "test_run": runs,
    }


def _dead(db: Session, model: Any, where: Any) -> list[Any]:
    return list(db.scalars(select(model).where(where, model.deleted_at.is_not(None))))


@dataclass(frozen=True)
class Done:
    """무엇에 손댔는지. 화면이 그대로 말한다."""

    name: str
    counts: dict[str, int]

    @property
    def said(self) -> str:
        parts = [f"{label} {count}건" for label, count in self.counts.items() if count]
        return ", ".join(parts) if parts else "없음"


def restore(db: Session, kind: str, item_id: uuid.UUID, *, actor: User) -> Done:
    """되살린다 — **이 행과 그 아래 함께 지워진 것 전부.**

    **커밋은 부르는 쪽이 한다**(`delete_tree` 와 같은 규칙).
    """
    row = _get(db, kind, item_id)
    blocked = _blocker(db, kind, row)
    if blocked:
        raise Conflict("MNX-TRASH-0004", blocked)

    tree = _tree(db, kind, row)
    counts: dict[str, int] = {}
    for one in KINDS:
        rows = tree[one]
        if not rows:
            continue
        counts[_MODELS[one][1]] = len(rows)
        for target in rows:
            target.deleted_at = None
            # 지울 때 뺀 것을 그대로 되돌린다.
            for binding in _BINDINGS[one]:
                vocabulary_services.bump_usage(db, getattr(target, binding.column), 1)

    done = Done(name=_name(kind, row), counts=counts)
    audit.record(
        db,
        action=audit.TRASH_RESTORED,
        actor=actor,
        target_table=_MODELS[kind][0].__tablename__,
        target_id=item_id,
        target_label=done.name,
        workspace_id=getattr(row, "workspace_id", None)
        or getattr(row, "owner_workspace_id", None),
        changes={"deleted_at": {"before": "set", "after": None}, "restored": done.counts},
    )
    return done


# --- 영영 지우기 -------------------------------------------------------------


def purge(db: Session, kind: str, item_id: uuid.UUID, *, actor: User) -> Done:
    """행을 진짜로 지운다. **되돌릴 수 없다.**

    곡선 파일까지 치운다 — 행만 지우면 디스크에 주인 없는 파일이 남고, 그것은
    아무도 찾지 못하는 용량이 된다.

    **감사 기록을 먼저 남긴다.** 행이 사라지고 나면 무엇이었는지 적을 수 없다.
    """
    row = _get(db, kind, item_id)
    tree = _tree(db, kind, row)
    counts = {_MODELS[one][1]: len(tree[one]) for one in KINDS if tree[one]}
    done = Done(name=_name(kind, row), counts=counts)

    audit.record(
        db,
        action=audit.TRASH_PURGED,
        actor=actor,
        target_table=_MODELS[kind][0].__tablename__,
        target_id=item_id,
        target_label=done.name,
        workspace_id=getattr(row, "workspace_id", None)
        or getattr(row, "owner_workspace_id", None),
        changes={"purged": done.counts},
    )

    # **아래에서 위로.** 위부터 지우면 FK 가 막고, 막힌 자리에서 이미 지운 것은
    # 돌아오지 않는다.
    runs: Sequence[Any] = tree["test_run"]
    for run in runs:
        _purge_run(db, run)
    for one in ("specimen", "sample", "material"):
        for target in tree[one]:
            db.delete(target)
    return done


def _purge_run(db: Session, run: Any) -> None:
    """시험 하나와 그 곡선·요약값·파일."""
    db.execute(delete(Curve).where(Curve.test_run_id == run.id))
    db.execute(delete(TestSummary).where(TestSummary.test_run_id == run.id))
    # **파일 실패로 멈추지 않는다.** 이미 사라진 파일이 흔하다(정리 잡이 먼저
    # 치웠을 수 있다). 행은 지워야 하고, 남은 파일은 저장소 정리가 다시 잡는다.
    source = getattr(run, "source_path", None)
    if source:
        with contextlib.suppress(OSError):
            filestore.delete_dir(str(source).rsplit("/", 1)[0])
    db.delete(run)
