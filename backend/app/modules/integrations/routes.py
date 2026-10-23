"""외부 연동 — **시스템 관리자만** 보고 고친다.

    GET  /integrations                  붙일 수 있는 바깥 시스템 전부(아직 안 넣은 것은 빈 칸)
    GET  /integrations/{system}         하나
    PUT  /integrations/{system}         주소 · 토큰 고치기(토큰은 안 보내면 그대로)
    POST /integrations/{system}/check   실제로 닿는지 — 결과를 남긴다

토큰은 어떤 응답에도 싣지 않는다. 보기까지 시스템 관리자로 묶은 것은 주소 · 토큰 주인 · 연결
상태가 사내 시스템 배치를 말하기 때문이다 — 바깥에 묻는 기능(측정법 연동)은 이 라우터가 아니라
`services.credentials` 로 받는다.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.accounts.models import User
from app.modules.integrations import services
from app.modules.integrations.schemas import (
    IntegrationCheckOut,
    IntegrationIn,
    IntegrationOut,
)
from app.shared.auth import require_system_admin

router = APIRouter(prefix="/integrations", tags=["integrations"])


@router.get("", response_model=list[IntegrationOut])
def list_integrations(
    _: User = Depends(require_system_admin), db: Session = Depends(get_db)
) -> list[IntegrationOut]:
    return services.list_all(db)


@router.get("/{system}", response_model=IntegrationOut)
def get_integration(
    system: str, _: User = Depends(require_system_admin), db: Session = Depends(get_db)
) -> IntegrationOut:
    return services.get(db, system)


@router.put("/{system}", response_model=IntegrationOut)
def update_integration(
    system: str,
    payload: IntegrationIn,
    user: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> IntegrationOut:
    return services.update(db, system, payload, user)


@router.post("/{system}/check", response_model=IntegrationCheckOut)
def check_integration(
    system: str, _: User = Depends(require_system_admin), db: Session = Depends(get_db)
) -> IntegrationCheckOut:
    return services.check(db, system)
