"""물성 항목 개명 — 열전도도 → 열전도율 · 열팽창계수 → 선팽창계수(CTE)

Revision ID: d47e91b0c3a8
Revises: a1c6f83d259b
Create Date: 2026-09-06

사용자 결정(2026-09-05, MaterialTwin 이식 라벨 정합에서). 세 가지를 함께 한다:

    ① 기준정보 term 의 이름을 바꾼다 (normalized 재계산)
    ② 옛 이름을 별칭으로 흡수한다 — 옛 이름으로 검색·매칭이 계속 닿는다
    ③ 재료·시료에 이미 저장된 선언 줄의 item 을 따라 바꾼다 — 안 바꾸면
       그 줄들이 「기준정보에 없는 항목」 이 되어 화면·검증에서 고아가 된다

normalized 값은 compare_key 실측치를 하드코딩한다 — 마이그레이션은 앱 코드가
바뀌어도 같은 일을 해야 한다. 씨앗을 안 심은 DB(축·항목 없음)는 전부 건너뛴다
(새 DB 는 씨앗이 처음부터 새 이름으로 심는다). 손으로 쓴 마이그레이션이다.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d47e91b0c3a8"
down_revision: Union[str, Sequence[str], None] = "a1c6f83d259b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

#: (옛 이름, 옛 normalized, 새 이름, 새 normalized)
RENAMES = [
    ("열전도도", "열전도도", "열전도율", "열전도율"),
    ("열팽창계수", "열팽창계수", "선팽창계수(CTE)", "선팽창계수(cte)"),
]


def _rename_terms(old: str, old_norm: str, new: str, new_norm: str) -> None:
    con = op.get_bind()
    axis_id = con.execute(
        sa.text("select id from vocabularies where slug = 'property_item'")
    ).scalar()
    if axis_id is None:
        return
    term_id = con.execute(
        sa.text(
            "select id from vocabulary_terms"
            " where vocabulary_id = :axis and normalized = :norm"
        ),
        {"axis": axis_id, "norm": old_norm},
    ).scalar()
    if term_id is None:
        return
    con.execute(
        sa.text(
            "update vocabulary_terms set value = :new, normalized = :new_norm where id = :term"
        ),
        {"new": new, "new_norm": new_norm, "term": term_id},
    )
    # 옛 이름을 별칭으로 — 이미 있으면(재실행) 그대로 둔다.
    con.execute(
        sa.text(
            "insert into vocabulary_aliases (id, vocabulary_id, term_id, alias, normalized)"
            " values (gen_random_uuid(), :axis, :term, :alias, :norm)"
            " on conflict (vocabulary_id, normalized) do nothing"
        ),
        {"axis": axis_id, "term": term_id, "alias": old, "norm": old_norm},
    )


def _rename_declared_rows(table: str, old: str, new: str) -> None:
    """저장된 선언 줄의 item 치환. 해당 항목이 든 행만 배열을 다시 만든다."""
    op.execute(
        sa.text(
            f"""
            update {table} set declared_properties = (
                select jsonb_agg(
                    case when elem->>'item' = :old
                         then jsonb_set(elem, '{{item}}', to_jsonb(cast(:new as text)))
                         else elem end)
                from jsonb_array_elements(declared_properties) as elem
            )
            where declared_properties @> jsonb_build_array(jsonb_build_object('item', :old))
            """
        ).bindparams(old=old, new=new)
    )


def upgrade() -> None:
    for old, old_norm, new, new_norm in RENAMES:
        _rename_terms(old, old_norm, new, new_norm)
        _rename_declared_rows("materials", old, new)
        _rename_declared_rows("samples", old, new)


def downgrade() -> None:
    con = op.get_bind()
    for old, old_norm, new, new_norm in RENAMES:
        _rename_terms(new, new_norm, old, old_norm)
        # 정방향이 만든 「옛 이름」 별칭과, 역방향이 방금 만든 「새 이름」 별칭을 걷는다.
        con.execute(
            sa.text(
                "delete from vocabulary_aliases where normalized in (:a, :b)"
                " and vocabulary_id = (select id from vocabularies where slug = 'property_item')"
            ),
            {"a": old_norm, "b": new_norm},
        )
        _rename_declared_rows("materials", new, old)
        _rename_declared_rows("samples", new, old)
