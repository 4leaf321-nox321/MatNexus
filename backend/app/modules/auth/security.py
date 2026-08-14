"""비밀번호 해시와 토큰 발급 — 암호 관련 원시 연산만 모은다.

**bcrypt 앞에 sha256을 한 번 건다.** bcrypt는 입력을 72바이트에서 자르는데,
한글 비밀번호는 글자당 3바이트라 24자를 넘으면 뒤가 조용히 무시된다. sha256으로
길이를 고정한 뒤 bcrypt에 넣으면 길이 제한이 사라진다(passlib의 bcrypt_sha256과
같은 방식). passlib 자체를 쓰지 않는 이유는 RA가 겪은 버전 호환 문제
(passlib 1.7.4 ↔ bcrypt 4.x)를 반복하지 않기 위해서다.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from app.config import get_settings

#: PAT 평문 앞에 붙는 표식. 로그·소스에서 유출을 눈으로 찾을 수 있게 한다.
PAT_PREFIX = "mnx_pat_"


def _prepared(password: str) -> bytes:
    return base64.b64encode(hashlib.sha256(password.encode("utf-8")).digest())


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_prepared(password), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(_prepared(password), password_hash.encode("ascii"))
    except ValueError:
        # 저장된 해시가 손상된 경우. 인증 실패로 처리하되 조용히 넘기지 않는다.
        return False


def hash_token(raw: str) -> str:
    """불투명 토큰(refresh·PAT)의 저장용 해시. 원문은 어디에도 남기지 않는다."""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def new_opaque_token() -> str:
    return secrets.token_urlsafe(48)


def new_pat() -> tuple[str, str, str]:
    """(평문, 표시용 prefix, 해시). 평문은 발급 응답에서 한 번만 노출된다."""
    raw = PAT_PREFIX + secrets.token_urlsafe(32)
    return raw, raw[: len(PAT_PREFIX) + 6], hash_token(raw)


def create_access_token(user_id: uuid.UUID) -> tuple[str, int]:
    """(JWT, 만료까지 초). access는 짧게 살고 폐기하지 않는다 — 폐기는 refresh의 몫."""
    settings = get_settings()
    ttl = timedelta(minutes=settings.access_token_minutes)
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int((now + ttl).timestamp()),
        "typ": "access",
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm="HS256")
    return token, int(ttl.total_seconds())


def decode_access_token(token: str) -> dict[str, Any] | None:
    """검증에 실패하면 None. 실패 사유를 호출자에게 넘기지 않는다 — 응답으로 새면
    공격자에게 힌트가 된다. 사유는 호출부에서 로그로 남긴다."""
    try:
        payload: dict[str, Any] = jwt.decode(
            token, get_settings().jwt_secret, algorithms=["HS256"]
        )
    except jwt.PyJWTError:
        return None
    return payload if payload.get("typ") == "access" else None
