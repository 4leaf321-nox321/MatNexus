"""토큰 — refresh 폐기 목록과 PAT.

**refresh 토큰을 JWT로 만들지 않는다.** JWT는 서버가 상태를 갖지 않으므로
발급한 뒤에는 되돌릴 수 없다. RA가 정확히 그 상태이고(비교표: *"stateless
refresh — DB 폐기 목록 없음"*), 비교표는 *"자체 인증을 새로 만든다면 DB 폐기
목록을 처음부터 넣을 것"* 이라고 못박았다. 그래서 refresh 는 불투명 난수이고
여기 한 행으로 존재한다 — 행을 지우거나 `revoked_at` 을 채우면 즉시 무효다.

원문은 어디에도 저장하지 않는다. sha256 해시만 둔다. DB가 새어도 남의 세션을
탈취할 수 없어야 한다.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    replaced_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("refresh_tokens.id", ondelete="SET NULL"),
        nullable=True,
    )
    """회전(rotation) 이력. 폐기된 토큰이 다시 쓰이면 탈취 신호로 볼 수 있다."""

    user_agent: Mapped[str | None] = mapped_column(String(300), nullable=True)


class PersonalAccessToken(Base):
    """장비 파이프라인·스크립트가 API를 부를 때 쓰는 자격 증명 (구조결정 9).

    Phase 6에서 장비 커넥터가 데이터를 밀어 넣을 때 무슨 자격으로 부를지가
    지금 정해져 있어야 토큰 체계가 둘로 갈라지지 않는다. 사람 세션(refresh)과
    기계 자격(PAT)은 수명과 폐기 방식이 다르므로 테이블을 나눈다.
    """

    __tablename__ = "personal_access_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    """어디에 쓰는 토큰인지. 폐기할 때 이것만 보고 판단하게 된다."""

    prefix: Mapped[str] = mapped_column(String(16), index=True)
    """평문의 앞자리. 목록 화면에서 어느 토큰인지 알아보게 하는 용도."""
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    """마지막 사용 시각. 안 쓰는 토큰을 찾아 지우는 근거가 된다."""
