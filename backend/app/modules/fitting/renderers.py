"""해석용 물성 정의 → 렌더러. **목록은 `shared/deckmap` 이 만든다**(2026-09-16 이동).

온톨로지 지도가 같은 목록을 읽어야 해서 shared 로 옮겼다. 여기는 fitting 이 부르는
이름을 그대로 둔다 — 라우터와 시험이 `renderers.all_renderers` 로 부른다.
"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.shared.deckmap import all_renderers
from matcore import export

__all__ = ["all_renderers", "renderer_for"]


def renderer_for(db: Session, workspace_id: uuid.UUID | None, key: str) -> export.Renderer:
    """하나를 고른다. 없으면 **있는 것을 알려 준다** — 화면과 목록이 어긋났을 때
    사람이 다음에 무엇을 할지 알아야 한다."""
    for item in all_renderers(db, workspace_id):
        if item.key == key:
            return item
    known = ", ".join(sorted(item.key for item in all_renderers(db, workspace_id)))
    raise export.ExportError(f"모르는 형식입니다: {key}. 있는 것: {known}")
