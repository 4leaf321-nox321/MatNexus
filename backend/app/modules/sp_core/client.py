"""SP 코어 API 를 읽는 자리 — **지침서 §4.2 의 봉투만 안다.**

    GET {base}                       카탈로그 — 무엇이 열려 있나(`system · revision · types`)
    GET {base}/{type}                행 — `since · cursor · limit`, 봉투 `{as_of, next, items}`
    GET {base}/{type}/relations      선 — 같은 규칙 + `reset`

`base` 는 설정의 `sp_core_url`(…`/api/core`)이다. 카탈로그가 주는 `endpoint` 주소로는 가지
않는다 — 응답이 가리키는 곳으로 토큰을 들고 가지 않게.

## 404 는 둘이다(규칙 11)

`APP-CORE-0001` 은 「공개 안 된 타입」(그 타입 수신을 멈추고 알린다), `APP-CORE-0002` 는
「커서를
못 읽음」(커서 없이 지난 `as_of` 부터 다시 받는다). 상태 코드만 보고 고르면 커서 하나로 타입을
통째로 멈춘다 — 그래서 본문의 코드로 가른다.

DB 를 모른다. 시험은 `httpx.MockTransport` 를 넣어 SP 없이 돈다.
"""

from __future__ import annotations

from typing import Any

import httpx

#: SP 의 최대(`coreapi.services.MAX_LIMIT`). 쪽이 적을수록 왕복이 준다.
PAGE_LIMIT = 2_000
TIMEOUT_SECONDS = 60.0


class SpCoreError(Exception):
    """받기를 멈춰야 하는 실패 — 사람이 읽을 한 줄을 든다."""


class NotPublished(SpCoreError):
    """`APP-CORE-0001` — 그 타입이 더 이상 공개돼 있지 않다."""


class BadCursor(SpCoreError):
    """`APP-CORE-0002` — 커서를 못 읽었다. 커서 없이 지난 `as_of` 부터 다시 받는다."""


def _code_of(response: httpx.Response) -> str:
    """SP 오류 본문의 코드 — 모양이 달라도 터지지 않게 넓게 찾는다."""
    try:
        body = response.json()
    except ValueError:
        return ""
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict) and isinstance(error.get("code"), str):
            return str(error["code"])
        if isinstance(body.get("code"), str):
            return str(body["code"])
        detail = body.get("detail")
        if isinstance(detail, dict) and isinstance(detail.get("code"), str):
            return str(detail["code"])
    return ""


class SpCoreClient:
    """코어 창구 하나. `with` 로 쓰면 연결을 한 번만 연다."""

    def __init__(
        self,
        base: str,
        token: str,
        *,
        transport: httpx.BaseTransport | None = None,
        timeout: float = TIMEOUT_SECONDS,
    ) -> None:
        if not base or not token:
            raise SpCoreError(
                "SP 코어 주소(SP_CORE_URL)와 토큰(SP_CORE_TOKEN)이 설정돼 있지 않습니다."
            )
        self.base = base.rstrip("/")
        self._client = httpx.Client(
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=timeout,
            transport=transport,
            # 리다이렉트를 따라가지 않는다 — 토큰을 다른 주소로 들고 가지 않게.
            follow_redirects=False,
        )

    def __enter__(self) -> SpCoreClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = self.base + path
        try:
            response = self._client.get(
                url, params={k: v for k, v in (params or {}).items() if v}
            )
        except httpx.HTTPError as failed:
            raise SpCoreError(f"SP 코어에 닿지 못했습니다({self.base}): {failed}") from failed
        if response.status_code == 404:
            code = _code_of(response)
            if code.endswith("CORE-0002"):
                raise BadCursor(f"SP 가 커서를 못 읽었습니다({path}).")
            if code.endswith("CORE-0001"):
                raise NotPublished(f"SP 가 이 타입을 더 이상 공개하지 않습니다({path}).")
            raise SpCoreError(
                f"SP 코어가 404 를 줬습니다({path}) — 주소(SP_CORE_URL)를 보세요."
            )
        if response.status_code in (401, 403):
            raise SpCoreError(
                f"SP 코어가 {response.status_code} 를 줬습니다 — 토큰(SP_CORE_TOKEN)이 "
                "맞는지, "
                "`core:read` 범위인지 보세요."
            )
        if response.status_code >= 300:
            raise SpCoreError(f"SP 코어가 {response.status_code} 를 줬습니다({path}).")
        try:
            body = response.json()
        except ValueError as failed:
            raise SpCoreError(f"SP 코어 응답이 JSON 이 아닙니다({path}).") from failed
        if not isinstance(body, dict):
            raise SpCoreError(f"SP 코어 응답의 모양이 다릅니다({path}).")
        return body

    def catalog(self) -> dict[str, Any]:
        """무엇이 열려 있나 — `system · revision · as_of · types`."""
        return self._get("")

    def rows(
        self, type_slug: str, *, since: str | None, cursor: str | None, limit: int = PAGE_LIMIT
    ) -> dict[str, Any]:
        """행 한 쪽 — `{as_of, next, items}`. `next` 가 있으면 `as_of` 는 null 이다(규칙 2)."""
        return self._get(f"/{type_slug}", {"since": since, "cursor": cursor, "limit": limit})

    def relations(
        self, type_slug: str, *, since: str | None, cursor: str | None, limit: int = PAGE_LIMIT
    ) -> dict[str, Any]:
        """선 한 쪽 — 행과 같은 규칙에 `reset` 이 더 온다."""
        return self._get(
            f"/{type_slug}/relations", {"since": since, "cursor": cursor, "limit": limit}
        )
