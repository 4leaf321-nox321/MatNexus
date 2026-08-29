"""서버 현황 — **읽기만 한다.**

여기서 서버를 재시작하거나 설정을 바꾸지 않는다. 화면에서 만질 수 있으면 그것은
「현황」 이 아니라 운영 도구이고, 웹으로 그 권한을 여는 것은 별개의 결정이다.
참고한 ReportArchive 는 워커 수를 화면에서 고치는데, 거기는 systemd 가 있고
재시작을 사람이 따로 한다 — 여기는 그 전제가 없다.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.accounts.models import User
from app.modules.server import services
from app.modules.server.schemas import ServerInfoOut
from app.shared.auth import require_system_admin

router = APIRouter(prefix="/server", tags=["server"])


@router.get("/info", response_model=ServerInfoOut)
def server_info(
    user: User = Depends(require_system_admin), db: Session = Depends(get_db)
) -> ServerInfoOut:
    """호스트·CPU·메모리·디스크·DB 를 한 번에.

    **시스템 관리자만.** 호스트 이름과 경로가 담겨 있어 사내라도 모두에게 보일
    것은 아니다.
    """
    return ServerInfoOut.model_validate(services.info(db))
