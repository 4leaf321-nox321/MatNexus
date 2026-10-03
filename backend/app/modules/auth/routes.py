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
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.modules.accounts.models import User
from app.modules.auth import gateway_token, services
from app.modules.auth.schemas import (
    ChangePasswordRequest,
    GatewayRevokeOut,
    GatewayTokenData,
    GatewayTokenOut,
    LoginRequest,
    LoginResponse,
    McpConnectionOut,
    PatCreateRequest,
    PatCreateResponse,
    PatOut,
    PortalConnectionOut,
    ProfileUpdateRequest,
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
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> LoginResponse:
    # **비동기다** — 틀린 비밀번호를 늦출 때 스레드를 붙잡지 않으려고(`LoginDelayed`). DB 를
    # 만지는 일은 전처럼 스레드 풀에서 하고, 기다리는 것만 이벤트 루프에서 한다.
    try:
        user = await run_in_threadpool(
            services.authenticate, db, str(payload.email), payload.password
        )
    except services.LoginDelayed as delayed:
        await services.wait(delayed.delay)
        raise delayed.error from None
    access, expires_in, refresh_raw = await run_in_threadpool(
        services.issue_session, db, user, request.headers.get("user-agent")
    )
    _set_refresh_cookie(response, refresh_raw)
    shown = await run_in_threadpool(services.user_out, db, user)
    return LoginResponse(
        access_token=access,
        expires_in=expires_in,
        user=shown,
        notice=services.login_notice(str(payload.email), user),
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


@router.patch("/me", response_model=UserOut)
def update_me(
    payload: ProfileUpdateRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> UserOut:
    """자기 표시 이름을 바꾼다.

    아이디는 여기서 못 바꾼다 — 로그인 식별자라 본인이 바꾸면 기록이 가리키는
    대상이 흔들린다. 그것은 관리자의 일이다.
    """
    user.display_name = payload.display_name.strip()
    db.commit()
    db.refresh(user)
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


# --- HWAX 포털 게이트웨이의 사람별 위임 (ADR 0056) -----------------------------
#
# 셋 다 **인증 의존성을 안 지난다** — 자격은 공유 비밀(`X-Heax-Gateway-Secret`)이고, 그 판정은
# `gateway_token.gate` 가 한다. 왜 SSO 가 아닌지 · 왜 계정을 안 만드는지 · 왜 읽기 전용인지는
# 그 모듈 머리에 있다.


@router.post("/sso", response_model=GatewayTokenOut)
def gateway_issue(request: Request, db: Session = Depends(get_db)) -> GatewayTokenOut:
    """HWAX 게이트웨이가 **그 사람의 읽기 전용 토큰**을 받아 간다. 꺼져 있으면 404, 비밀이
    틀리면 401, 그 사람을 들여보낼 수 없으면 403 — 404 는 「창구 꺼짐」 전용이다."""
    gateway_token.gate(request)
    return GatewayTokenOut(data=GatewayTokenData(**gateway_token.issue(db, request)))


@router.post("/sso/verify", status_code=204)
def gateway_verify(request: Request) -> None:
    """비밀만 확인한다(204 / 401) — 설정이 맞는지 볼 때. 아무것도 만들지 않는다."""
    gateway_token.gate(request)


@router.post("/sso/revoke", response_model=GatewayRevokeOut)
def gateway_revoke(request: Request, db: Session = Depends(get_db)) -> GatewayRevokeOut:
    """그 사람 · 그 client 의 위임 토큰을 폐기한다. 폐기할 것이 없어도 200 이다."""
    gateway_token.gate(request)
    return GatewayRevokeOut(revoked=gateway_token.revoke(db, request))


@router.get("/mcp-connection", response_model=McpConnectionOut)
def mcp_connection(_user: User = Depends(current_user)) -> McpConnectionOut:
    """사람에게 줄 MCP 연결 주소 — **서버가 준다**(RA `/api/me/mcp-connection` 과 같은 판단).

    화면이 「지금 보는 호스트:8012」 로 짐작하면, 서버를 옮기거나 앞에 프록시를 둔 날 그 짐작이
    틀린 주소를 준다 — RA 는 포털 아래로 옮긴 뒤 그 주소로 등록한 사람들의 MCP 가 끊겼다.
    설정이 없으면 모른다고 답한다(화면이 그때만 짐작하고, 짐작이라고 말한다).
    """
    settings = get_settings()
    direct = settings.mcp_public_url.strip() or None
    portal_base = settings.hwax_portal_url.strip().rstrip("/")
    portal = (
        PortalConnectionOut(
            gateway_url=f"{portal_base}/mcp-gw/mcp",
            tokens_url=f"{portal_base}/tokens",
            auto_token=gateway_token.enabled(),
        )
        if portal_base
        else None
    )
    return McpConnectionOut(direct_url=direct, portal=portal)


# --- PAT — 장비 파이프라인·스크립트용 자격 증명 (구조결정 9) --------------------


@router.post("/tokens", response_model=PatCreateResponse, status_code=201)
def create_token(
    payload: PatCreateRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> PatCreateResponse:
    raw, pat = services.create_pat(
        db, user, payload.name, payload.expires_in_days, read_only=payload.read_only
    )
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
