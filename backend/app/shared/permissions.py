"""권한 판정.

**가시성·수정 권한을 각 쿼리에 흩뿌리지 않고 여기서만 판정한다.** 65가 RLS로
DB에 강제를 걸어 얻은 이점이 "앱에 버그가 있어도 데이터가 새지 않는다"였는데,
우리는 아직 앱 레벨이므로 최소한 판정 지점이라도 하나여야 한다. 나중에 RLS를
도입할 때도 이 함수들이 정책의 대응물이 된다(개발계획 §10).

## 보기는 전원이다 (ADR 0035)

자료(재료·시료·시편·시험과 그 아래)와 정의(시험 종류·장비 파일 정의·레시피·해석용
물성 정의)는 **로그인한 사람이면 전부 본다.** 부서가 가리는 손잡이(`restricted`)도
걷었다. 전에는 「누가 무엇을 보나」 가 자료 종류마다 달라서, 자료는 보이는데 그
정의는 안 보이는 일이 생겼고 — 다른 시스템이 물성을 받아 가다 「정의가 없다」 로
막혔다 — 잠긴 이유를 사람이 알아낼 길이 없었다.

측정 의뢰·장비 커넥터·워크벤치 작업도 이제 전원이 본다(3단계). 셋은 보기와 고치기가
한 판정에 묶여 있어서 보기만 먼저 열 수 없었다 — 둘을 떼고 나서 열었다. 작성 중인
의뢰만 낸 사람의 것이다. 남는 예외는 감사 기록뿐이다.

## 고치기는 사람 기준이다 (ADR 0035 D4)

자료를 고치는 사람은 넷이다 — 시스템 관리자 · 자료 관리자 · 그 자료의 등록자 · 그
자료에 편집을 받은 부서의 멤버(`require_edit`). 소속 부서는 권한을 정하지 않는다.
정의(시험 종류·장비 파일 정의·레시피·해석용 물성 정의)와 장비도 같다(3단계).

역할은 사람에게 붙는다.
  - `is_system_admin` : 전사. 계정·부서 자체를 만들고 지운다
  - `is_data_manager` : 전사. 모든 자료를 고치고, 검토의 뜻이 있는 일을 한다 — 카드
                        확정 · 새 기준정보 값 · 핸드북 승인. 계정·서버는 못 만진다
  - 부서 `manager`    : 그 부서 안에서만. 멤버 · 장비 커넥터와 수신함 · 의뢰 알림

**업무 흐름은 권한이 아니라 역할이다.** 의뢰를 움직이는 것(낸 쪽 / 받는 쪽)과
수신함을 처리하는 것(커넥터의 부서)은 「고치기」 가 아니라 「일을 넘기기」 라서 위
판정을 따르지 않는다 — 각 모듈이 제 흐름대로 본다.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import ColumnElement, Select, or_, select
from sqlalchemy.orm import Session

from app.modules.accounts.models import User
from app.modules.commissions.models import Commission
from app.modules.equipment.models import EquipmentUnit
from app.modules.fitting.models import ExportProfile, PropertyCard
from app.modules.grouping.models import GroupResult
from app.modules.materials.models import Material, Sample, Specimen
from app.modules.pipelines.models import PipelineConnector
from app.modules.processing.models import ProcessingRecipe, ProcessingResult
from app.modules.tests.models import FormatProfile, TestRun, TestType
from app.modules.workbench.models import WorkbenchRun
from app.modules.workspaces.models import Workspace, WorkspaceMember
from app.shared import audit
from app.shared.errors import AppError, Forbidden, NotFound


def workspace_by_slug(db: Session, slug: str) -> Workspace:
    workspace = db.scalar(select(Workspace).where(Workspace.slug == slug))
    if workspace is None:
        raise NotFound("MNX-WORKSPACES-0001", f"부서를 찾을 수 없습니다: {slug}")
    return workspace


def membership_of(
    db: Session, *, workspace_id: uuid.UUID, user_id: uuid.UUID
) -> WorkspaceMember | None:
    return db.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
        )
    )


def require_member(db: Session, *, workspace: Workspace, user: User) -> None:
    """그 부서를 볼 수 있는가. 시스템 관리자는 모든 부서를 본다."""
    if user.is_system_admin:
        return
    if membership_of(db, workspace_id=workspace.id, user_id=user.id) is None:
        raise Forbidden("MNX-WORKSPACES-0002", "이 부서에 접근할 권한이 없습니다.")


def require_manager(db: Session, *, workspace: Workspace, user: User) -> None:
    """그 부서의 멤버·역할을 바꿀 수 있는가."""
    if user.is_system_admin:
        return
    membership = membership_of(db, workspace_id=workspace.id, user_id=user.id)
    if membership is None or membership.role != "manager":
        raise Forbidden("MNX-WORKSPACES-0003", "부서 관리자만 할 수 있습니다.")


# --- 정의의 등록 부서 --------------------------------------------------------
#
# 정의(시험 종류·장비 파일 정의·레시피·해석용 물성 정의)는 **등록한 부서**를 적는다.
# 권한이 아니다 — 고치는 사람은 `require_edit` 이 정한다(ADR 0035 3단계). 전에는 이
# 칸이 「전역이면 시스템 관리자, 부서 것이면 그 부서 관리자」 로 권한을 정했고, 「전역」
# 이라는 말은 다른 시스템이 「공식」 으로 읽었다.
#
# 남은 뜻은 하나다: **장비 파일을 자동으로 고를 때의 후보**(내 부서 것 + 부서 없는 것,
# `tests.formats.auto_profiles`). 그래서 부서 없이 올리는 것만 관리자가 한다.


def registering_workspace(
    db: Session, user: User, slug: str | None, *, given: bool, what: str, code: str
) -> uuid.UUID | None:
    """새 정의의 등록 부서.

        안 보냄      내 소속 부서(관리자는 소속이 없으면 부서 없이)
        부서         내가 속한 부서여야 한다 — 관리자는 아무 부서
        비워서 보냄  부서 없이 — **관리자만**

    **안 보낸 것과 비운 것을 가른다**(AGENTS.md). 부서 없는 장비 파일 정의는 모든
    부서의 자동 추정에 들어간다 — 한 사람이 모두의 파일 읽기를 바꾸는 자리라서,
    화면이 칸을 안 보냈다고 그렇게 되면 안 된다.
    """
    steward = is_data_steward(user)
    if not given:
        if user.home_workspace_id is not None:
            return user.home_workspace_id
        if steward:
            return None
        raise AppError(
            code, "소속 부서가 없습니다 — 관리자에게 부서 지정을 요청하세요.", status=422
        )
    if slug is None:
        if steward:
            return None
        raise Forbidden(
            code,
            f"부서 없이 올리는 {what}은 자료 관리자만 만들 수 있습니다. 내 부서를 고르세요.",
        )
    workspace = workspace_by_slug(db, slug)
    if not steward and workspace.id not in my_workspace_ids(db, user):
        raise Forbidden(code, f"{workspace.name}에 속하지 않아 그 부서로 올릴 수 없습니다.")
    return workspace.id


def is_any_manager(db: Session, user: User) -> bool:
    """어느 부서든 관리자인가 — **부서 일을 알릴지**만 정한다(수신함·의뢰 알림).

    고칠 권한의 근거로 쓰지 않는다(ADR 0035). 전에는 장비·새 기준정보 값·핸드북
    승인이 「어느 부서든 관리자면」 이었는데, 그래서 남의 조직 장비를 누구 관리자든
    고쳤다.
    """
    if user.is_system_admin:
        return True
    return (
        db.scalar(
            select(WorkspaceMember.id).where(
                WorkspaceMember.user_id == user.id, WorkspaceMember.role == "manager"
            )
        )
        is not None
    )


def managed_workspace_ids(db: Session, user: User) -> list[uuid.UUID]:
    """내가 관리자인 부서들 — 커넥터·수신함을 다룰 자리를 가른다."""
    return list(
        db.scalars(
            select(WorkspaceMember.workspace_id).where(
                WorkspaceMember.user_id == user.id, WorkspaceMember.role == "manager"
            )
        )
    )


# --- 재료 계층의 가시 범위 --------------------------------------------------
#
# **여기 있는 이유가 있다.** 재료·시료·시편·시험이 전부 같은 규칙을 따라야 하는데,
# 각 모듈이 자기 버전을 갖고 있으면 "재료는 보이는데 그 시험은 안 보인다" 같은
# 어긋남이 생긴다. 모듈끼리 직접 부르는 것은 경계 규칙이 막으므로(CLAUDE.md),
# 공유해야 하는 판정은 shared 에 둔다.


def my_workspace_ids(db: Session, user: User) -> list[uuid.UUID]:
    return list(
        db.scalars(
            select(WorkspaceMember.workspace_id).where(WorkspaceMember.user_id == user.id)
        )
    )


def visible_materials(db: Session, user: User) -> Select[tuple[Material]]:
    """볼 수 있는 재료 — **살아 있는 것 전부**(ADR 0035).

    전에는 「전역 + 열린 부서 + 내 부서」 였다. 부서가 `restricted` 를 켜면 멤버로
    좁혔는데, 그 손잡이가 켜졌는지는 막힌 사람 쪽에서 보이지 않았다 — 「없다」 와
    「가려졌다」 가 같은 모양이었다. 물성은 사업부 간 공유가 목적인 데이터다.

    `user` 를 받는 것은 판정 자리를 여기 하나로 두려는 것이다 — 규칙이 다시 사람에
    따라 달라지면 부르는 쪽 수십 곳을 안 고치고 여기만 고친다.
    """
    del user
    return select(Material).where(Material.deleted_at.is_(None))


def visible_commissions(db: Session, user: User) -> Select[tuple[Commission]]:
    """측정 의뢰 — **낸 것은 전원이 본다.** 작성 중인 것은 낸 사람만(시스템 관리자는 전부).

    전에는 낸 부서·받는 부서 멤버만 봤다 — 두 부서 사이의 약속이라 제3부서가 볼 것이
    아니라는 판단이었다. 그런데 그 판정이 **움직이는 권한과 한 함수**였고, 그래서 「이
    시료를 누가 재 달라고 했나」 를 옆 부서가 물을 길이 없었다(ADR 0035 3단계). 움직이는
    것은 여전히 낸 쪽·받는 쪽이다(`commissions.services.side_of`).

    의뢰 목록·그래프·홈 요약이 **같은 규칙**을 쓰려고 여기 둔다(2026-09-16) — 두 벌이면
    「홈에는 세는데 목록엔 없다」 가 생긴다.
    """
    del db
    query = select(Commission)
    if user.is_system_admin:
        return query
    return query.where(or_(Commission.status != "draft", Commission.created_by_id == user.id))


def visible_material_ids(db: Session, user: User) -> Select[tuple[uuid.UUID]]:
    """하위 계층 쿼리에 끼워 넣을 서브쿼리. `visible_materials` 와 **같은 조건**이다."""
    del user
    return select(Material.id).where(Material.deleted_at.is_(None))


def visible_specimen(db: Session, user: User, specimen_id: uuid.UUID) -> Specimen:
    """볼 수 있는 시편 하나. 재료의 가시 범위를 그대로 따라간다."""
    specimen = db.scalar(
        select(Specimen)
        .join(Sample, Sample.id == Specimen.sample_id)
        .where(
            Specimen.id == specimen_id,
            Specimen.deleted_at.is_(None),
            Sample.deleted_at.is_(None),
            Sample.material_id.in_(visible_material_ids(db, user)),
        )
    )
    if specimen is None:
        raise NotFound("MNX-MATERIALS-0003", "시편을 찾을 수 없습니다.")
    return specimen


def visible_connectors(db: Session, user: User) -> Select[tuple[PipelineConnector]]:
    """장비 커넥터 — **전원이 본다**(ADR 0035 3단계). 지운 것은 뺀다.

    전에는 내가 속한 부서의 것만 보였다. 그 판정이 다루는 권한과 한 자리여서, 「내
    파일이 왜 안 들어왔나」 를 옆 부서 장비에 대해 물을 수 없었다. 다루는 것(설정·
    수신함 처리)은 여전히 **그 커넥터 부서의 관리자**다(`pipelines.routes`).

    **여기 있는 이유:** 커넥터 화면(`pipelines`)과 홈 요약(`statistics`)이 둘 다
    이 규칙을 쓴다. 모듈끼리 직접 부르지 않으므로(AGENTS.md) 한쪽이 베끼면 규칙이
    둘이 되고, 그러면 **홈의 숫자와 커넥터 화면의 숫자가 갈린다.** 홈의 「수신함
    대기」 는 이 위에서 **내가 다룰 부서**로 다시 좁힌다 — 할 일을 세는 자리라서다.
    """
    del db, user
    return select(PipelineConnector).where(PipelineConnector.deleted_at.is_(None))


def visible_runs(db: Session, user: User) -> Select[tuple[TestRun]]:
    """시험의 가시 범위는 **재료를 따라간다.**

    시험에 별도의 공개 규칙을 두지 않는 이유: 규칙이 둘이 되면 "재료는 보이는데
    그 시험은 안 보인다" 또는 그 반대가 생기고, 어느 쪽이 맞는지 그때그때
    판단해야 한다.

    **여기 있는 이유:** 시험 모듈만 쓰던 것인데 처리가 같은 것을 필요로 하고,
    통계·적합·내보내기도 곧 그렇다. 모듈마다 자기 버전을 갖게 두면 판정이 갈린다.
    """
    query = select(TestRun).where(TestRun.deleted_at.is_(None))
    if user.is_system_admin:
        return query
    return query.where(
        TestRun.specimen_id.in_(
            select(Specimen.id)
            .join(Sample, Sample.id == Specimen.sample_id)
            .where(Sample.material_id.in_(visible_material_ids(db, user)))
        )
    )


def get_run(db: Session, user: User, run_id: uuid.UUID) -> TestRun:
    run = db.scalar(visible_runs(db, user).where(TestRun.id == run_id))
    if run is None:
        raise NotFound("MNX-TESTS-0001", "시험을 찾을 수 없습니다.")
    return run


# --- 고치기 — 사람 기준 (ADR 0035 D4) ----------------------------------------
#
# **판정은 하나다.** 시스템 관리자 · 자료 관리자 · 그 자료의 등록자 · 그 자료에 편집을
# 받은 부서의 멤버. 층마다 제 등록자가 있다 — 시료·시편·시험은 재료의 권한에 딸려
# 가지 않는다. 딸려 가면 SECC 를 처음 올린 사람만 그 아래를 고친다.
#
# 모듈은 등록자·부서를 직접 견주지 않고 여기를 부른다(`tests/architecture` 가 본다).
# 전에는 모듈마다 다섯 갈래로 판정했고, 그래서 같은 재료에서 필드는 고쳐지는데 문헌
# 연결은 막혔다 — 사람은 그 차이를 설명할 길이 없었다.

#: 고칠 권한이 붙는 것 — 자료, 정의(3단계), 장비(3단계), 워크벤치 작업(3단계).
Owned = (
    Material
    | Sample
    | Specimen
    | TestRun
    | PropertyCard
    | GroupResult
    | TestType
    | FormatProfile
    | ProcessingRecipe
    | ExportProfile
    | EquipmentUnit
    | WorkbenchRun
)

#: 등록자 칸 이름 — 표마다 셋으로 갈려 있다. 그 차이는 `owner_of` 한 곳이 흡수한다.
_REGISTRANT: dict[type, str] = {
    Material: "registered_by_id",
    Sample: "registered_by_id",
    Specimen: "registered_by_id",
    TestRun: "registered_by_id",
    EquipmentUnit: "registered_by_id",
    PropertyCard: "created_by_id",
    GroupResult: "created_by_id",
    TestType: "created_by_id",
    FormatProfile: "created_by_id",
    ProcessingRecipe: "created_by_id",
    ExportProfile: "created_by_id",
    # 워크벤치 작업은 「시작한 사람」 이다.
    WorkbenchRun: "owner_id",
}

#: 편집을 받은 부서의 칸. **워크벤치 작업만 제 부서가 곧 편집 부서다** — 부서 안에서
#: 함께 미는 것이 그 표의 뜻이다(ADR 0025). 나머지는 등록자가 보이게 준 부서다.
_EDIT_SPACE: dict[type, str] = {WorkbenchRun: "workspace_id"}

#: 막혔을 때 「무엇이」 — 조사까지 붙여 둔다.
_SUBJECT: dict[type, str] = {
    Material: "이 재료는",
    Sample: "이 시료는",
    Specimen: "이 시편은",
    TestRun: "이 시험은",
    PropertyCard: "이 카드는",
    GroupResult: "이 묶음은",
    TestType: "이 시험 정의는",
    FormatProfile: "이 장비 파일 정의는",
    ProcessingRecipe: "이 레시피는",
    ExportProfile: "이 해석용 물성 정의는",
    EquipmentUnit: "이 장비는",
    WorkbenchRun: "이 작업은",
}


def is_data_steward(user: User) -> bool:
    """전사로 자료를 고치는 사람 — 시스템 관리자와 자료 관리자."""
    return user.is_system_admin or user.is_data_manager


def owner_of(row: Owned) -> tuple[uuid.UUID | None, uuid.UUID | None]:
    """(등록자, 편집을 받은 부서)."""
    kind = type(row)
    registrant: uuid.UUID | None = getattr(row, _REGISTRANT[kind])
    workspace: uuid.UUID | None = getattr(row, _EDIT_SPACE.get(kind, "edit_workspace_id"))
    return registrant, workspace


def registrant_of(db: Session, table: str, target_id: uuid.UUID) -> uuid.UUID | None:
    """표 이름과 id 로 **그 행의 등록자** — 감사가 「누구의 자료인가」 를 채울 때 묻는다.

    처리 결과는 제 등록자가 없다 — 그 결과를 낸 **시험의 등록자**다. 표가 여기 없거나 행이
    없으면 `None`(계정·부서처럼 누구의 자료도 아닌 일)."""
    if table == ProcessingResult.__tablename__:
        result = db.get(ProcessingResult, target_id)
        run = db.get(TestRun, result.test_run_id) if result is not None else None
        return run.registered_by_id if run is not None else None
    for model, column in _REGISTRANT.items():
        if getattr(model, "__tablename__", None) == table:
            row = db.get(model, target_id)
            return getattr(row, column) if row is not None else None
    return None


def set_registrant(row: Owned, user_id: uuid.UUID) -> None:
    """등록자를 바꾼다 — 칸 이름이 갈린 것을 `owner_of` 와 같은 자리에서 흡수한다."""
    setattr(row, _REGISTRANT[type(row)], user_id)


def set_edit_workspace(row: Owned, workspace_id: uuid.UUID | None) -> None:
    """편집을 받은 부서를 바꾼다 — 칸 이름을 `owner_of` 와 같은 표에서 읽는다."""
    setattr(row, _EDIT_SPACE.get(type(row), "edit_workspace_id"), workspace_id)


def editable_clause(db: Session, user: User, model: type) -> ColumnElement[bool] | None:
    """`Editor.allows` 와 **같은 뜻의 SQL 조건** — 행을 다 읽지 않고 거를 때(휴지통).

    `None` 이면 전부다(관리자). 판정이 둘이 되면 목록과 단추가 다른 말을 한다 — 그래서
    칸 이름은 `owner_of` 와 같은 표(`_REGISTRANT`·`_EDIT_SPACE`)에서 읽는다.
    """
    if is_data_steward(user):
        return None
    registrant = getattr(model, _REGISTRANT[model])
    space = getattr(model, _EDIT_SPACE.get(model, "edit_workspace_id"))
    return or_(registrant == user.id, space.in_(my_workspace_ids(db, user)))


@dataclass(frozen=True)
class Editor:
    """한 사람이 무엇을 고칠 수 있나. **목록이 여러 행에 물을 때 한 번만 읽는다.**"""

    user_id: uuid.UUID
    steward: bool
    workspaces: frozenset[uuid.UUID]

    def allows(self, row: Owned) -> bool:
        if self.steward:
            return True
        registrant, workspace = owner_of(row)
        if registrant is not None and registrant == self.user_id:
            return True
        return workspace is not None and workspace in self.workspaces

    def can_hand_over(self, row: Owned) -> bool:
        """등록자·편집 부서를 바꿀 수 있나 — **등록자와 관리자만.**

        편집을 받은 부서 사람은 고칠 수는 있어도 권한을 옮기지는 못한다. 옮기게 두면
        받은 권한으로 등록자의 권한을 걷는 길이 된다.
        """
        if self.steward:
            return True
        registrant, _ = owner_of(row)
        return registrant is not None and registrant == self.user_id


def editor(db: Session, user: User) -> Editor:
    return Editor(
        user_id=user.id,
        steward=is_data_steward(user),
        workspaces=frozenset(my_workspace_ids(db, user)),
    )


def locked_reason(*, registrant: str | None, workspace: str | None) -> str:
    """못 고칠 때 할 말 — **누구에게 물으면 되는지** 이름으로 적는다.

    「권한이 없습니다」 만 적으면 사람은 누구를 찾아가야 할지 모른다. 전에는 그것이
    소속 때문에 잠긴 것인지조차 알 수 없었다(ADR 0035 배경).
    """
    who = []
    if registrant:
        who.append(f"등록자 {registrant}")
    if workspace:
        who.append(f"{workspace} 사람")
    who.append("자료 관리자")
    return " · ".join(who) + "만 고칠 수 있습니다."


def data_steward_names(db: Session) -> list[str]:
    """물어볼 사람들. 자료 관리자가 없으면 시스템 관리자를 댄다 — 빈 목록은 답이 아니다."""
    active = (User.deleted_at.is_(None), User.status == "active")
    names = list(
        db.scalars(
            select(User.display_name)
            .where(User.is_data_manager.is_(True), *active)
            .order_by(User.display_name)
        )
    )
    if names:
        return names
    return list(
        db.scalars(
            select(User.display_name)
            .where(User.is_system_admin.is_(True), *active)
            .order_by(User.display_name)
        )
    )


def require_edit(db: Session, user: User, row: Owned, *, code: str) -> None:
    """고칠 수 있는가. **자료를 고치는 길은 전부 여기를 지난다**(ADR 0035).

    막히면 누가 고칠 수 있는지를 **이름으로** 함께 낸다 — 등록자, 편집을 받은 부서,
    자료 관리자. 화면은 같은 말을 단추 옆에 미리 보인다(`shared/access`).
    """
    if editor(db, user).allows(row):
        _note_edit(db, user, row)
        return
    raise locked(db, row, code=code)


def admits(db: Session, user: User, judge: Editor, row: Owned) -> bool:
    """`Editor.allows` 에 **쓰기의 흔적**을 더한 것 — 일괄 쓰기가 줄마다 부른다.

    일괄 수정은 막힌 줄을 모아 알려 주느라 `require_edit`(막히면 멈춘다) 대신 판정을 직접
    묻는다. 그 길로 고친 남의 자료도 `require_edit` 로 고친 것과 같이 남아야 한다 — 안 그러면
    자료 관리자가 일괄로 고친 것만 등록자에게 안 보인다."""
    if not judge.allows(row):
        return False
    _note_edit(db, user, row)
    return True


def _note_edit(db: Session, user: User, row: Owned) -> None:
    """**남의 자료를 고치면 남긴다**(2026-09-25, ADR 0035 남은 것).

    고칠 권한이 등록자 밖으로 넓어진 대가다 — 자료 관리자와 편집을 받은 부서가 고칠 수
    있게 되자, 등록자는 제 자료에 누가 손댔는지 볼 길이 없었다. 판정이 한 곳이라 여기서
    남기면 새 쓰기 길이 생겨도 빠지지 않는다. **근거를 함께 적는다** — 등록자가 「왜 저
    사람이 고칠 수 있었나」 를 다시 묻지 않게.

    남기지 않는 것: 제 자료 · 등록자가 없는 자료(물을 사람이 없다) · 워크벤치 작업(부서 안에서
    함께 미는 것이 그 표의 뜻이다, ADR 0025)."""
    if isinstance(row, WorkbenchRun):
        return
    registrant, workspace_id = owner_of(row)
    if registrant is None or registrant == user.id:
        return
    if user.is_system_admin:
        basis = "시스템 관리자"
    elif user.is_data_manager:
        basis = "자료 관리자"
    else:
        workspace = db.get(Workspace, workspace_id) if workspace_id else None
        basis = f"편집을 받은 부서({workspace.name if workspace else '?'})"
    audit.record_edit_by_other(db, user, row, registrant_id=registrant, basis=basis)


def locked(db: Session, row: Owned, *, code: str) -> Forbidden:
    """막혔을 때의 오류 — 일괄 처리가 건별 사유로도 쓴다."""
    registrant_id, workspace_id = owner_of(row)
    registrant = db.get(User, registrant_id) if registrant_id else None
    workspace = db.get(Workspace, workspace_id) if workspace_id else None
    reason = locked_reason(
        registrant=registrant.display_name if registrant else None,
        workspace=workspace.name if workspace else None,
    )
    return Forbidden(
        code,
        f"{_SUBJECT[type(row)]} {reason}",
        details={
            "registrant": registrant.display_name if registrant else None,
            "edit_workspace": workspace.name if workspace else None,
            "data_managers": data_steward_names(db),
        },
    )


def require_hand_over(db: Session, user: User, row: Owned, *, code: str) -> None:
    """등록자·편집 부서를 바꿀 수 있나 — **등록자와 관리자만**(`Editor.can_hand_over`)."""
    if editor(db, user).can_hand_over(row):
        return
    registrant_id, _ = owner_of(row)
    registrant = db.get(User, registrant_id) if registrant_id else None
    who = f"등록자 {registrant.display_name} · " if registrant else ""
    raise Forbidden(
        code,
        f"{_SUBJECT[type(row)]} {who}자료 관리자만 넘길 수 있습니다. "
        "편집을 받은 부서 사람은 고칠 수는 있어도 권한을 옮기지는 못합니다.",
        details={
            "registrant": registrant.display_name if registrant else None,
            "data_managers": data_steward_names(db),
        },
    )


def require_steward(user: User, *, code: str, what: str) -> None:
    """관리자만 하는 일 — 카드 확정처럼 **검토의 뜻이 있는 것**(ADR 0035 D4)."""
    if is_data_steward(user):
        return
    raise Forbidden(code, f"{what}은 자료 관리자만 할 수 있습니다.")
