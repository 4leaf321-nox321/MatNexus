"""외부 연동 — 설정을 읽고 고치고, 실제로 닿는지 확인한다.

고치기     주소 둘 · 토큰(봉인). 토큰은 **안 보내면 그대로**, 지우기는 따로 말한다
연결 확인  `GET {api}/auth/me` 로 토큰 주인을, `GET {api}/properties` 로 시험 항목이 이어진
           물성 수를 본다 — 둘째가 0 이면 닿아도 물성으로 장비를 못 찾는다
빌려주기   바깥에 묻는 쪽(측정법 · 의뢰)은 `shared.testscope` 를 거친다 — 주소 · 토큰 ·
           클라이언트가 거기 한 벌이다(시험은 `testscope.TRANSPORT` 에 모의를 끼운다)
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.accounts.models import User
from app.modules.integrations.models import SYSTEMS, IntegrationConnection
from app.modules.integrations.schemas import (
    IntegrationCheckOut,
    IntegrationIn,
    IntegrationOut,
)
from app.shared import audit, secretbox, testscope
from app.shared.errors import AppError, NotFound


def _system(system: str) -> str:
    if system not in SYSTEMS:
        raise NotFound(
            "MNX-INTEGRATIONS-0001",
            f"그런 외부 연동이 없습니다: {system} — {', '.join(SYSTEMS)} 중 하나.",
        )
    return system


def _row(db: Session, system: str) -> IntegrationConnection | None:
    return db.scalar(
        select(IntegrationConnection).where(IntegrationConnection.system == system)
    )


def _clean_url(raw: str, *, field: str) -> str:
    url = raw.strip().rstrip("/")
    if url and not url.lower().startswith(("http://", "https://")):
        raise AppError(
            "MNX-INTEGRATIONS-0002",
            f"{field} 는 http:// 또는 https:// 로 시작해야 합니다: {raw}",
            status=422,
        )
    return url


def api_url(raw: str) -> str:
    """API 주소 — 끝에 `/api` 가 없으면 붙인다. 화면 주소를 그대로 붙여 넣는 일이 흔하다."""
    url = _clean_url(raw, field="API 주소")
    if url and not url.endswith("/api"):
        url += "/api"
    return url


def link_url(row: IntegrationConnection | None) -> str:
    if row is None:
        return ""
    if row.web_url:
        return row.web_url
    return row.base_url[: -len("/api")] if row.base_url.endswith("/api") else row.base_url


def to_out(db: Session, system: str, row: IntegrationConnection | None) -> IntegrationOut:
    readable = bool(row and secretbox.unseal(row.token_sealed))
    editor = db.get(User, row.updated_by_id) if row and row.updated_by_id else None
    return IntegrationOut(
        system=system,
        label=SYSTEMS[system],
        base_url=row.base_url if row else "",
        web_url=row.web_url if row else "",
        link_url=link_url(row),
        has_token=bool(row and row.token_sealed),
        token_readable=readable,
        token_set_at=row.token_set_at if row else None,
        configured=bool(row and row.base_url and readable),
        checked_at=row.checked_at if row else None,
        check_ok=row.check_ok if row else None,
        check_message=row.check_message if row else None,
        updated_by=editor.display_name if editor else None,
        updated_at=row.updated_at if row else None,
    )


def get(db: Session, system: str) -> IntegrationOut:
    return to_out(db, _system(system), _row(db, system))


def list_all(db: Session) -> list[IntegrationOut]:
    return [to_out(db, system, _row(db, system)) for system in SYSTEMS]


def update(db: Session, system: str, payload: IntegrationIn, user: User) -> IntegrationOut:
    _system(system)
    base = api_url(payload.base_url)
    web = _clean_url(payload.web_url, field="화면 주소")
    row = _row(db, system)
    if row is None:
        row = IntegrationConnection(system=system)
        db.add(row)
    changes: dict[str, Any] = {}
    if row.base_url != base:
        changes["base_url"] = {"before": row.base_url or None, "after": base or None}
        row.base_url = base
    if row.web_url != web:
        changes["web_url"] = {"before": row.web_url or None, "after": web or None}
        row.web_url = web
    token = (payload.token or "").strip()
    if payload.clear_token:
        if row.token_sealed:
            changes["token"] = "(지움)"
        row.token_sealed = ""
        row.token_set_at = None
    elif token:
        try:
            row.token_sealed = secretbox.seal(token)
        except secretbox.SecretError as exc:
            raise AppError(
                "MNX-INTEGRATIONS-0003", f"토큰을 봉인하지 못했습니다 — {exc}", status=500
            ) from exc
        row.token_set_at = datetime.now(UTC)
        # **값은 감사에 남기지 않는다** — 감사를 보는 사람이 토큰을 얻게 된다.
        changes["token"] = "(바뀜)"
    if changes:
        # 지난 확인은 옛 주소 · 토큰의 것이다 — 그대로 두면 「연결됨」 이 거짓말이 된다.
        row.checked_at = None
        row.check_ok = None
        row.check_message = None
        row.updated_by_id = user.id
        db.flush()
        audit.record(
            db,
            action=audit.INTEGRATION_UPDATED,
            actor=user,
            target_table="integration_connections",
            target_id=row.id,
            target_label=SYSTEMS[system],
            changes=changes,
        )
        # 물성 표 캐시는 옛 주소 · 토큰으로 받은 것이다.
        testscope.forget()
    db.commit()
    db.refresh(row)
    return to_out(db, system, row)


def credentials(db: Session, system: str) -> tuple[str, str] | None:
    """바깥에 물을 주소와 토큰 — 설정이 덜 됐거나 토큰을 못 풀면 None(지어 쓰지 않는다)."""
    _system(system)
    found = testscope.connection(db)
    return (found.api, found.token) if found else None


def _probe_testscope(base: str, token: str) -> IntegrationCheckOut:
    now = datetime.now(UTC)
    try:
        with testscope.client(base, token) as client:
            me = client.get("/auth/me")
            if me.status_code != 200:
                return IntegrationCheckOut(
                    ok=False, message=testscope.refused(me), checked_at=now
                )
            who = str(me.json().get("display_name") or me.json().get("email") or "")
            found = client.get("/properties", params={"include_unlinked": "false"})
            if found.status_code != 200:
                return IntegrationCheckOut(
                    ok=False, message=testscope.refused(found), checked_at=now, who=who
                )
            linked = len(found.json()) if isinstance(found.json(), list) else 0
    except httpx.HTTPError as exc:
        return IntegrationCheckOut(
            ok=False,
            message=f"TestScope 에 닿지 못했습니다 — 주소 · 방화벽 · 서비스 확인({exc}).",
            checked_at=now,
        )
    except ValueError:
        return IntegrationCheckOut(
            ok=False,
            message="TestScope 가 아닌 곳이 답했습니다(JSON 이 아님) — API 주소를 확인하세요.",
            checked_at=now,
        )
    message = f"연결됨 — TestScope 사용자 「{who}」, 시험 항목이 이어진 물성 {linked}개."
    if linked == 0:
        message += " 물성 연결이 없어 물성으로 장비를 찾지 못합니다."
    return IntegrationCheckOut(
        ok=True, message=message, checked_at=now, who=who, linked_properties=linked
    )


def check(db: Session, system: str) -> IntegrationCheckOut:
    """실제로 닿는지 본다 — 결과를 줄에 남겨 화면이 다음에도 보인다."""
    row = _row(db, _system(system))
    found = credentials(db, system)
    if row is None or found is None:
        if row is None or not row.base_url:
            message = "API 주소를 먼저 넣으세요."
        elif not row.token_sealed:
            message = "토큰을 먼저 넣으세요."
        else:
            message = "이 서버가 봉인한 토큰을 풀지 못합니다 — 토큰을 다시 넣으세요."
        return IntegrationCheckOut(ok=False, message=message, checked_at=datetime.now(UTC))
    result = _probe_testscope(*found)
    row.checked_at = result.checked_at
    row.check_ok = result.ok
    row.check_message = result.message
    db.commit()
    return result
