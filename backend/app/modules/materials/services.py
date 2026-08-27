"""재료·시료·시편 로직 — 단위 변환, 이름 생성, 채번, 가시 범위.

라우트에서 이것들을 하지 않는 이유가 두 가지다. 하나는 **이름을 만드는 곳이
하나여야** 하기 때문이고(기존 앱은 화면이 만들어서 서버·배치가 같은 이름을 만들
수 없었다), 다른 하나는 가시 범위 판정이 흩어지면 "이 목록에만 전역 재료가 안
보인다" 같은 어긋남이 생기기 때문이다.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.accounts.models import User
from app.modules.materials.models import USE_AXES, Material, MaterialUse, Sample, Specimen
from app.modules.tests.models import TestRun, TestType
from app.modules.vocabulary import services as vocabulary_services
from app.modules.workspaces.models import Workspace
from app.shared import permissions, vocabulary_hooks
from app.shared.errors import AppError, Conflict, Forbidden, NotFound
from matcore import naming, units

logger = logging.getLogger(__name__)

# --- 단위 -------------------------------------------------------------------


def to_si(value: float | None, unit: str, *, field: str, dimension: str) -> float | None:
    """사람 단위 → 저장 단위. 모르는 단위도, **차원이 다른 단위도** 거부한다.

    조용히 계수 1로 통과시키면 잘못된 값이 SI 인 척 저장되고, 나중에 어느 행이
    틀렸는지 알아낼 방법이 없다.

    ## 차원을 왜 받는가

    실측으로 걸렸다(2026-08-27, 전체 흐름 점검). 두께 자리에 `kg` 을 보냈더니
    **201 로 통과했다.** `kg` 은 아는 단위라 `UnknownUnit` 이 안 나고, 환산은
    질량 자리에서 무사히 끝나며, 그 결과가 `spec_thickness_m` 에 들어간다 —
    `1 kg` 이 **두께 1 m(=1000 mm)** 짜리 재료가 됐다. 화면에도 DB 에도 이상한
    데가 없고, 나중에 그 재료로 뽑은 덱이 조용히 틀린다.

    그래서 `dimension` 은 **기본값이 없다.** 새 칸을 붙이는 사람이 무엇을
    기대하는지 적지 않고는 이 함수를 못 부른다 — 시험 조건 쪽은 이미 같은
    검사를 하고 있었고(`tests/services.py`), 여기만 빠져 있었다.
    """
    # **값보다 단위를 먼저 본다.** 값이 비어 있어도 단위는 `input_units` 에
    # 그대로 저장된다. 거기 엉뚱한 단위가 앉으면, 나중에 값을 채우려는 순간
    # 막히는데 그 사람은 자기가 방금 적은 것만 보고 있어 이유를 알 수 없다.
    try:
        found = units.unit_of(unit)
    except units.UnknownUnit as exc:
        raise AppError(
            "MNX-MATERIALS-0005",
            f"{field} 의 단위를 알 수 없습니다: {exc.symbol}",
            status=422,
        ) from exc
    if not units.same_dimension(found.dimension, dimension):
        raise AppError(
            "MNX-MATERIALS-0028",
            f"{field} 는 {dimension} 인데 {unit} 은 {found.dimension} 입니다. "
            f"쓸 수 있는 단위: {', '.join(units.units_for(dimension))}",
            status=422,
        )
    if value is None:
        return None
    return units.to_si(value, unit)


def from_si(value: float | None, unit: str) -> float | None:
    return None if value is None else units.from_si(value, unit)


# --- 가시 범위 --------------------------------------------------------------


#: 가시 범위 판정은 `shared/permissions` 하나뿐이다. 재료·시료·시편·시험이 전부
#: 같은 규칙을 따라야 하는데, 모듈마다 자기 버전을 두면 "재료는 보이는데 그 시험은
#: 안 보인다" 같은 어긋남이 생긴다.
my_workspace_ids = permissions.my_workspace_ids
visible_materials = permissions.visible_materials


def get_material(db: Session, user: User, material_id: uuid.UUID) -> Material:
    material = db.scalar(visible_materials(db, user).where(Material.id == material_id))
    if material is None:
        raise NotFound("MNX-MATERIALS-0001", "재료를 찾을 수 없습니다.")
    return material


def require_writable(db: Session, user: User, material: Material) -> None:
    """전역 재료는 관리자만 고친다.

    아니면 A부서가 이름을 바꿔 B부서 데이터의 맥락이 사라진다 — 전역으로 올린
    순간 그 재료는 특정 부서의 것이 아니게 된다.
    """
    if user.is_system_admin:
        return
    if material.owner_workspace_id is None:
        raise Forbidden(
            "MNX-MATERIALS-0007", "전역 재료는 시스템 관리자만 수정할 수 있습니다."
        )
    if material.owner_workspace_id not in my_workspace_ids(db, user):
        raise Forbidden("MNX-MATERIALS-0008", "이 재료를 수정할 권한이 없습니다.")


def resolve_workspace(db: Session, user: User, slug: str | None) -> Workspace:
    """등록 대상 부서. 생략하면 내 소속 부서."""
    if slug is not None:
        workspace = db.scalar(select(Workspace).where(Workspace.slug == slug))
        if workspace is None:
            raise NotFound("MNX-MATERIALS-0009", f"부서를 찾을 수 없습니다: {slug}")
    else:
        if user.home_workspace_id is None:
            raise AppError(
                "MNX-MATERIALS-0010",
                "소속 부서가 없습니다. 관리자에게 부서 지정을 요청하세요.",
                status=422,
            )
        workspace = db.get(Workspace, user.home_workspace_id)
        if workspace is None:
            raise NotFound("MNX-MATERIALS-0009", "소속 부서를 찾을 수 없습니다.")

    if not user.is_system_admin and workspace.id not in my_workspace_ids(db, user):
        raise Forbidden("MNX-MATERIALS-0011", "이 부서에 등록할 권한이 없습니다.")
    return workspace


# --- 이름 -------------------------------------------------------------------


def material_record_name(
    *, grade: str | None, details: str | None, spec_thickness_m: float | None
) -> str:
    thickness_mm = from_si(spec_thickness_m, "mm")
    return naming.material_name(
        grade=grade,
        details=details,
        thickness_mm=thickness_mm if thickness_mm is not None else "",
    )


def name_taken(
    db: Session,
    *,
    owner_workspace_id: uuid.UUID | None,
    record_name: str,
    exclude_id: uuid.UUID | None = None,
) -> bool:
    query = (
        select(func.count()).select_from(Material).where(Material.record_name == record_name)
    )
    query = (
        query.where(Material.owner_workspace_id.is_(None))
        if owner_workspace_id is None
        else query.where(Material.owner_workspace_id == owner_workspace_id)
    )
    if exclude_id is not None:
        query = query.where(Material.id != exclude_id)
    return bool(db.scalar(query))


def find_by_name(
    db: Session, *, owner_workspace_id: uuid.UUID | None, record_name: str
) -> Material | None:
    """이름으로 살아 있는 재료 하나를 찾는다.

    여러 개를 한꺼번에 넣을 때 쓴다 — 같은 재료 아래에 시료를 여러 벌 넣으려면
    **두 번째 줄부터는 만드는 것이 아니라 찾는 것**이어야 한다. `name_taken` 은
    지운 것까지 세지만(이름은 계속 잡아 둔다) 여기서는 살아 있는 것만 본다.
    """
    query = select(Material).where(
        Material.record_name == record_name, Material.deleted_at.is_(None)
    )
    query = (
        query.where(Material.owner_workspace_id.is_(None))
        if owner_workspace_id is None
        else query.where(Material.owner_workspace_id == owner_workspace_id)
    )
    return db.scalar(query)


def ensure_name_free(
    db: Session,
    *,
    owner_workspace_id: uuid.UUID | None,
    record_name: str,
    exclude_id: uuid.UUID | None = None,
) -> None:
    """DB 제약이 최종 방어선이지만, 여기서 먼저 막아 읽을 수 있는 이유를 준다.

    IntegrityError 를 그대로 흘리면 사용자는 "서버 오류"만 본다.
    """
    if name_taken(
        db,
        owner_workspace_id=owner_workspace_id,
        record_name=record_name,
        exclude_id=exclude_id,
    ):
        raise Conflict(
            "MNX-MATERIALS-0004", f"같은 이름의 재료가 이미 있습니다: {record_name}"
        )


def rename_descendants(db: Session, material: Material) -> None:
    """재료 이름이 바뀌면 하위 이름을 다시 계산한다.

    기존 앱에서는 이것이 불가능했다 — 이름이 곧 참조 키라 바꾸면 계보가 끊어졌다.
    여기서는 참조가 UUID 라 이름은 표시 문자열일 뿐이므로, 다시 계산해서 덮으면
    그만이다. 이 함수가 존재할 수 있다는 것 자체가 ADR 0004 의 결론이다.
    """
    samples = list(db.scalars(select(Sample).where(Sample.material_id == material.id)))
    if not samples:
        return
    for sample in samples:
        sample.record_name = naming.sample_name(
            material=material.record_name, seq_no=sample.seq_no
        )
    by_sample = {sample.id: sample for sample in samples}
    specimens = list(
        db.scalars(select(Specimen).where(Specimen.sample_id.in_(list(by_sample))))
    )
    for specimen in specimens:
        specimen.record_name = naming.specimen_name(
            sample=by_sample[specimen.sample_id].record_name,
            orientation=specimen.orientation,
            seq_no=specimen.seq_no,
        )

    # **시험까지 내려간다.**
    #
    # 여기서 멈춰 있었다 — 재료 이름을 바꾸면 시험만 옛 이름을 달고 있었고,
    # 재료 수정 창은 "시편·시험 이름이 전부 따라 바뀝니다" 라고 **약속하고
    # 있었다.** Grade 기준정보를 붙이면서 실측으로 드러났다.
    by_specimen = {specimen.id: specimen for specimen in specimens}
    if not by_specimen:
        return
    runs = list(db.scalars(select(TestRun).where(TestRun.specimen_id.in_(list(by_specimen)))))
    if not runs:
        return
    # 시험 종류를 건별로 읽지 않는다 — 시험이 수백 건이면 그만큼 왕복한다.
    abbrs = {
        row.id: row.abbr
        for row in db.scalars(
            select(TestType).where(TestType.id.in_({run.test_type_id for run in runs}))
        )
    }
    for run in runs:
        run.record_name = naming.test_run_name(
            specimen=by_specimen[run.specimen_id].record_name,
            type_abbr=abbrs.get(run.test_type_id, "?"),
            seq_no=run.seq_no,
        )


# --- 채번 -------------------------------------------------------------------


def next_sample_seq(db: Session, material_id: uuid.UUID) -> int:
    """재료 단위로 채번한다 — 부서 단위로 하면 전역 재료 밑에서 이름이 겹친다.

    삭제한 시료의 번호는 재사용하지 않는다. 재사용하면 지운 시료와 새 시료가
    같은 이름을 갖게 되어, 옛 문서·엑셀에 적힌 이름이 다른 것을 가리킨다.
    """
    highest = db.scalar(
        select(func.max(Sample.seq_no)).where(Sample.material_id == material_id)
    )
    return (highest or 0) + 1


def next_specimen_seq(db: Session, sample_id: uuid.UUID, orientation: str) -> int:
    highest = db.scalar(
        select(func.max(Specimen.seq_no)).where(
            Specimen.sample_id == sample_id, Specimen.orientation == orientation
        )
    )
    return (highest or 0) + 1


# --- 용도 (적용 제품·부위) --------------------------------------------------


def uses_of(
    db: Session, material_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, dict[str, list[str]]]:
    """재료들의 용도를 **한 번에** 읽는다.

    목록이 재료마다 물으면 N+1 이다. 200건짜리 화면에서 그것이 200번이 된다.
    """
    empty: dict[str, list[str]] = {axis: [] for axis in USE_AXES}
    if not material_ids:
        return {}
    found: dict[uuid.UUID, dict[str, list[str]]] = {}
    rows = db.scalars(
        select(MaterialUse)
        .where(MaterialUse.material_id.in_(material_ids))
        .order_by(MaterialUse.axis, MaterialUse.position, MaterialUse.value)
    )
    for row in rows:
        found.setdefault(row.material_id, {axis: [] for axis in USE_AXES})
        found[row.material_id].setdefault(row.axis, []).append(row.value)
    return {mid: found.get(mid, dict(empty)) for mid in material_ids}


def set_uses(
    db: Session,
    material: Material,
    axis: str,
    values: Sequence[str],
    *,
    created_by_id: uuid.UUID | None = None,
) -> None:
    """한 축의 용도를 **통째로 갈아 끼운다.**

    줄 하나를 지운 것과 안 보낸 것을 구별할 방법이 없어서다 — 선언 물성과 같은
    규칙이다. 안 보내면 이 함수를 아예 안 부른다.

    기준정보를 거친다(ADR 0010). 값마다 용어를 찾거나 만들고 `usage_count` 를
    옮긴다 — **여기서 안 옮기면** 피커에 「쓰이지 않는 값」 이 남고 관리 화면의
    「쓰는 곳」 이 거짓말을 한다.
    """
    if axis not in USE_AXES:
        raise AppError("MNX-MATERIALS-0014", f"모르는 용도 축입니다: {axis}", status=422)

    before = list(
        db.scalars(
            select(MaterialUse).where(
                MaterialUse.material_id == material.id, MaterialUse.axis == axis
            )
        )
    )
    for row in before:
        vocabulary_services.bump_usage(db, row.term_id, -1)
        db.delete(row)
    # 지운 줄이 아직 세션에 남아 있으면 유일 제약에 걸린다 — 같은 값을 다시
    # 넣는 것이 가장 흔한 경우다(하나만 더 붙이는 수정).
    db.flush()

    vocabulary = vocabulary_services.get_vocabulary(db, axis)
    seen: set[uuid.UUID] = set()
    for position, raw in enumerate(values):
        term = vocabulary_services.resolve_or_create(
            db, vocabulary, raw, created_by_id=created_by_id
        )
        if term is None or term.id in seen:
            # 빈 값과 **같은 값 두 번**은 넘긴다. 목록에 같은 칩이 둘 보이면
            # 사람은 둘 중 하나가 다른 뜻이라고 읽는다.
            continue
        seen.add(term.id)
        db.add(
            MaterialUse(
                material_id=material.id,
                axis=axis,
                term_id=term.id,
                value=term.value,
                position=position,
            )
        )
        vocabulary_services.bump_usage(db, term.id, 1)
    db.flush()


def release_uses(db: Session, material: Material) -> None:
    """재료가 사라질 때 용도의 `usage_count` 를 되돌린다.

    줄은 남긴다 — 재료가 소프트 삭제라 되살릴 수 있어야 하고, 세는 쪽은 이미
    지워진 재료를 빼고 센다(`vocabulary._COUNT_SOURCES`).
    """
    for row in db.scalars(select(MaterialUse).where(MaterialUse.material_id == material.id)):
        vocabulary_services.bump_usage(db, row.term_id, -1)


def registrant_names(rows: Sequence[Any], db: Session) -> dict[uuid.UUID | None, str]:
    """등록한 사람의 이름을 **한 번에** 읽는다.

    줄마다 `db.get(User, ...)` 하면 시편 20개짜리 화면에 쿼리가 20개 붙는다.
    """
    ids = {row.registered_by_id for row in rows if row.registered_by_id}
    if not ids:
        return {}
    # 열쇠를 `None` 까지 받는 형태로 둔다 — 부르는 쪽이 매번 `if` 를 쓰면
    # 어딘가 한 곳이 빠지고, 그 자리만 조용히 이름이 안 나온다.
    found: dict[uuid.UUID | None, str] = {}
    for user_id, name in db.execute(
        select(User.id, User.display_name).where(User.id.in_(ids))
    ).all():
        found[user_id] = name
    return found


# --- 개수 (N+1 방지) --------------------------------------------------------


def sample_counts(db: Session, material_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not material_ids:
        return {}
    rows = db.execute(
        select(Sample.material_id, func.count())
        .where(Sample.material_id.in_(list(material_ids)), Sample.deleted_at.is_(None))
        .group_by(Sample.material_id)
    )
    return {material_id: count for material_id, count in rows}


def specimen_counts(db: Session, sample_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not sample_ids:
        return {}
    rows = db.execute(
        select(Specimen.sample_id, func.count())
        .where(Specimen.sample_id.in_(list(sample_ids)), Specimen.deleted_at.is_(None))
        .group_by(Specimen.sample_id)
    )
    return {sample_id: count for sample_id, count in rows}


# --- 사슬 삭제 --------------------------------------------------------------


@dataclass(frozen=True)
class DeletePlan:
    """이 재료를 지우면 **무엇이 함께 사라지는가.**

    화면이 세지 않게 하려고 서버가 낸다 — 화면이 자기 나름대로 세면 사람이 본
    숫자와 실제로 지워지는 것이 어긋난다. 그리고 이 숫자는 사람이 「예」 를 누를
    근거이므로, 어긋나면 그 「예」 는 다른 것에 대한 대답이 된다.
    """

    samples: int
    specimens: int
    test_runs: int

    @property
    def empty(self) -> bool:
        return not (self.samples or self.specimens or self.test_runs)

    @property
    def said(self) -> str:
        """사람이 읽는 한 줄. 0인 층은 뺀다."""
        parts = [
            f"{label} {count}건"
            for label, count in (
                ("시료", self.samples),
                ("시편", self.specimens),
                ("시험", self.test_runs),
            )
            if count
        ]
        return " · ".join(parts) or "없음"


def deletable_tree(
    db: Session, material: Material
) -> tuple[list[Sample], list[Specimen], list[TestRun]]:
    """이 재료에 매달린 **살아 있는** 행들. 지워진 것은 다시 안 지운다."""
    samples = list(
        db.scalars(
            select(Sample).where(
                Sample.material_id == material.id, Sample.deleted_at.is_(None)
            )
        )
    )
    if not samples:
        return [], [], []
    sample_ids = [one.id for one in samples]
    specimens = list(
        db.scalars(
            select(Specimen).where(
                Specimen.sample_id.in_(sample_ids), Specimen.deleted_at.is_(None)
            )
        )
    )
    if not specimens:
        return samples, [], []
    specimen_ids = [one.id for one in specimens]
    runs = list(
        db.scalars(
            select(TestRun).where(
                TestRun.specimen_id.in_(specimen_ids), TestRun.deleted_at.is_(None)
            )
        )
    )
    return samples, specimens, runs


def delete_plan(db: Session, material: Material) -> DeletePlan:
    """지우기 전에 보여 줄 숫자."""
    samples, specimens, runs = deletable_tree(db, material)
    return DeletePlan(samples=len(samples), specimens=len(specimens), test_runs=len(runs))


def workspace_names(db: Session, ids: Sequence[uuid.UUID | None]) -> dict[uuid.UUID, str]:
    wanted = [i for i in ids if i is not None]
    if not wanted:
        return {}
    rows = db.execute(select(Workspace.id, Workspace.name).where(Workspace.id.in_(wanted)))
    return {workspace_id: name for workspace_id, name in rows}


def rename_materials_of_grade(db: Session, term_id: uuid.UUID) -> None:
    """Grade 값 이름이 바뀌면 그 Grade 를 쓰는 재료 이름을 다시 만든다.

    Grade 는 재료 이름을 만든다(ADR 0004). 문자열만 맞추면 이름이 옛 Grade 를 그대로
    달고 있게 된다 — `SECC_-_1.0` 인데 Grade 는 `SPCC` 인 상태.

    **이름이 겹치면 그 재료만 건너뛴다.** `SECC_-_1.0` 과 `SPCC_-_1.0` 이 있는데
    `SPCC` 를 `SECC` 로 고치면 둘이 같은 이름이 된다 — 유니크 제약에 걸려 요청
    전체가 실패하는 것보다, 옮길 수 있는 것을 옮기고 못 옮긴 것을 로그로 말하는
    편이 낫다. 그런 상황이면 애초에 값을 병합해야 한다.
    """
    materials = list(
        db.scalars(
            select(Material).where(
                Material.grade_term_id == term_id, Material.deleted_at.is_(None)
            )
        )
    )
    for material in materials:
        renamed = material_record_name(
            grade=material.grade,
            details=material.details,
            spec_thickness_m=material.spec_thickness_m,
        )
        if renamed == material.record_name:
            continue
        if name_taken(
            db,
            owner_workspace_id=material.owner_workspace_id,
            record_name=renamed,
            exclude_id=material.id,
        ):
            logger.warning(
                "재료 %r 의 이름을 %r 로 못 바꿨습니다 — 같은 이름이 이미 있습니다. "
                "합치려면 기준정보 병합을 쓰세요.",
                material.record_name,
                renamed,
            )
            continue
        material.record_name = renamed
        rename_descendants(db, material)


vocabulary_hooks.on_rename("grade", rename_materials_of_grade)
