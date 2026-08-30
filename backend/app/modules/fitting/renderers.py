"""해석용 물성 정의를 행에서 읽어 렌더러로 만든다 — ADR 0023 2단계.

**`matcore` 는 DB 를 모른다.** 행을 읽는 것은 여기고, 넘기는 것은 dict 다
(인풋 프로파일과 같은 규칙, ADR 0006).

## 기동이 아니라 요청 때 합친다

ADR 초안은 「앱 기동 시점에 `add_renderer` 로 얹는다」 였다. 안 그렇게 했다:

- **고치면 바로 먹어야 한다.** 기동 때 한 번 얹으면 화면에서 정의를 고쳐도
  재기동 전까지 옛 덱이 나간다. 「배포 없이」 를 얻으려고 만든 것인데 재기동이
  남으면 절반만 얻는다.
- **워커마다 상태가 갈린다.** 여럿을 띄우면 얹은 시점이 달라, 같은 요청이 어느
  워커에 닿느냐에 따라 다른 덱이 나온다 — 그리고 그것은 재현되지 않는다.
- **레지스트리는 프로세스 전역이다.** 부서마다 정의가 다른데 전역에 얹으면 한
  요청이 옆 요청의 덱을 바꾼다.

부르는 자리가 둘뿐이라(`list_formats` · `export_card`) 값도 싸다.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from matcore import export
from matcore.export import template

from .models import ExportProfile

log = logging.getLogger(__name__)


def _rows(db: Session, workspace_id: uuid.UUID | None) -> list[ExportProfile]:
    """살아 있는 정의. **내 부서 것이 전역보다 먼저다.**

    같은 솔버라도 사업부마다 덱 관례가 다르다 — 어느 키워드를 쓰는지, 표를 몇
    줄로 자르는지. 부서 것이 있으면 그것이 이긴다(프로파일과 같은 규칙).
    """
    rows = db.scalars(
        select(ExportProfile)
        .where(
            ExportProfile.deleted_at.is_(None),
            ExportProfile.is_active.is_(True),
            or_(
                ExportProfile.owner_workspace_id.is_(None),
                ExportProfile.owner_workspace_id == workspace_id,
            ),
        )
        .order_by(ExportProfile.key)
    ).all()

    # 부서 것을 나중에 넣어 전역을 덮는다.
    chosen: dict[str, ExportProfile] = {}
    for row in sorted(rows, key=lambda one: one.owner_workspace_id is not None):
        chosen[row.key] = row
    return list(chosen.values())


def all_renderers(db: Session, workspace_id: uuid.UUID | None) -> list[export.Renderer]:
    """코드 렌더러 + 정의 렌더러.

    **깨진 정의 하나가 목록을 죽이지 않는다.** 건너뛰고 로그를 남긴다 — 목록이
    안 뜨면 사람은 어느 정의가 문제인지 볼 길조차 없어지고, 고치러 들어갈 화면도
    그 목록 위에 있다.
    """
    found = list(export.list_renderers())
    taken = {item.key for item in found}
    for row in _rows(db, workspace_id):
        if row.key in taken:
            # **코드 렌더러가 이긴다.** 덮게 두면 코드 쪽 검증(키워드 확인·물리적
            # 타당성)을 정의 하나가 조용히 우회한다. 저장할 때도 막지만, 코드에
            # 새 렌더러가 붙어 뒤늦게 겹칠 수 있어 여기서도 본다.
            log.warning(
                "해석용 물성 정의 %s 를 건너뜁니다 — 같은 key 의 코드 렌더러가 있습니다",
                row.key,
            )
            continue
        try:
            found.append(
                # **행의 칸이 정본이다.** `key`·`label` 은 컬럼에도 정의에도 둘 수
                # 있는데, 두 벌로 두면 목록에 뜨는 이름과 덱에 적히는 이름이
                # 어긋난다 — 그리고 어느 쪽이 맞는지 화면에 안 나온다.
                template.renderer_from_definition(
                    {**row.definition, "key": row.key, "label": row.label}
                )
            )
        except export.ExportError:
            log.exception("해석용 물성 정의 %s 를 읽지 못했습니다", row.key)
    return found


def renderer_for(db: Session, workspace_id: uuid.UUID | None, key: str) -> export.Renderer:
    """하나를 고른다. 없으면 **있는 것을 알려 준다** — 화면과 목록이 어긋났을 때
    사람이 다음에 무엇을 할지 알아야 한다."""
    for item in all_renderers(db, workspace_id):
        if item.key == key:
            return item
    known = ", ".join(sorted(item.key for item in all_renderers(db, workspace_id)))
    raise export.ExportError(f"모르는 형식입니다: {key}. 있는 것: {known}")
