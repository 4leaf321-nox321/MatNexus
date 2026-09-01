"""의존성 레지스트리 — "무엇이 이 행을 가리키는가"에 답한다.

**삭제·이관 기능을 만들기 전에 있어야 한다.** RA 주석에 남은 실제 장애가 근거다:
부서 삭제 500 버그의 원인이 "참조 테이블 목록이 검사 함수에 하드코딩돼 새 테이블을
못 따라감(files·html_embed_bundles·composite_reports 누락)" 이었다. 사람이 관리하는
목록은 반드시 뒤처진다.

그래서 `Base.metadata` 를 훑어 FK 를 **자동 수집**한다. Phase 2에서 시험 데이터
테이블이 늘어나도 이 파일은 그대로다.

FK 로 잡히지 않는 참조(배열 컬럼·다형 참조·정책상 차단)는 `EXTRA_CHECKS` 에
손으로 보탠다. 지금은 비어 있지만, 자리를 만들어 두지 않으면 그런 참조가 생겼을 때
검사 자체를 우회하게 된다.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import Base

#: 사람이 읽을 이름. 없으면 테이블 이름을 그대로 쓴다 — 빠뜨려도 동작은 한다.
TABLE_LABELS: dict[str, str] = {
    "workspace_members": "부서 멤버십",
    "refresh_tokens": "로그인 세션",
    "personal_access_tokens": "개인 액세스 토큰",
    "users": "계정",
    "workspaces": "부서",
    "materials": "재료",
    "samples": "시료",
    "specimens": "시편",
    "test_runs": "시험",
    "workbench_items": "워크벤치 작업에 담긴 것",
    "curves": "곡선",
    "test_summaries": "시험 요약값",
    "pipeline_connectors": "장비 커넥터",
    "pipeline_inbox_items": "수집함 항목",
    "guide_documents": "가이드 문서",
    "guide_sections": "가이드 절",
    "guide_revisions": "가이드 리비전",
    "guide_assets": "가이드 그림",
}

#: FK 로 표현되지 않는 참조를 보탤 자리.
#: 시그니처: (db, table, pk) -> list[Reference]
EXTRA_CHECKS: list[Callable[[Session, str, Any], list[Reference]]] = []


@dataclass(frozen=True)
class Reference:
    """이 행을 가리키는 참조 하나."""

    table: str
    column: str
    count: int
    on_delete: str | None
    """DB 가 알아서 처리하는지 알려 준다.
    CASCADE  = 함께 지워진다        (사용자에게 알릴 필요는 있다)
    SET NULL = 참조만 끊긴다
    None     = 아무 규칙이 없다 — 지우려면 먼저 정리해야 한다"""

    @property
    def label(self) -> str:
        return TABLE_LABELS.get(self.table, self.table)

    @property
    def blocks_delete(self) -> bool:
        """지우려면 먼저 정리해야 하는 참조인가.

        규칙이 **없을 때**(None)만이 아니다. `RESTRICT`·`NO ACTION` 은 DB 가
        적극적으로 **거부**하는 규칙이라 마찬가지로 막힌다. 이 둘을 "DB 가 알아서
        한다" 쪽으로 세면 화면은 '삭제 가능' 이라고 해 놓고 누르는 순간 500 이
        난다 — 부서에 `parent_id` 를 RESTRICT 로 넣으면서 실제로 그럴 뻔했다.
        """
        rule = (self.on_delete or "").upper().replace(" ", "")
        return rule in ("", "RESTRICT", "NOACTION")


def references_to(db: Session, *, table: str, pk: Any) -> list[Reference]:
    """`table` 의 기본키 `pk` 를 가리키는 모든 참조를 센다.

    개수가 0인 참조는 돌려주지 않는다 — 화면에 "0건" 목록을 늘어놓아 봐야
    무엇이 문제인지 흐려질 뿐이다.
    """
    import app.all_models  # noqa: F401  (metadata 를 채운다)

    found: list[Reference] = []

    for source in Base.metadata.sorted_tables:
        for column in source.columns:
            for fk in column.foreign_keys:
                if fk.column.table.name != table:
                    continue
                count = (
                    db.scalar(select(func.count()).select_from(source).where(column == pk))
                    or 0
                )
                if count:
                    found.append(
                        Reference(
                            table=source.name,
                            column=column.name,
                            count=count,
                            on_delete=fk.ondelete,
                        )
                    )

    for check in EXTRA_CHECKS:
        found.extend(check(db, table, pk))

    return sorted(found, key=lambda ref: (ref.table, ref.column))


def blocking(references: list[Reference]) -> list[Reference]:
    return [ref for ref in references if ref.blocks_delete]


#: 소유를 뜻하는 컬럼 이름. 계정을 지울 때 이 컬럼들만 다른 사람에게 넘긴다.
#:
#: **이름 규약으로 두는 이유**: Phase 2에서 시험·곡선·모델 테이블이 생길 때마다
#: 승계 함수를 고치면 반드시 빠뜨린다(RA 의 부서 삭제 500 버그가 그것이다).
#: 새 테이블이 이 이름을 쓰면 자동으로 승계 대상이 된다.
#:
#: 반대로 이력·감사 성격의 참조(`decided_by_id` 등)는 넘기지 않는다 —
#: "누가 승인했는가"는 사실이라 소유권처럼 이전할 수 있는 것이 아니다.
OWNER_COLUMNS = frozenset({"owner_id", "created_by_id", "registered_by_id"})


def transfer_ownership(
    db: Session, *, table: str, from_pk: Any, to_pk: Any
) -> list[Reference]:
    """소유 컬럼을 다른 사람에게 넘긴다. 옮긴 내역을 돌려준다.

    커밋은 호출부가 한다 — 승계와 삭제가 한 트랜잭션이어야 "옮기다 만" 상태가
    남지 않는다.
    """
    import app.all_models  # noqa: F401

    moved: list[Reference] = []

    for source in Base.metadata.sorted_tables:
        for column in source.columns:
            if column.name not in OWNER_COLUMNS:
                continue
            if not any(fk.column.table.name == table for fk in column.foreign_keys):
                continue

            count = (
                db.scalar(select(func.count()).select_from(source).where(column == from_pk))
                or 0
            )
            if not count:
                continue

            db.execute(source.update().where(column == from_pk).values({column.name: to_pk}))
            moved.append(
                Reference(table=source.name, column=column.name, count=count, on_delete=None)
            )

    return sorted(moved, key=lambda ref: (ref.table, ref.column))


def describe(references: list[Reference]) -> str:
    """사람이 읽는 요약. 오류 메시지에 그대로 넣는다."""
    if not references:
        return "참조 없음"
    return ", ".join(f"{ref.label} {ref.count}건" for ref in references)
