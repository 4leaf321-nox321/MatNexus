"""재료 검색에 trigram 인덱스

**`ILIKE '%낱말%'` 은 B-tree 를 못 탄다.** 앞에 와일드카드가 있어서 어느
접두사부터 봐야 할지 정할 수가 없다. 그래서 지금 검색은 매 타이핑마다 재료
전체를 훑는다.

실측(합성 5만 건, `matnexus_bench`):

    검색 1낱말   목록 92ms + 개수 116ms = 208ms
    검색 2낱말   목록 27ms + 개수 122ms = 149ms

**개수 세기가 더 비싸다.** 목록은 `LIMIT 50` 에서 멈출 수 있지만 `count(*)` 는
조건에 맞는 행을 끝까지 세야 한다. 그리고 이 비용은 재료 수에 정비례한다 —
50만 건이면 1초를 넘긴다.

`pg_trgm` 의 GIN 인덱스는 문자열을 세 글자씩 쪼개 색인하므로 가운데 일치도
인덱스를 탄다. 한글도 글자 단위로 쪼개져 동작한다(두 글자 이하 검색은 트라이그램이
안 나와 스캔으로 떨어진다 — 그건 감수한다).

## OR 가지는 **전부** 인덱스가 있어야 한다

처음에 `record_name`·`alias` 둘만 색인했더니 아무 효과가 없었다. 실행 계획을
보면 이유가 분명하다 — 여섯 컬럼을 `OR` 로 묶으면 색인 안 된 가지 하나 때문에
어차피 전 행을 훑어야 한다.

    6개 OR : Seq Scan  118ms
    2개 OR : BitmapOr → Bitmap Index Scan  4.6ms   (25배)

그래서 **검색 대상을 줄이고 그 전부를 색인한다.** `grade` 와 `details` 는 빼도
잃는 것이 없다 — `record_name` 이 `{grade}_{details}_{두께}` 라서(ADR 0004) 이름
인덱스가 그 검색을 이미 덮는다.

    SECC180_MDOI_1.0   ← grade 도 details 도 여기 들어 있다

`family`·`category` 는 이름에 없으므로 남기고 색인한다. 이 둘은 곧 어휘 외래키가
되므로(ADR 0010) 그때 이 인덱스도 함께 옮긴다.

Revision ID: 154c0d5508af
Revises: b371627c5768
Create Date: 2026-08-19

"""

from typing import Sequence, Union

from alembic import op

revision: str = "154c0d5508af"
down_revision: Union[str, Sequence[str], None] = "b371627c5768"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 확장은 슈퍼유저가 필요하다. install.ps1 이 postgres 로 붙으므로 통과하지만,
    # 권한이 없는 계정으로 배포하면 여기서 멈춘다 — 조용히 넘기지 않는다.
    # 인덱스 없이 도는 시스템은 느린 것이 아니라 **나중에 못 고치는** 것이다.
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        "CREATE INDEX ix_materials_record_name_trgm ON materials"
        " USING gin (record_name gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX ix_materials_alias_trgm ON materials USING gin (alias gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX ix_materials_family_trgm ON materials USING gin (family gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX ix_materials_category_trgm ON materials"
        " USING gin (category gin_trgm_ops)"
    )


def downgrade() -> None:
    """Downgrade schema.

    확장은 지우지 않는다 — 다른 것이 쓰고 있을 수 있고, 남아 있어도 해가 없다.
    """
    op.execute("DROP INDEX IF EXISTS ix_materials_category_trgm")
    op.execute("DROP INDEX IF EXISTS ix_materials_family_trgm")
    op.execute("DROP INDEX IF EXISTS ix_materials_alias_trgm")
    op.execute("DROP INDEX IF EXISTS ix_materials_record_name_trgm")
