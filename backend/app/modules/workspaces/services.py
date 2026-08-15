"""부서 로직 — 생성·보관, 멤버와 역할.

**부서를 지우지 않는다.** `is_active=false` 로 보관만 한다. 부서에는 시험 데이터가
매달리게 되고(Phase 2), 무엇이 그 부서를 참조하는지 답할 수 있게 된 뒤에야
삭제를 논할 수 있다(의존성 레지스트리, 1-2). 그 전까지 삭제 버튼을 만들면
"지웠더니 데이터가 사라졌다"가 된다.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.accounts.models import User
from app.modules.workspaces.models import Workspace, WorkspaceMember
from app.modules.workspaces.schemas import MemberOut, WorkspaceOption, WorkspaceOut
from app.shared.errors import AppError, Conflict, NotFound
from app.shared.permissions import membership_of, workspace_by_slug

ROLES = ("member", "manager")


def _member_count(db: Session, workspace_id: uuid.UUID) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(WorkspaceMember)
            .where(WorkspaceMember.workspace_id == workspace_id)
        )
        or 0
    )


def workspace_out(
    db: Session,
    workspace: Workspace,
    viewer: User,
    *,
    depth: int | None = None,
    path: str | None = None,
    parent_slug: str | None = None,
) -> WorkspaceOut:
    """트리 위치는 **안 주면 스스로 찾는다.**

    목록은 이미 한 번 순회했으니 그 값을 넘겨 준다. 단건 응답(만들기·옮기기)은
    넘길 값이 없는데, 그때 깊이 0·경로=이름으로 두면 방금 자식으로 만든 부서가
    화면에서 뿌리로 보인다 — 실제로 그렇게 틀렸다.
    """
    if depth is None or path is None:
        for node, node_depth, node_path in ordered_tree(db):
            if node.id == workspace.id:
                depth, path = node_depth, node_path
                if node.parent_id:
                    parent = db.get(Workspace, node.parent_id)
                    parent_slug = parent.slug if parent else None
                break

    membership = membership_of(db, workspace_id=workspace.id, user_id=viewer.id)
    return WorkspaceOut(
        id=workspace.id,
        slug=workspace.slug,
        name=workspace.name,
        kind=workspace.kind,
        parent_slug=parent_slug,
        depth=depth or 0,
        path=path or workspace.name,
        sort_order=workspace.sort_order,
        is_active=workspace.is_active,
        created_at=workspace.created_at,
        member_count=_member_count(db, workspace.id),
        my_role=membership.role if membership else None,
    )


# --- 트리 --------------------------------------------------------------------


def ordered_tree(db: Session) -> list[tuple[Workspace, int, str]]:
    """(부서, 깊이, 경로) 를 **트리 순서**로. 화면은 이 순서 그대로 그린다.

    순서를 서버가 정하는 이유: 화면이 평면 목록을 받아 스스로 트리를 세우면,
    부서 선택기·관리 화면·가입 화면이 각자 다른 정렬을 갖게 된다. 조직도의
    순서는 한 곳에서만 정해져야 한다.

    부모가 없는(끊어진) 행도 뿌리로 취급해 반드시 내보낸다. 데이터가 이상해도
    **화면에서 사라지는 것이 가장 나쁘다** — 사라지면 고칠 수도 없다.
    """
    rows = list(db.scalars(select(Workspace)))
    by_parent: dict[uuid.UUID | None, list[Workspace]] = {}
    known = {row.id for row in rows}
    for row in rows:
        parent = row.parent_id if row.parent_id in known else None
        by_parent.setdefault(parent, []).append(row)
    for siblings in by_parent.values():
        siblings.sort(key=lambda item: (item.sort_order, item.name))

    slugs = {row.id: row.slug for row in rows}
    out: list[tuple[Workspace, int, str]] = []

    def walk(parent: uuid.UUID | None, depth: int, prefix: str) -> None:
        for node in by_parent.get(parent, []):
            path = f"{prefix} / {node.name}" if prefix else node.name
            out.append((node, depth, path))
            walk(node.id, depth + 1, path)

    walk(None, 0, "")

    # 순환이 생겨 walk 가 못 닿은 행이 있으면 뒤에 붙인다. 조용히 빠뜨리지 않는다.
    reached = {node.id for node, _, _ in out}
    for row in rows:
        if row.id not in reached:
            out.append((row, 0, f"{row.name} (연결 끊김)"))
    del slugs
    return out


def _descendant_ids(db: Session, workspace_id: uuid.UUID) -> set[uuid.UUID]:
    """자신 + 모든 하위. 부모를 바꿀 때 순환을 막는 데 쓴다."""
    rows = list(db.scalars(select(Workspace)))
    by_parent: dict[uuid.UUID | None, list[Workspace]] = {}
    for row in rows:
        by_parent.setdefault(row.parent_id, []).append(row)

    found = {workspace_id}
    stack = [workspace_id]
    while stack:
        current = stack.pop()
        for child in by_parent.get(current, []):
            if child.id not in found:
                found.add(child.id)
                stack.append(child.id)
    return found


def options(db: Session) -> list[WorkspaceOption]:
    """가입 신청용 부서 목록. 인증 없이 나가므로 이름과 경로만 담는다.

    **경로를 함께 준다.** 같은 이름의 팀이 본부마다 있을 수 있어서, 이름만 보면
    가입 신청자가 어느 쪽인지 고를 수 없다.
    """
    return [
        WorkspaceOption(slug=node.slug, name=node.name, path=path, depth=depth)
        for node, depth, path in ordered_tree(db)
        if node.is_active and node.kind == "org"
    ]


def list_for(db: Session, viewer: User, *, all_workspaces: bool) -> list[WorkspaceOut]:
    """`all_workspaces` 는 시스템 관리자만 쓸 수 있다(라우터가 판정).

    트리 순서로 준다. 내 부서만 볼 때도 순서는 조직도를 따른다 — 화면마다 정렬이
    다르면 같은 목록이 다르게 보인다.
    """
    mine: set[uuid.UUID] | None = None
    if not all_workspaces:
        mine = set(
            db.scalars(
                select(WorkspaceMember.workspace_id).where(
                    WorkspaceMember.user_id == viewer.id
                )
            )
        )

    slug_by_id = {node.id: node.slug for node, _, _ in ordered_tree(db)}
    return [
        workspace_out(
            db,
            node,
            viewer,
            depth=depth,
            path=path,
            parent_slug=slug_by_id.get(node.parent_id) if node.parent_id else None,
        )
        for node, depth, path in ordered_tree(db)
        if mine is None or node.id in mine
    ]


def create(
    db: Session, *, slug: str, name: str, creator: User, parent_slug: str | None = None
) -> Workspace:
    if db.scalar(select(Workspace).where(Workspace.slug == slug)) is not None:
        raise Conflict("MNX-WORKSPACES-0004", "이미 사용 중인 부서 주소입니다.")

    parent = workspace_by_slug(db, parent_slug) if parent_slug else None
    if parent is not None and not parent.is_active:
        raise Conflict(
            "MNX-WORKSPACES-0012",
            "보관된 부서 아래에는 새 부서를 만들 수 없습니다. 상위 부서를 먼저 되살리세요.",
        )

    workspace = Workspace(
        slug=slug,
        name=name.strip(),
        kind="org",
        parent_id=parent.id if parent else None,
        sort_order=_next_sort_order(db, parent.id if parent else None),
    )
    db.add(workspace)
    db.flush()
    # 만든 사람을 관리자로 넣는다. manager 가 0명인 부서는 아무도 멤버를 넣을 수
    # 없어 태어나자마자 잠긴다.
    db.add(WorkspaceMember(workspace_id=workspace.id, user_id=creator.id, role="manager"))
    db.commit()
    return workspace


def _next_sort_order(db: Session, parent_id: uuid.UUID | None) -> int:
    highest = db.scalar(
        select(func.max(Workspace.sort_order)).where(
            Workspace.parent_id.is_(None)
            if parent_id is None
            else Workspace.parent_id == parent_id
        )
    )
    return (highest or 0) + 10


def update(db: Session, *, slug: str, name: str | None, is_active: bool | None) -> Workspace:
    workspace = workspace_by_slug(db, slug)
    if name is not None:
        workspace.name = name.strip()
    if is_active is not None:
        if not is_active:
            _ensure_no_active_children(db, workspace)
        workspace.is_active = is_active
    db.commit()
    return workspace


def _ensure_no_active_children(db: Session, workspace: Workspace) -> None:
    """**부모만 보관하고 자식을 남기면 조직도에 구멍이 난다.**

    RA 가 같은 규칙을 두고 있다(O1). 보관은 "이제 안 쓴다" 는 뜻인데, 그 아래
    활성 팀이 남아 있으면 그 팀은 보관된 본부에 매달린 채로 계속 돌아간다 —
    부서 선택기에서 보관을 걸러 내면 그 팀은 부모 없는 고아처럼 보인다.
    """
    active = list(
        db.scalars(
            select(Workspace).where(
                Workspace.parent_id == workspace.id, Workspace.is_active.is_(True)
            )
        )
    )
    if active:
        raise Conflict(
            "MNX-WORKSPACES-0015",
            f"하위 부서 {len(active)}개가 아직 활성입니다"
            f"({', '.join(w.name for w in active[:3])}). "
            f"하위 부서를 먼저 보관하거나 다른 곳으로 옮기세요.",
        )


def move(db: Session, *, slug: str, parent_slug: str | None) -> Workspace:
    """상위 부서를 바꾼다(조직 개편).

    참조가 `id` 라서 트리를 옮겨도 **데이터는 하나도 안 움직인다.** 시험·재료는
    부서 id 를 가리키고 있고 그 id 는 그대로다.
    """
    workspace = workspace_by_slug(db, slug)
    parent = workspace_by_slug(db, parent_slug) if parent_slug else None

    if parent is not None:
        if parent.id == workspace.id:
            raise Conflict("MNX-WORKSPACES-0013", "자기 자신을 상위 부서로 둘 수 없습니다.")
        if parent.id in _descendant_ids(db, workspace.id):
            # 이걸 막지 않으면 트리에서 떨어져 나간 고리가 생긴다. 화면에서 사라지고
            # 순회는 무한히 돈다.
            raise Conflict(
                "MNX-WORKSPACES-0013",
                "하위 부서 아래로는 옮길 수 없습니다 — 트리가 순환합니다.",
            )
        if workspace.is_active and not parent.is_active:
            raise Conflict(
                "MNX-WORKSPACES-0012",
                "보관된 부서 아래로는 활성 부서를 옮길 수 없습니다.",
            )

    workspace.parent_id = parent.id if parent else None
    workspace.sort_order = _next_sort_order(db, workspace.parent_id)
    db.commit()
    return workspace


def reorder(db: Session, *, slug: str, direction: str) -> Workspace:
    """형제 사이에서 한 칸 올리거나 내린다.

    끌어 놓기(DnD)를 쓰지 않는 이유: 라이브러리가 하나 더 붙고, 키보드로는 쓸 수
    없고, 조직 개편은 자주 하는 일이 아니다. 위/아래 버튼이면 충분하다.
    """
    if direction not in ("up", "down"):
        raise AppError("MNX-WORKSPACES-0014", "위 또는 아래만 가능합니다.", status=400)

    workspace = workspace_by_slug(db, slug)
    siblings = [
        node for node, _, _ in ordered_tree(db) if node.parent_id == workspace.parent_id
    ]
    index = next((i for i, node in enumerate(siblings) if node.id == workspace.id), None)
    if index is None:
        return workspace

    target = index - 1 if direction == "up" else index + 1
    if target < 0 or target >= len(siblings):
        return workspace  # 끝에서 더 밀면 아무 일도 안 한다

    siblings[index], siblings[target] = siblings[target], siblings[index]
    # 통째로 다시 매긴다. 두 값만 바꾸면 예전 데이터의 중복·구멍이 그대로 남는다.
    for order, node in enumerate(siblings):
        node.sort_order = (order + 1) * 10
    db.commit()
    return workspace


# --- 멤버 --------------------------------------------------------------------


def members(db: Session, *, workspace: Workspace) -> list[MemberOut]:
    rows = db.execute(
        select(WorkspaceMember, User)
        .join(User, User.id == WorkspaceMember.user_id)
        .where(WorkspaceMember.workspace_id == workspace.id)
        .order_by(User.display_name)
    ).all()
    return [
        MemberOut(
            user_id=user.id,
            email=user.email,
            display_name=user.display_name,
            status=user.status,
            role=member.role,
            joined_at=member.created_at,
        )
        for member, user in rows
    ]


def add_member(db: Session, *, workspace: Workspace, email: str, role: str) -> MemberOut:
    _check_role(role)
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    if user is None:
        raise NotFound("MNX-WORKSPACES-0005", "계정을 찾을 수 없습니다.")
    if user.status == "pending":
        # 승인 절차를 우회해 부서에 넣는 길을 막는다.
        raise Conflict(
            "MNX-WORKSPACES-0006", "승인 대기 중인 계정입니다. 계정 관리에서 먼저 승인하세요."
        )

    existing = membership_of(db, workspace_id=workspace.id, user_id=user.id)
    if existing is not None:
        raise Conflict("MNX-WORKSPACES-0007", "이미 이 부서의 멤버입니다.")

    member = WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role=role)
    db.add(member)
    if user.home_workspace_id is None:
        user.home_workspace_id = workspace.id
    db.commit()
    db.refresh(member)
    return MemberOut(
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        status=user.status,
        role=member.role,
        joined_at=member.created_at,
    )


def set_role(db: Session, *, workspace: Workspace, user_id: uuid.UUID, role: str) -> MemberOut:
    _check_role(role)
    member = membership_of(db, workspace_id=workspace.id, user_id=user_id)
    if member is None:
        raise NotFound("MNX-WORKSPACES-0008", "이 부서의 멤버가 아닙니다.")

    if member.role == "manager" and role != "manager":
        _ensure_another_manager(db, workspace=workspace, excluding=user_id)

    member.role = role
    db.commit()
    user = db.get(User, user_id)
    assert user is not None
    return MemberOut(
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        status=user.status,
        role=member.role,
        joined_at=member.created_at,
    )


def remove_member(db: Session, *, workspace: Workspace, user_id: uuid.UUID) -> None:
    member = membership_of(db, workspace_id=workspace.id, user_id=user_id)
    if member is None:
        raise NotFound("MNX-WORKSPACES-0008", "이 부서의 멤버가 아닙니다.")
    if member.role == "manager":
        _ensure_another_manager(db, workspace=workspace, excluding=user_id)

    user = db.get(User, user_id)
    if user is not None and user.home_workspace_id == workspace.id:
        # 소속을 남은 부서 중 하나로 옮긴다. 비워 두면 로그인 후 갈 곳이 없다.
        remaining = db.scalar(
            select(WorkspaceMember).where(
                WorkspaceMember.user_id == user_id,
                WorkspaceMember.workspace_id != workspace.id,
            )
        )
        user.home_workspace_id = remaining.workspace_id if remaining else None

    db.delete(member)
    db.commit()


def _ensure_another_manager(
    db: Session, *, workspace: Workspace, excluding: uuid.UUID
) -> None:
    """마지막 관리자를 잃지 않게 한다.

    manager 가 0명이 되면 그 부서는 멤버를 넣을 수도 뺄 수도 없어, 시스템 관리자가
    개입해야만 풀린다. 그런 상태를 만들 수 있는 버튼은 두지 않는다.
    """
    other = db.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace.id,
            WorkspaceMember.role == "manager",
            WorkspaceMember.user_id != excluding,
        )
    )
    if other is None:
        raise Conflict(
            "MNX-WORKSPACES-0009",
            "부서에 관리자가 최소 한 명 있어야 합니다. 다른 사람을 먼저 관리자로 지정하세요.",
        )


def _check_role(role: str) -> None:
    if role not in ROLES:
        raise AppError("MNX-WORKSPACES-0010", "허용되지 않는 역할입니다.", status=400)
