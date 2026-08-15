"""재료·시료·시편 로직 — 단위 변환, 이름 생성, 채번, 가시 범위.

라우트에서 이것들을 하지 않는 이유가 두 가지다. 하나는 **이름을 만드는 곳이
하나여야** 하기 때문이고(기존 앱은 화면이 만들어서 서버·배치가 같은 이름을 만들
수 없었다), 다른 하나는 가시 범위 판정이 흩어지면 "이 목록에만 전역 재료가 안
보인다" 같은 어긋남이 생기기 때문이다.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.modules.accounts.models import User
from app.modules.materials.models import Material, Sample, Specimen
from app.modules.workspaces.models import Workspace, WorkspaceMember
from app.shared.errors import AppError, Conflict, Forbidden, NotFound
from matcore import naming, units

# --- 단위 -------------------------------------------------------------------


def to_si(value: float | None, unit: str, *, field: str) -> float | None:
    """사람 단위 → 저장 단위. 모르는 단위는 **거부한다.**

    조용히 계수 1로 통과시키면 잘못된 값이 SI 인 척 저장되고, 나중에 어느 행이
    틀렸는지 알아낼 방법이 없다.
    """
    if value is None:
        return None
    try:
        return units.to_si(value, unit)
    except units.UnknownUnit as exc:
        raise AppError(
            "MNX-MATERIALS-0005",
            f"{field} 의 단위를 알 수 없습니다: {exc.symbol}",
            status=422,
        ) from exc


def from_si(value: float | None, unit: str) -> float | None:
    return None if value is None else units.from_si(value, unit)


# --- 가시 범위 --------------------------------------------------------------


def my_workspace_ids(db: Session, user: User) -> list[uuid.UUID]:
    return list(
        db.scalars(
            select(WorkspaceMember.workspace_id).where(WorkspaceMember.user_id == user.id)
        )
    )


def visible_materials(db: Session, user: User) -> Select[tuple[Material]]:
    """내 부서 재료 + 전역 재료.

    전역(NULL)을 처음부터 함께 보게 짜는 것이 ADR 0004 가 지금 요구하는 둘 중
    하나다. 나중에 붙이면 모든 목록·상세·검색 쿼리를 다시 손봐야 한다.
    """
    query = select(Material).where(Material.deleted_at.is_(None))
    if user.is_system_admin:
        return query
    mine = my_workspace_ids(db, user)
    return query.where(
        or_(Material.owner_workspace_id.is_(None), Material.owner_workspace_id.in_(mine))
    )


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
    specimens = db.scalars(select(Specimen).where(Specimen.sample_id.in_(list(by_sample))))
    for specimen in specimens:
        specimen.record_name = naming.specimen_name(
            sample=by_sample[specimen.sample_id].record_name,
            orientation=specimen.orientation,
            seq_no=specimen.seq_no,
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


def workspace_names(db: Session, ids: Sequence[uuid.UUID | None]) -> dict[uuid.UUID, str]:
    wanted = [i for i in ids if i is not None]
    if not wanted:
        return {}
    rows = db.execute(select(Workspace.id, Workspace.name).where(Workspace.id.in_(wanted)))
    return {workspace_id: name for workspace_id, name in rows}
