"""ReportArchive 부서 트리 가져오기 — **조직도를 두 번 치지 않는다.**

ReportArchive(RA)의 「시스템 관리 > 부서 정보 내보내기」 가 만든 CSV(`부서정보.csv`)를
받아 MatNexus 의 부서 트리를 만든다. 두 시스템을 같은 조직이 쓰는데 부서를 양쪽에
손으로 치면, 오타 하나로 「같은 부서가 다른 이름」 이 된다 — slug 가 갈리는 순간
사람이 눈으로 못 잡는다.

## 형식 (RA `workspaces/export.csv`)

    slug,name,parent_slug,parent_name,depth,path,kind,status,description,
    sort_order,external_view_default,member_count,managers,created_at

UTF-8 BOM · 깊이우선 순서. 여기서 쓰는 것은 **slug·name·parent_slug·kind·
sort_order** 다 — 나머지(멤버수·매니저·생성일)는 RA 운영 정보라 들여오지 않는다.
멤버는 계정 체계가 달라 자동으로 못 잇는다(RA 이름 ↔ MatNexus 계정).

## 무엇을 들여오나

    org      들여온다 — 조직도의 부서다
    virtual  들여온다(org 로) — RA 의 트리 묶음 노드인데, MatNexus 트리에서도
             같은 자리(중간 노드)가 필요하다. 종류 구분은 MatNexus 에 없다
    tf       건너뛴다 — 한시 조직이라 조직도가 아니다(RA 설계도 트리 밖이다)
    personal 건너뛴다 — RA 내보내기에도 없지만, 손으로 만든 파일을 대비해 막는다

## 멱등이다

이미 있는 slug 는 **건드리지 않고 건너뛴다.** 이름이 달라도 덮지 않는다 — MatNexus
에서 고친 이름을 가져오기가 조용히 되돌리면, 고친 사람은 영문을 모른다. 갱신은
부서 관리 화면에서 한다.

## slug 를 고쳐 쓰지 않는다

MatNexus 규칙(2~50자)에 안 맞는 slug 는 **오류로 낸다.** 자르거나 바꿔서 만들면
두 시스템이 같은 부서를 다른 주소로 부르게 된다 — 이 기능이 막으려는 바로 그 일이다.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.accounts.models import User
from app.modules.workspaces.models import Workspace, WorkspaceMember
from app.modules.workspaces.schemas import SLUG_PATTERN
from app.shared.errors import AppError

#: 없으면 이 파일이 아니다. 값 열(멤버수 등)은 없어도 된다 — 손으로 줄인 파일을 받는다.
REQUIRED_COLUMNS = ("slug", "name", "parent_slug", "kind")

#: 행이 이렇게 처리된다. 화면이 이 값으로 줄 색을 정한다.
ACTIONS = ("create", "skip_exists", "skip_kind", "error")


@dataclass(frozen=True)
class Planned:
    """행 하나의 운명 — 만들지, 왜 건너뛰는지."""

    line: int
    slug: str
    name: str
    parent_slug: str | None
    action: str
    reason: str


def parse(raw: bytes) -> list[dict[str, str]]:
    """CSV 를 행 dict 로. **형식이 아니면 무엇이 없는지 말하고 거절한다.**

    아무 CSV 나 받아 조용히 0건을 만들면, 사람은 「가져오기가 안 된다」 만 안다.
    """
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise AppError(
            "MNX-WORKSPACES-0020",
            "UTF-8 파일이 아닙니다. ReportArchive 의 「부서 정보 내보내기」 가 만든 "
            "CSV 를 그대로 올리세요.",
            status=422,
        ) from exc

    reader = csv.DictReader(io.StringIO(text))
    header = [name.strip() for name in (reader.fieldnames or [])]
    missing = [name for name in REQUIRED_COLUMNS if name not in header]
    if missing:
        raise AppError(
            "MNX-WORKSPACES-0020",
            f"부서 내보내기 형식이 아닙니다 — {', '.join(missing)} 열이 없습니다. "
            "ReportArchive 의 「부서 정보 내보내기」 가 만든 CSV 를 그대로 올리세요.",
            status=422,
        )
    return [
        {key.strip(): (value or "").strip() for key, value in row.items()} for row in reader
    ]


def plan(db: Session, rows: list[dict[str, str]]) -> list[Planned]:
    """행마다 무엇이 일어날지. **적용과 같은 코드로 판정한다** — 미리보기 따로
    적용 따로면 「미리보기엔 된다더니」 가 된다."""
    existing = set(db.scalars(select(Workspace.slug)))
    # 파일 안에서 만들어질 것들 — 뒤 행의 부모가 앞 행일 수 있다(깊이우선 순서).
    will_exist = set(existing)
    seen_in_file: set[str] = set()

    planned: list[Planned] = []
    for at, row in enumerate(rows, start=2):  # 1행은 머리말
        slug = row.get("slug", "")
        name = row.get("name", "") or slug
        parent = row.get("parent_slug", "") or None
        kind = row.get("kind", "") or "org"

        def keep(
            action: str,
            reason: str,
            *,
            line: int = at,
            slug: str = slug,
            name: str = name,
            parent: str | None = parent,
        ) -> None:
            planned.append(
                Planned(
                    line=line,
                    slug=slug,
                    name=name,
                    parent_slug=parent,
                    action=action,
                    reason=reason,
                )
            )

        if kind not in ("org", "virtual"):
            keep(
                "skip_kind",
                "한시 조직(TF)·개인 공간은 조직도가 아니라 들여오지 않습니다."
                if kind in ("tf", "personal")
                else f"모르는 종류입니다: {kind}",
            )
            continue
        if not re.fullmatch(SLUG_PATTERN, slug):
            # **고쳐 쓰지 않는다.** 자르거나 바꾸면 두 시스템이 같은 부서를
            # 다른 주소로 부르게 된다.
            keep("error", "주소(slug)가 규칙(소문자·숫자·하이픈, 2~50자)에 맞지 않습니다.")
            continue
        if slug in seen_in_file:
            keep("error", "파일 안에 같은 주소가 두 번 있습니다.")
            continue
        seen_in_file.add(slug)
        if slug in existing:
            # **덮지 않는다.** MatNexus 에서 고친 이름을 조용히 되돌리면
            # 고친 사람은 영문을 모른다.
            keep("skip_exists", "이미 있는 부서라 그대로 둡니다(이름도 덮지 않습니다).")
            continue
        if parent and parent not in will_exist:
            keep(
                "error",
                f"상위 부서({parent})가 MatNexus 에도, 이 파일의 앞 행에도 없습니다. "
                "TF 아래 행이거나 파일이 잘렸을 수 있습니다.",
            )
            continue
        will_exist.add(slug)
        keep("create", "")
    return planned


def apply(db: Session, rows: list[dict[str, str]], creator: User) -> list[Planned]:
    """계획대로 만든다. **커밋하지 않는다 — 라우트가 한 번에 한다.**

    `services.create` 를 안 쓰는 이유: 그 함수는 행마다 commit 한다. 도중에 하나가
    막히면(동시에 누가 같은 slug 를 만들었다거나) **절반만 들어간 조직도**가 남는데,
    그것은 없느니만 못하다 — 다시 올리면 앞 절반이 「이미 있음」 으로 갈려 무엇이
    이번 것인지 알 수 없다.

    순서는 파일이 보장한다 — RA 내보내기가 깊이우선이라 부모가 항상 앞 행이다.
    """
    planned = plan(db, rows)
    by_slug = {row.get("slug", ""): row for row in rows}
    made_by_slug: dict[str, Workspace] = {}
    for one in planned:
        if one.action != "create":
            continue
        parent: Workspace | None = None
        if one.parent_slug:
            parent = made_by_slug.get(one.parent_slug) or db.scalar(
                select(Workspace).where(Workspace.slug == one.parent_slug)
            )
        raw_order = by_slug.get(one.slug, {}).get("sort_order", "")
        made = Workspace(
            slug=one.slug,
            name=one.name.strip(),
            kind="org",
            parent_id=parent.id if parent else None,
            # RA 트리의 형제 순서를 지킨다 — 순서는 사람이 정한 것이다.
            sort_order=int(raw_order) if raw_order.lstrip("-").isdigit() else 0,
        )
        db.add(made)
        db.flush()
        # 만든 사람을 관리자로 — manager 0명인 부서는 태어나자마자 잠긴다
        # (`services.create` 와 같은 규칙).
        db.add(WorkspaceMember(workspace_id=made.id, user_id=creator.id, role="manager"))
        made_by_slug[one.slug] = made
    return planned
