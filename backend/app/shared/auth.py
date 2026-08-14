"""인증 의존성 — 모든 모듈이 쓰는 `current_user`.

여기가 `app/modules/auth` 가 아니라 `shared` 에 있는 이유: 모든 모듈이 현재
사용자를 필요로 하는데, 그때마다 auth 모듈을 직접 import 하면 모든 모듈이 auth
에 묶인다. 의존성은 횡단 관심사이므로 shared 가 맞다(RA·52도 `shared/auth.py`).
방향은 shared → auth 한 쪽이며 그 반대는 없다.

**두 가지 자격을 같은 지점에서 받는다** — 사람의 access JWT와 기계의 PAT.
Phase 6의 장비 파이프라인은 PAT로 같은 엔드포인트를 부른다. 권한 판정이 한
곳이어야 "사람은 되는데 파이프라인은 안 되는" 어긋남이 생기지 않는다.
"""

from __future__ import annotations

import logging

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.accounts.models import User
from app.modules.auth import security, services
from app.shared.errors import AppError, Forbidden

logger = logging.getLogger(__name__)

_UNAUTHENTICATED = "로그인이 필요합니다."


def _bearer(request: Request) -> str | None:
    header = request.headers.get("authorization")
    if not header or not header.lower().startswith("bearer "):
        return None
    return header[7:].strip() or None


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = _bearer(request)
    if token is None:
        raise AppError("MNX-AUTH-0100", _UNAUTHENTICATED, status=401)

    if token.startswith(security.PAT_PREFIX):
        user = services.resolve_pat(db, token)
        if user is None:
            logger.warning("PAT 인증 실패 (prefix=%s)", token[: len(security.PAT_PREFIX) + 6])
            raise AppError("MNX-AUTH-0101", "토큰이 유효하지 않습니다.", status=401)
        # 접근 로그 미들웨어가 "누가" 를 알 수 있게 scope 에 남긴다. 미들웨어는
        # 인증보다 바깥에 있어서 스스로는 사용자를 알 수 없다.
        request.scope["mnx_user_id"] = user.id
        return user

    payload = security.decode_access_token(token)
    if payload is None:
        # 사유(만료·서명 불일치)는 응답에 싣지 않는다 — 공격자에게 힌트가 된다.
        raise AppError("MNX-AUTH-0102", "세션이 만료되었습니다.", status=401)

    user = db.get(User, payload["sub"])
    if user is None:
        raise Forbidden("MNX-AUTH-0002", "삭제된 계정입니다. 관리자에게 문의하세요.")
    services.ensure_can_sign_in(user)
    request.scope["mnx_user_id"] = user.id
    return user


def require_system_admin(user: User = Depends(current_user)) -> User:
    if not user.is_system_admin:
        raise Forbidden("MNX-AUTH-0103", "권한이 없습니다.")
    return user
