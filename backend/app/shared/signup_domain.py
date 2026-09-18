"""가입 아이디의 도메인 — **가입(accounts)과 로그인(auth)이 같은 규칙을 쓴다.**

설정 `SIGNUP_EMAIL_DOMAINS`(기본 samsung.com)가 정본이다. 모듈끼리 직접 부르지 않으므로
여기 둔다.
"""

from __future__ import annotations

from app.config import get_settings


def allowed_signup_domains() -> list[str]:
    """설정의 도메인을 **소문자·앞 `@` 없이** 정리한 것. `@Samsung.com` 으로 적어도 된다."""
    return [
        one.strip().lstrip("@").lower()
        for one in get_settings().signup_email_domains
        if one.strip().lstrip("@")
    ]


def complete_email(email: str) -> str:
    """`@` 없이 적은 아이디에 허용 도메인을 붙인다 — **사람에게 도메인을 치게 하지 않는다.**

    실사용(2026-09-18): 녹스 ID 만 치고 가입하다 「회사 메일 주소로만」 에 막히는 사람이
    있었다. 허용 도메인이 **하나뿐일 때만** 붙인다 — 둘 이상이면 어느 것인지 알 수 없어
    그대로 두고 `require_signup_domain` 이 막는다. 이미 `@` 가 있으면 손대지 않는다.
    소문자·양끝 공백 정리는 여기서 한 번에.
    """
    normalized = email.strip().lower()
    domains = allowed_signup_domains()
    if "@" not in normalized and len(domains) == 1 and normalized:
        return f"{normalized}@{domains[0]}"
    return normalized
