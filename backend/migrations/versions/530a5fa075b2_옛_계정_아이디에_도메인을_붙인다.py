"""옛 계정 아이디에 도메인을 붙인다 — `hong` → `hong@samsung.com`.

v1.242 전에는 도메인 없이 가입할 수 있었다. 이제 가입·로그인이 `@` 없는 아이디에
허용 도메인을 붙이므로(`shared/signup_domain.complete_email`), 옛 계정도 같은 모양으로
맞춘다. 옛 아이디(`hong`)로 로그인하면 여전히 들어오고 「@samsung.com 이 붙었다」 고
알려 준다(2026-09-18 결정).

- 시스템 관리자(`admin`)는 그대로 둔다 — 가입 도메인 제한이 처음부터 admin 을 뺐다.
- 붙인 아이디가 이미 있으면(`hong` 과 `hong@samsung.com` 이 둘 다) 손대지 않는다 —
  어느 쪽이 그 사람인지는 관리자가 정한다.
- 허용 도메인이 하나가 아니면 아무것도 안 한다 — 어느 것을 붙일지 알 수 없다.

Revision ID: 530a5fa075b2
Revises: e004e443d2fb
Create Date: 2026-09-18 12:55:13.507016

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "530a5fa075b2"
down_revision: Union[str, Sequence[str], None] = "e004e443d2fb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _single_domain() -> str | None:
    try:
        from app.shared.signup_domain import allowed_signup_domains

        domains = allowed_signup_domains()
    except Exception:  # 설정을 못 읽으면 기본값 — 설정의 기본과 같다
        domains = ["samsung.com"]
    return domains[0] if len(domains) == 1 else None


def upgrade() -> None:
    domain = _single_domain()
    if domain is None:
        return
    op.execute(
        sa.text(
            """
            UPDATE users AS u
               SET email = u.email || :suffix
             WHERE u.email NOT LIKE '%@%'
               AND u.is_system_admin = false
               AND NOT EXISTS (
                     SELECT 1 FROM users AS taken WHERE taken.email = u.email || :suffix
                   )
            """
        ).bindparams(suffix=f"@{domain}")
    )


def downgrade() -> None:
    # 되돌리지 않는다 — 어느 계정이 이 마이그레이션으로 붙은 것인지 구별할 표지가 없고,
    # 새 규칙으로 가입한 계정까지 도메인을 떼면 로그인 아이디가 바뀐다.
    pass
