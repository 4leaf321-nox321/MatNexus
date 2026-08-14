"""인증 라우터.

**refresh 토큰은 httpOnly 쿠키로만 오간다.** 자바스크립트가 읽을 수 없으므로
XSS로 새지 않고, 배포가 동일 출처(백엔드 한 프로세스가 SPA까지 서빙)라 별도
설정도 필요 없다. 개발 중에도 Vite 프록시를 거치므로 브라우저 입장에서는 같은
출처다. access 토큰은 응답 본문으로만 주고 프론트는 메모리에 둔다 —
localStorage에 두면 XSS 한 번에 탈취된다.

쿠키 path 를 `/api/auth` 로 제한해 일반 API 호출에는 실려 나가지 않는다.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.modules.accounts.models import User
from app.modules.auth import services
from app.modules.auth.schemas import (
    ChangePasswordRequest,
    LoginRequest,
    LoginResponse,
    PatCreateRequest,
    PatCreateResponse,
    PatOut,
    UserOut,
)
from app.shared.auth import current_user
from app.shared.errors import AppError

router = APIRouter(prefix="/auth", tags=["auth"])

COOKIE_PATH = "/api/auth"


def _set_refresh_cookie(response: Response, raw: str) -> None:
    settings = get_settings()
    response.set_cookie(
        settings.refresh_cookie_name,
        raw,
        max_age=settings.refresh_token_days * 24 * 3600,
        httponly=True,
        samesite="lax",
        secure=settings.refresh_cookie_secure,
        path=COOKIE_PATH,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(get_settings().refresh_cookie_name, path=COOKIE_PATH)


@router.post("/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> LoginResponse:
    user = services.authenticate(db, str(payload.email), payload.password)
    access, expires_in, refresh_raw = services.issue_session(
        db, user, request.headers.get("user-agent")
    )
    _set_refresh_cookie(response, refresh_raw)
    return LoginResponse(
        access_token=access, expires_in=expires_in, user=services.user_out(db, user)
    )


@router.post("/refresh", response_model=LoginResponse)
def refresh(
    request: Request, response: Response, db: Session = Depends(get_db)
) -> LoginResponse:
    raw = request.cookies.get(get_settings().refresh_cookie_name)
    if not raw:
        raise AppError("MNX-AUTH-0003", "세션이 없습니다. 로그인해 주세요.", status=401)

    user, access, expires_in, new_raw = services.rotate_refresh(
        db, raw, request.headers.get("user-agent")
    )
    _set_refresh_cookie(response, new_raw)
    return LoginResponse(
        access_token=access, expires_in=expires_in, user=services.user_out(db, user)
    )


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, db: Session = Depends(get_db)) -> None:
    raw = request.cookies.get(get_settings().refresh_cookie_name)
    if raw:
        services.revoke_refresh(db, raw)
    _clear_refresh_cookie(response)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user), db: Session = Depends(get_db)) -> UserOut:
    return services.user_out(db, user)


@router.post("/change-password", status_code=204)
def change_password(
    payload: ChangePasswordRequest,
    response: Response,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> None:
    services.change_password(db, user, payload.current_password, payload.new_password)
    # 모든 세션을 끊었으므로 이 브라우저의 쿠키도 함께 버린다.
    _clear_refresh_cookie(response)


# --- PAT — 장비 파이프라인·스크립트용 자격 증명 (구조결정 9) --------------------


@router.post("/tokens", response_model=PatCreateResponse, status_code=201)
def create_token(
    payload: PatCreateRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> PatCreateResponse:
    raw, pat = services.create_pat(db, user, payload.name, payload.expires_in_days)
    return PatCreateResponse(token=raw, pat=pat)


@router.get("/tokens", response_model=list[PatOut])
def list_tokens(
    user: User = Depends(current_user), db: Session = Depends(get_db)
) -> list[PatOut]:
    return services.list_pats(db, user)


@router.delete("/tokens/{pat_id}", status_code=204)
def revoke_token(
    pat_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> None:
    services.revoke_pat(db, user, pat_id)
