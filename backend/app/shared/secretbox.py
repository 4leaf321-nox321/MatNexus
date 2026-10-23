"""비밀값 봉인 — **Windows DPAPI(기계 범위)로 암호화해 DB 에 둔다.**

TestScope 읽기 토큰처럼 화면에서 받아 DB 에 두는 비밀이 처음 생겼다(2026-10-23). 평문으로 두면
DB 백업 · 덤프를 본 사람 누구나 그 토큰으로 바깥 시스템을 읽는다. `.env` 에 두면 시스템
관리자가 서버 파일을 고쳐야 바뀐다 — 사용자가 화면에서 넣기를 원했다.

**새 의존성을 들이지 않는다.** 운영 · CI · 개발이 모두 Windows 라 운영체제가 키를 관리하는
DPAPI 를 쓴다(`CryptProtectData`, 기계 범위). TestScope 의 `shared/secretbox` 와 같은 방식이다.
앱 비밀값(`JWT_SECRET`)을 보조 엔트로피로 더해, 같은 PC 의 다른 프로그램이 DB 값만으로는 못
푼다(TestScope 와 접두가 달라 서로의 봉인값도 못 푼다).

못 푸는 경우가 있다 — DB 를 다른 PC 로 옮겼거나 `JWT_SECRET` 을 바꿨을 때. 그때는 빈 값을
돌려주고 화면이 「토큰 다시 입력」 을 말한다(지어서 쓰지 않는다).
"""

from __future__ import annotations

import base64
import ctypes
import hashlib
import sys

from app.config import get_settings

PREFIX = "dpapi:v1:"

_UI_FORBIDDEN = 0x1
_LOCAL_MACHINE = 0x4


class SecretError(RuntimeError):
    """봉인하지 못했다 — 이 플랫폼에 DPAPI 가 없거나 운영체제가 거절했다."""


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob(data: bytes) -> tuple[_Blob, ctypes.Array[ctypes.c_char]]:
    """`DATA_BLOB` 과 그 버퍼 — 버퍼를 함께 돌려줘야 호출이 끝날 때까지 살아 있다."""
    buffer = ctypes.create_string_buffer(data, len(data))
    return _Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char))), buffer


def _entropy() -> bytes:
    secret = get_settings().jwt_secret
    return hashlib.sha256(("matnexus-secretbox:" + secret).encode("utf-8")).digest()


def _call(protect: bool, data: bytes) -> bytes:
    if sys.platform != "win32":
        raise SecretError("비밀값 봉인은 Windows(DPAPI)에서만 됩니다.")
    crypt32 = ctypes.windll.crypt32  # type: ignore[attr-defined,unused-ignore]
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined,unused-ignore]
    source, _keep = _blob(data)
    entropy, _keep_entropy = _blob(_entropy())
    out = _Blob()
    fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    ok = fn(
        ctypes.byref(source),
        None,
        ctypes.byref(entropy),
        None,
        None,
        _UI_FORBIDDEN | _LOCAL_MACHINE,
        ctypes.byref(out),
    )
    if not ok:
        raise SecretError("운영체제가 비밀값 처리를 거절했습니다.")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        kernel32.LocalFree(out.pbData)


def seal(plaintext: str) -> str:
    """평문 → `dpapi:v1:<base64>`. 빈 값은 빈 값."""
    if not plaintext:
        return ""
    return PREFIX + base64.b64encode(_call(True, plaintext.encode("utf-8"))).decode("ascii")


def unseal(sealed: str) -> str:
    """봉인값 → 평문. **못 풀면 빈 값** — 다른 PC 로 옮긴 DB · 바뀐 `JWT_SECRET`."""
    if not sealed or not sealed.startswith(PREFIX):
        return ""
    try:
        return _call(False, base64.b64decode(sealed[len(PREFIX) :])).decode("utf-8")
    except (SecretError, ValueError):
        return ""
